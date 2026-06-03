import asyncio
import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from browser_use import Agent, BrowserSession

from services.llm_factory import ProviderNotConfiguredError, create_llm
from services.config_store import get_provider_config

SESSION_DIR = Path(__file__).parent.parent / ".sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

STORAGE_STATE_PATH = SESSION_DIR / "browser_state.json"

logger = logging.getLogger(__name__)


@dataclass
class StepEvent:
    step: int
    action: str
    target: str
    status: str
    screenshot: str | None = None


@dataclass
class ResultEvent:
    output: str
    steps: int
    duration_ms: int


@dataclass
class ErrorEvent:
    message: str
    step: int


@dataclass
class InteractiveEvent:
    type: str
    message: str
    screenshot: str | None = None


class AgentRunner:
    def __init__(self) -> None:
        self._agent: Agent | None = None
        self._running = False
        self._step_events: list[StepEvent] = []
        self._start_time: float = 0
        self._on_step: list[object] = []
        self._on_result: list[object] = []
        self._on_error: list[object] = []
        self._on_interactive: list[object] = []
        self._lock = asyncio.Lock()
        self._result_sent = False
        self._input_future: asyncio.Future | None = None
        self._command_queue: deque = deque()
        self._browser_session: BrowserSession | None = None
        self._queue_max_size = 50
        self._idle_timer: asyncio.Task | None = None
        self._idle_timeout = 5 * 60
        self._ws: Any = None
        self._queue_handled = False

    def set_ws(self, ws: Any) -> None:
        self._ws = ws

    @property
    def running(self) -> bool:
        return self._running

    @property
    def step_events(self) -> list[StepEvent]:
        return self._step_events

    def on_step(self, callback) -> None:
        self._on_step.append(callback)

    def on_result(self, callback) -> None:
        self._on_result.append(callback)

    def on_error(self, callback) -> None:
        self._on_error.append(callback)

    def off_step(self, callback) -> None:
        try:
            self._on_step.remove(callback)
        except ValueError:
            pass

    def off_result(self, callback) -> None:
        try:
            self._on_result.remove(callback)
        except ValueError:
            pass

    def off_error(self, callback) -> None:
        try:
            self._on_error.remove(callback)
        except ValueError:
            pass

    def on_interactive(self, callback) -> None:
        self._on_interactive.append(callback)

    def off_interactive(self, callback) -> None:
        try:
            self._on_interactive.remove(callback)
        except ValueError:
            pass

    def provide_input(self, user_input: dict) -> None:
        if self._input_future and not self._input_future.done():
            self._input_future.set_result(user_input)

    async def enqueue(self, command: str) -> None:
        if len(self._command_queue) >= self._queue_max_size:
            from api.ws import send_queue_status
            if self._ws:
                await send_queue_status(self._ws, len(self._command_queue))
                await self._ws.send_json({
                    "type": "error",
                    "data": {"message": "Queue is full (max 50 commands)", "step": 0}
                })
            return

        self._command_queue.append(command)

        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None

        from api.ws import send_queue_status
        if self._ws:
            await send_queue_status(self._ws, len(self._command_queue))

        if not self._running:
            asyncio.create_task(self._run_next())

    async def _run_next(self) -> None:
        if not self._command_queue:
            return
        command = self._command_queue.popleft()
        logger.info(f"[AgentRunner] Dequeued command: {command[:50]}...")
        try:
            await self.run(command)
        except Exception as e:
            logger.exception(f"[AgentRunner] Command execution failed: {e}")
            for cb in self._on_error:
                await cb(ErrorEvent(message=str(e), step=0))

    async def _idle_wait(self) -> None:
        await asyncio.sleep(self._idle_timeout)
        if self._browser_session:
            await self._browser_session.close()
            self._browser_session = None
        from api.ws import send_queue_status
        if self._ws:
            await send_queue_status(self._ws, 0)

    async def run(
        self,
        task: str,
        *,
        sensitive_data: dict[str, str | dict[str, str]] | None = None,
        initial_actions: list[dict[str, dict[str, Any]]] | None = None,
        use_vision: bool = True,
        max_failures: int = 5,
        max_actions_per_step: int = 5,
        step_timeout: int = 180,
        headless: bool = True,
    ) -> None:
        async with self._lock:
            if self._running:
                raise RuntimeError("A task is already running")
            self._running = True

        self._step_events = []
        self._start_time = time.time()
        self._result_sent = False
        logger.info(f"[AgentRunner] Task started: {task[:50]}...")

        try:
            llm = create_llm()
        except (ProviderNotConfiguredError, ValueError) as e:
            self._running = False
            for cb in self._on_error:
                await cb(ErrorEvent(message=str(e), step=0))
            return

        saved_config = get_provider_config()
        browser_mode = "local"
        browser_use_api_key = ""

        env_api_key = os.getenv("BROWSER_USE_API_KEY")
        if env_api_key:
            browser_use_api_key = env_api_key
            browser_mode = "cloud"
        elif saved_config:
            browser_mode = saved_config.get("browser_mode", "local")
            if browser_mode == "cloud":
                browser_use_api_key = saved_config.get("browser_use_api_key", "")

        if browser_use_api_key:
            os.environ["BROWSER_USE_API_KEY"] = browser_use_api_key
            browser_session = BrowserSession(use_cloud=True, cloud_browser=True)
        elif headless:
            browser_session = BrowserSession(storage_state=str(STORAGE_STATE_PATH) if STORAGE_STATE_PATH.exists() else None)
        else:
            browser_session = BrowserSession(headless=False, storage_state=str(STORAGE_STATE_PATH) if STORAGE_STATE_PATH.exists() else None)

        # Store as persistent session for reuse
        self._browser_session = browser_session
        agent_history_ref = None

        # Initialize browser (creates cloud browser if needed) and reset page context before each command
        try:
            cdp = await browser_session.get_or_create_cdp_session()
            await cdp.Page.navigate(url="about:blank")
        except Exception as e:
            logger.warning(f"[AgentRunner] Failed to reset page context: {e}")

        # Emit live_url if cloud mode - sent inside step_callback when cdp_url is actually available
        _live_url_sent = False

        async def step_callback(browser_state, agent_output, step_number):
            # Emit live_url on first step when cloud mode and cdp_url is available
            nonlocal _live_url_sent
            if browser_use_api_key and not _live_url_sent and self._ws:
                cdp_url = browser_session.cdp_url
                if cdp_url:
                    live_url = f"https://live.browser-use.com/?wss={quote(str(cdp_url), safe='')}"
                    from api.ws import send_live_url
                    await send_live_url(self._ws, live_url)
                    _live_url_sent = True

            action_desc = ""
            target_desc = ""
            try:
                if agent_output and not isinstance(agent_output, str) and hasattr(agent_output, 'action'):
                    action = agent_output.action
                    if isinstance(action, list) and action:
                        first_action = action[0]
                        if hasattr(first_action, "model_dump"):
                            action_dict = first_action.model_dump()
                        elif isinstance(first_action, dict):
                            action_dict = first_action
                        else:
                            action_dict = {}
                        if action_dict:
                            action_name = next(iter(action_dict), "unknown")
                            action_desc = action_name
                            action_params = action_dict.get(action_name, {})
                            target_desc = action_params.get("index", "") or action_params.get("url", "") or ""
            except Exception as e:
                logger.warning(f"[AgentRunner] step_callback action parse error: {e}")

            screenshot = browser_state.screenshot if browser_state else None

            event = StepEvent(
                step=step_number,
                action=action_desc,
                target=str(target_desc),
                status="running",
                screenshot=screenshot,
            )

            page_url = ""
            page_text = ""
            if browser_state:
                if hasattr(browser_state, 'url') and browser_state.url:
                    page_url = str(browser_state.url)
                if hasattr(browser_state, 'tabs') and browser_state.tabs:
                    for tab in browser_state.tabs:
                        if hasattr(tab, 'page_text') and tab.page_text:
                            page_text = str(tab.page_text)[:2000]

            login_keywords = ['login', 'sign in', '扫码', '登录', '二维码', 'qr code', 'scan']
            url_match = any(k in page_url.lower() for k in login_keywords)
            text_match = any(k in page_text.lower() for k in login_keywords)

            if (url_match or text_match) and screenshot:
                cmd_type = "login_qr"
                cmd_msg = "请扫码登录或确认登录状态"
                event_interactive = InteractiveEvent(type=cmd_type, message=cmd_msg, screenshot=screenshot)
                for cb in self._on_interactive:
                    await cb(event_interactive)
                self._input_future = asyncio.Future()
                try:
                    await asyncio.wait_for(self._input_future, timeout=300)
                except asyncio.TimeoutError:
                    logger.warning("[AgentRunner] Interactive input timed out")

            self._step_events.append(event)
            for cb in self._on_step:
                await cb(event)

        async def done_callback(history):
            if self._result_sent:
                return
            self._result_sent = True
            duration_ms = int((time.time() - self._start_time) * 1000)
            output = history.final_result() or ""
            steps = history.number_of_steps()

            result = ResultEvent(output=str(output), steps=steps, duration_ms=duration_ms)
            for cb in self._on_result:
                await cb(result)

            # Save browser state before session closes
            try:
                if browser_session and not browser_use_api_key:
                    state = await browser_session.export_storage_state()
                    if state and (state.get("cookies") or state.get("origins")):
                        STORAGE_STATE_PATH.write_text(json.dumps(state, indent=2))
                        logger.info(f"[AgentRunner] Browser state saved to {STORAGE_STATE_PATH}")
            except Exception as e:
                logger.warning(f"[AgentRunner] Failed to save browser state in done_callback: {e}")

            # Queue next command if available, otherwise start idle timer
            if self._command_queue:
                asyncio.create_task(self._run_next())
            else:
                self._idle_timer = asyncio.create_task(self._idle_wait())

        try:
            self._agent = Agent(
                task=task,
                llm=llm,
                browser_session=browser_session,
                register_new_step_callback=step_callback,
                register_done_callback=done_callback,
                use_thinking=False,
                sensitive_data=sensitive_data,
                initial_actions=initial_actions,
                use_vision=use_vision,
                max_failures=max_failures,
                max_actions_per_step=max_actions_per_step,
                step_timeout=step_timeout,
            )
            agent_history_ref = self._agent
            await asyncio.wait_for(self._agent.run(), timeout=600)
        except asyncio.TimeoutError:
            logger.warning("[AgentRunner] Task timed out after 10 minutes")
            duration_ms = int((time.time() - self._start_time) * 1000)

            partial_output = ""
            agent_history = getattr(agent_history_ref, 'history', None)
            if agent_history is not None:
                try:
                    partial_output = agent_history.final_result() or ""
                except Exception as e:
                    logger.warning(f"[AgentRunner] Timeout - failed to get partial result: {e}")

            for cb in self._on_error:
                await cb(ErrorEvent(message="Task timed out after 10 minutes", step=len(self._step_events)))

            if not self._result_sent:
                self._result_sent = True
                result_output = partial_output or "Task timed out after 10 minutes. No partial results available."
                for cb in self._on_result:
                    await cb(ResultEvent(output=result_output, steps=len(self._step_events), duration_ms=duration_ms))
        except Exception as e:
            logger.error(f"[AgentRunner] Task failed: {e}")
            duration_ms = int((time.time() - self._start_time) * 1000)
            for cb in self._on_error:
                await cb(ErrorEvent(message=str(e), step=len(self._step_events)))
        finally:
            logger.info(f"[AgentRunner] Task finished, _running reset to False")
            self._running = False
            self._agent = None
            # Only close if not in cloud mode (cloud session persists for next command)
            if not browser_use_api_key:
                await browser_session.close()
                self._browser_session = None

    async def cancel(self) -> None:
        if self._input_future and not self._input_future.done():
            self._input_future.cancel()
            self._input_future = None
        if self._agent:
            try:
                self._agent.stop()
            except Exception:
                pass
        self._running = False
        self._agent = None
        self._command_queue.clear()
        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None
        if self._browser_session:
            await self._browser_session.close()
            self._browser_session = None


runner = AgentRunner()