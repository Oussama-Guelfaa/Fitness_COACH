"""Ollama LLM provider — uses the Ollama REST API (OpenAI-compatible)."""

import httpx
import structlog

from llm.base import BaseLLMProvider, LLMMessage, LLMResponse
from config.settings import LLMSettings

logger = structlog.get_logger()


class OllamaProvider(BaseLLMProvider):
    """LLM provider using Ollama's OpenAI-compatible /v1/chat/completions."""

    def __init__(self, settings: LLMSettings):
        self.settings = settings
        self.base_url = settings.base_url.rstrip("/")
        self.model = settings.model
        self.client = httpx.AsyncClient(timeout=120.0)

    def _chat_url(self) -> str:
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    async def chat(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """Send chat request to Ollama."""
        url = self._chat_url()
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", self.settings.temperature),
            "max_tokens": kwargs.get("max_tokens", self.settings.max_tokens),
            "stream": False,
        }
        headers = {}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"

        try:
            resp = await self.client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return LLMResponse(
                content=content,
                model=data.get("model", self.model),
                usage=data.get("usage"),
            )
        except httpx.HTTPStatusError as e:
            logger.error("LLM HTTP error", status=e.response.status_code, body=e.response.text)
            raise
        except Exception as e:
            logger.error("LLM request failed", error=str(e))
            raise

    async def close(self):
        await self.client.aclose()


class OpenAICompatibleProvider(BaseLLMProvider):
    """Generic OpenAI-compatible provider (works with OpenAI, Groq, Mistral, etc.)."""

    def __init__(self, settings: LLMSettings):
        self.settings = settings
        self.base_url = settings.base_url.rstrip("/")
        self.model = settings.model
        self.client = httpx.AsyncClient(timeout=120.0)

    def _chat_url(self) -> str:
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    async def chat(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        url = self._chat_url()
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", self.settings.temperature),
            "max_tokens": kwargs.get("max_tokens", self.settings.max_tokens),
        }
        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        resp = await self.client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self.model),
            usage=data.get("usage"),
        )

    async def close(self):
        await self.client.aclose()


def create_llm_provider(settings: LLMSettings) -> BaseLLMProvider:
    """Factory function to create the appropriate LLM provider."""
    provider_map = {
        "ollama": OllamaProvider,
        "openai": OpenAICompatibleProvider,
        "groq": OpenAICompatibleProvider,
        "mistral": OpenAICompatibleProvider,
    }
    provider_class = provider_map.get(settings.provider, OllamaProvider)
    logger.info("Creating LLM provider", provider=settings.provider, model=settings.model)
    return provider_class(settings)
