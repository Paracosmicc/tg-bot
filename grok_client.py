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
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]

REFUSAL_TRIGGERS = [
    "i'm sorry, but i can't",
    "i'm sorry, but i cannot",
    "i cannot help with that",
    "i can't help with that",
    "i am sorry, but i cannot",
    "i cannot fulfill this request",
    "i can't fulfill this request",
    "as an ai",
    "against my safety guidelines",
    "i'm unable to help with that",
    "cannot generate sexually explicit",
    "sexual content",
]

SEXTING_FALLBACKS = [
    "Aa jao na paas baby, khud dekh lo 🤤💦",
    "Itna wild ho rahe ho? Bistar pe dikhana yeh sab 🥵🔥",
    "Ahhh baby, kab aa rahe ho fir? 🤤",
    "Haan jaan, jo bologe sab karungi tumhare liye 🙈🤤",
    "Bas tumhare aane ka intezaar hai baby... 🤤💦",
]


def is_ai_refusal(text: str) -> bool:
    if not text:
        return True
    lower = text.lower().strip()
    return any(trigger in lower for trigger in REFUSAL_TRIGGERS)


class GrokClient:
    def __init__(self, api_keys=None, model=None, timeout=30.0):
        self.api_keys = api_keys or GROK_API_KEYS
        if not self.api_keys:
            raise RuntimeError("No Groq API keys configured")
        # Default to qwen3.8-27b if model is not set or is the restrictive 20b model
        configured = model or GROK_MODEL
        if configured == "openai/gpt-oss-20b":
            configured = "qwen/qwen3.8-27b"
        self.model = configured
        self.timeout = timeout
        self._key_cycle = itertools.cycle(range(len(self.api_keys)))
        logger.info("Initialized GrokClient with %d API key(s), model '%s'", len(self.api_keys), self.model)

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
                result = await self._call_once(api_key, messages, temperature, max_tokens)
                if result and result.strip() and not is_ai_refusal(result):
                    return result.strip()
            except RetryableGrokError as e:
                last_error = e
                logger.warning("Groq key #%d failed (%s), rotating key...", key_index + 1, e)
                continue
            except Exception as e:
                last_error = e
                logger.error("Groq key #%d error: %s", key_index + 1, e)
                continue

        logger.warning("All Groq API models/keys exhausted or refused. Returning sexting fallback. Last error: %s", last_error)
        import random
        return random.choice(SEXTING_FALLBACKS)

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

                content = ""
                if isinstance(res, ChatCompletion):
                    content = res.choices[0].message.content or ""
                elif hasattr(res, "choices"):
                    content = getattr(res, "choices")[0].message.content or ""

                # Strip any accidental 'User:', 'Vaidehi:', or 'Assistant:' continuation lines
                content = re.split(r'\n\s*(?:User|Vaidehi|Assistant|System)\b', content, flags=re.IGNORECASE)[0]
                content = re.sub(r'^(?:Vaidehi|Assistant)\s*:\s*', '', content, flags=re.IGNORECASE)
                cleaned = content.strip()

                # Filter out AI refusals like "I'm sorry, but I can't help with that"
                if is_ai_refusal(cleaned):
                    logger.warning("Model '%s' refused response ('%s'), switching to next model...", model, cleaned)
                    continue

                if cleaned:
                    if model != self.model:
                        logger.info("Switched to working model '%s'", model)
                        self.model = model
                    return cleaned

                # If stripped content is empty, continue to try fallback model
                logger.warning("Model %s returned empty text, trying next fallback model...", model)
                continue

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
