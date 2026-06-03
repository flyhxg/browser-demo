import json
import re

from browser_use import ChatAnthropic, ChatOpenAI
from browser_use.llm.views import ChatInvokeCompletion

from services.config_store import get_provider_config


class ProviderNotConfiguredError(Exception):
    pass


class ChatOpenAIWithThinkingSupport(ChatOpenAI):
    """Custom ChatOpenAI that handles models which output thinking content before JSON."""

    async def ainvoke(self, messages, output_format=None, **kwargs):
        if output_format is not None:
            result = await super().ainvoke(messages, output_format=None, **kwargs)

            if isinstance(result.completion, str):
                content = result.completion
                json_content = self._extract_json(content)

                try:
                    parsed = output_format.model_validate_json(json_content)
                    return ChatInvokeCompletion(
                        completion=parsed,
                        usage=result.usage,
                        stop_reason=result.stop_reason,
                    )
                except Exception:
                    return result
            else:
                return result
        else:
            return await super().ainvoke(messages, output_format=output_format, **kwargs)

    def _extract_json(self, content: str) -> str:
        """Extract JSON from content that may have thinking text prepended or appended."""
        content = content.strip()

        if content.startswith("```"):
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                return match.group(1).strip()

        start_idx = -1
        for i, char in enumerate(content):
            if char in ('{', '['):
                start_idx = i
                break

        if start_idx == -1:
            return content

        stack = []
        end_idx = len(content)
        for i in range(start_idx, len(content)):
            char = content[i]
            if char in ('{', '['):
                stack.append(char)
            elif char in ('}', ']'):
                if stack:
                    stack.pop()
                    if not stack:
                        end_idx = i + 1
                        break

        return content[start_idx:end_idx]


def create_llm() -> ChatOpenAI | ChatAnthropic:
    config = get_provider_config()
    if not config or not config.get("api_key"):
        raise ProviderNotConfiguredError("API key not configured")

    base_url = config.get("base_url", "https://api.anthropic.com")
    model = config.get("model", "claude-sonnet-4-20250514")
    api_key = config["api_key"]
    protocol = config.get("protocol", "anthropic")

    if protocol == "openai":
        return ChatOpenAIWithThinkingSupport(
            model=model,
            api_key=api_key,
            base_url=base_url,
            dont_force_structured_output=True,
            add_schema_to_system_prompt=True,
            remove_min_items_from_schema=True,
            remove_defaults_from_schema=True,
        )
    else:
        return ChatAnthropic(model=model, api_key=api_key, base_url=base_url)