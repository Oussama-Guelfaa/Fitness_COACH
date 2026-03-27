"""Abstract LLM interface — swap providers without touching business logic."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMMessage:
    """A single message in a chat completion request."""
    role: str  # system, user, assistant
    content: str


@dataclass
class LLMResponse:
    """Response from the LLM."""
    content: str
    model: str = ""
    usage: dict | None = None


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def chat(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """Send a chat completion request and return the response."""
        ...

    @abstractmethod
    async def close(self):
        """Clean up resources."""
        ...

