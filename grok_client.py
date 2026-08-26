"""
Client wrapper around Groq Cloud API with key rotation and fallback models.
"""
import itertools
import logging
import re
from groq import AsyncGroq, APIError, AuthenticationError, RateLimitError
from groq.types.chat import ChatCompletion


from config import GROK_API_KEYS, GROK_MODEL

from typing import Any, List, Dict

logger = logging.getLogger("grok_client")

FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "groq/compound-mini",
]


class GrokClient:
    def __init__(self, api_keys=None, model=None, timeout=30.0):
        self.api_keys = api_keys or GROK_API_KEYS
        if not self.api_keys:
            raise RuntimeError("No Groq API keys configured")
        self.model = model or GROK_MODEL
        self.timeout = timeout
        self._key_cycle = itertools.cycle(range(len(self.api_keys)))

    def _next_key_index(self):
        return next(self._key_cycle)

    async def generate(self, messages: Any, temperature: float = 0.9, max_tokens: int = 400) -> str:
        last_error = None
        attempts = len(self.api_keys)
        start_index = self._next_key_index()

        for offset in range(attempts):
            key_index = (start_index + offset) % len(self.api_keys)
            api_key = self.api_keys[key_index]
            try:
                return await self._call_once(api_key, messages, temperature, max_tokens)
            except RetryableGrokError as e:
                last_error = e
                logger.warning("Groq key #%d failed (%s), rotating key...", key_index + 1, e)
                continue
            except Exception as e:
                last_error = e
                logger.error("Groq key #%d error: %s", key_index + 1, e)
                continue

        raise RuntimeError(f"All Groq API keys failed. Last error: {last_error}")

    async def _call_once(self, api_key: str, messages: Any, temperature: float, max_tokens: int) -> str:
        client = AsyncGroq(api_key=api_key, timeout=self.timeout)

        models_to_try = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]

        for model in models_to_try:
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_completion_tokens": max_tokens,
                    "stop": ["\nUser:", "\nUser ", "\nVaidehi:", "\nAssistant:"],
                    "stream": False,
                }
                res = await client.chat.completions.create(**kwargs)

                if model != self.model:
                    logger.info("Using fallback model '%s'", model)
                    self.model = model

                content = ""
                if isinstance(res, ChatCompletion):
                    content = res.choices[0].message.content or ""
                elif hasattr(res, "choices"):
                    content = getattr(res, "choices")[0].message.content or ""

                # Strip any accidental 'User:', 'Vaidehi:', or 'Assistant:' continuation lines
                content = re.split(r'\n\s*(?:User|Vaidehi|Assistant|System)\b', content, flags=re.IGNORECASE)[0]
                content = re.sub(r'^(?:Vaidehi|Assistant)\s*:\s*', '', content, flags=re.IGNORECASE)
                return content.strip()


            except AuthenticationError as e:
                raise RetryableGrokError(f"Authentication error: {e}")
            except RateLimitError as e:
                raise RetryableGrokError(f"Rate limit error: {e}")
            except APIError as e:
                if "model_not_found" in str(e) or "decommissioned" in str(e):
                    continue
                raise RetryableGrokError(f"Groq API Error: {e}")
            except Exception as e:
                raise RetryableGrokError(f"Unexpected error: {e}")

        raise RetryableGrokError("No working Groq models found for key")


class RetryableGrokError(Exception):
    """Raised when a key-specific failure occurs and rotation should be attempted."""
    pass
