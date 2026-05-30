import asyncio
import time
from dataclasses import dataclass, field

from browser_use import Agent, BrowserProfile, BrowserSession

from services.config_store import get_config
from services.llm_factory import ProviderNotConfiguredError, create_llm


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


class AgentRunner:
    def __init__(self) -> None:
        self._agent: Agent | None = None
        self._running = False
        self._step_events: list[StepEvent] = []
        self._start_time: float = 0
        self._on_step: list[object] = []  # callbacks set by ws layer
        self._on_result: list[object] = []
        self._on_error: list[object] = []

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

    async def run(self, task: str, provider: str) -> None:
        if self._running:
            raise RuntimeError("A task is already running")

        self._running = True
        self._step_events = []
        self._start_time = time.time()

        try:
            llm = create_llm(provider)
        except (ProviderNotConfiguredError, ValueError) as e:
            self._running = False
            for cb in self._on_error:
                await cb(ErrorEvent(message=str(e), step=0))
            return

        config = get_config()
        browser_config = config.get("browser", {})
        browser_mode = browser_config.get("mode", "local")

        if browser_mode == "cloud":
            browser_profile = BrowserProfile(use_cloud=True)
            browser_session = BrowserSession(browser_profile=browser_profile)
        else:
            browser_session = BrowserSession()

        async def step_callback(browser_state, agent_output, step_number):
            action_desc = ""
            target_desc = ""
            if agent_output and agent_output.action:
                first_action = agent_output.action[0]
                action_dict = first_action.model_dump() if hasattr(first_action, "model_dump") else {}
                action_name = next(iter(action_dict), "unknown")
                action_desc = action_name
                action_params = action_dict.get(action_name, {})
                target_desc = action_params.get("index", "") or action_params.get("url", "") or ""

            screenshot = browser_state.screenshot if browser_state else None

            event = StepEvent(
                step=step_number,
                action=action_desc,
                target=str(target_desc),
                status="running",
                screenshot=screenshot,
            )
            self._step_events.append(event)
            for cb in self._on_step:
                await cb(event)

        async def done_callback(history):
            duration_ms = int((time.time() - self._start_time) * 1000)
            output = history.final_result() or ""
            steps = history.number_of_steps()

            result = ResultEvent(output=str(output), steps=steps, duration_ms=duration_ms)
            for cb in self._on_result:
                await cb(result)

            self._running = False

        try:
            self._agent = Agent(
                task=task,
                llm=llm,
                browser_session=browser_session,
                register_new_step_callback=step_callback,
                register_done_callback=done_callback,
            )
            await self._agent.run()
        except Exception as e:
            duration_ms = int((time.time() - self._start_time) * 1000)
            for cb in self._on_error:
                await cb(ErrorEvent(message=str(e), step=len(self._step_events)))
            self._running = False
        finally:
            self._agent = None

    async def cancel(self) -> None:
        if self._agent:
            self._agent.stop()
            self._running = False


runner = AgentRunner()
