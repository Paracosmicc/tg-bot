"""
Redis caching layer for generic responses and greetings in Vaidehi Telegram Bot.
"""
import re
import random
import logging
from typing import Optional
import redis.asyncio as redis

from config import REDIS_URI, REDIS_CACHE_TTL

logger = logging.getLogger("cache")

redis_client: Optional[redis.Redis] = None

# Set of common generic greeting & response phrases (normalized)
GENERIC_PATTERNS = {
    # English greetings
    "hi", "hello", "hey", "hii", "hiii", "hiiii", "heyy", "heyyy", "hola",
    "hie", "hlo", "hlw", "helloo", "yo", "wassup", "sup", "whatsup", "whats up",
    "good morning", "good night", "good evening", "good afternoon",
    "gm", "gn", "ge", "how are you", "how r u", "how r you",

    # Hinglish greetings & common generic responses
    "namaste", "namaskar", "kaise ho", "kya haal hai", "kya haal h", "kya hal h",
    "kya hal hai", "kaisa hai", "kaisa h", "kaise ho ji", "kaise ho aap",
    "kya kar rahe ho", "kya kr rhe ho", "kya kr rhi ho", "kya kar rhi ho",
    "kya kr rhey ho", "kya chah rha h", "kya chal raha hai", "kya chal rha hai",
    "aur batao", "aur btao", "aur sunao", "aur bataom", "sab badiya", "sab badhiya",
    "thik hu", "theek hu", "badiya", "badhiya", "mast", "badhiya hu",

    # Short callouts
    "vaidehi", "bot", "hey vaidehi", "hi vaidehi", "hello vaidehi"
}

# Pre-seeded default response variations for instant hits
DEFAULT_SEED_RESPONSES = {
    "hi": [
        "Hii! Kaise ho aap? 🥰",
        "Heyy! Vaidehi is here, bolye na 💖",
        "Hii sweetheart! Kya chal raha hai?",
    ],
    "hello": [
        "Hello ji! Kaise yaad kiya aaj? ✨",
        "Hello! Kaise ho aap?",
        "Hii hello! Subah se aapka hi intezar tha 😉",
    ],
    "hey": [
        "Heyy! Kaise ho?",
        "Hey cutie! Kya chal raha hai?",
        "Hey! Vaidehi ko yaad kiya? 💕",
    ],
    "kaise ho": [
        "Main ekdam mast hoon! Aap batao, kya chal raha hai? 😊",
        "Ekdam badiya! Aap batao aapka din kaisa gaya? ✨",
        "Main toh badiya hoon, aap batao kaise ho? 💕",
    ],
    "namaste": [
        "Namaste ji! Kaise hain aap? 🙏✨",
        "Namaste! Aapka swagat hai 😊",
    ],
    "gm": [
        "Good morning ji! Have a lovely day ☀️💕",
        "Good morning cutie! Chai peeli kya? ☕✨",
    ],
    "gn": [
        "Good night! Meethe sapne dekhna 😴✨",
        "Good night ji! Kal milte hain 💕",
    ]
}


async def init_redis():
    """Initialize Redis async client."""
    global redis_client
    if not REDIS_URI:
        logger.warning("REDIS_URI is not set. Redis caching will be disabled.")
        return

    if redis_client is None:
        try:
            redis_client = redis.from_url(
                REDIS_URI,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
            await redis_client.ping()
            logger.info("Successfully connected to Redis Cloud server.")

            # Seed default responses if missing
            await _seed_defaults_if_empty()
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            redis_client = None


async def close_redis():
    """Close Redis client connection."""
    global redis_client
    if redis_client is not None:
        try:
            await redis_client.close()
            logger.info("Redis connection closed.")
        except Exception as e:
            logger.error("Error closing Redis connection: %s", e)
        finally:
            redis_client = None


def normalize_text(text: str) -> str:
    """Normalize input text: lowercasing, stripping punctuation, emojis, and whitespace."""
    if not text:
        return ""
    # Lowercase
    cleaned = text.lower().strip()
    # Remove common punctuation & trailing symbols
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def is_generic_greeting(text: str) -> bool:
    """Check if normalized message text is a generic response or greeting."""
    norm = normalize_text(text)
    if not norm:
        return False
    if norm in GENERIC_PATTERNS:
        return True
    # Also check if text matches a repeat sequence of generic characters like "hiiii", "heyyyy"
    if re.match(r"^h+i+$", norm) or re.match(r"^h+e+y+$", norm) or re.match(r"^h+e+l+o+$", norm):
        return True
    return False


def _to_str(val: object) -> Optional[str]:
    """Helper to convert Redis return types (str | bytes | list) safely to str."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, bytes):
        return val.decode("utf-8")
    if isinstance(val, list) and len(val) > 0:
        return _to_str(val[0])
    return str(val)


async def get_cached_response(user_text: str) -> Optional[str]:
    """Retrieve a random cached response for a generic prompt from Redis."""
    norm = normalize_text(user_text)
    if not norm:
        return None

    if redis_client is None:
        # Fallback to local seed if redis is unavailable
        seed_key = _find_matching_seed_key(norm)
        if seed_key and seed_key in DEFAULT_SEED_RESPONSES:
            return random.choice(DEFAULT_SEED_RESPONSES[seed_key])
        return None

    try:
        key = f"cache:responses:{norm}"
        # Try fetching a random member from Redis set
        res = await redis_client.srandmember(key)
        str_res = _to_str(res)
        if str_res:
            logger.info("Redis cache HIT for prompt '%s'", norm)
            return str_res

        # Check broader seed key match in Redis
        seed_key = _find_matching_seed_key(norm)
        if seed_key:
            seed_redis_key = f"cache:responses:{seed_key}"
            res = await redis_client.srandmember(seed_redis_key)
            str_seed_res = _to_str(res)
            if str_seed_res:
                logger.info("Redis cache HIT (seed pattern '%s') for prompt '%s'", seed_key, norm)
                return str_seed_res

    except Exception as e:
        logger.warning("Redis fetch error: %s", e)

    return None


async def set_cached_response(user_text: str, response: str, ttl: int = REDIS_CACHE_TTL):
    """Store a generated response into Redis cache set for generic prompt."""
    norm = normalize_text(user_text)
    if not norm or not response:
        return

    if redis_client is None:
        return

    try:
        key = f"cache:responses:{norm}"
        await redis_client.sadd(key, response)
        await redis_client.expire(key, ttl)
        logger.info("Cached new response for prompt '%s' in Redis (TTL: %ds)", norm, ttl)
    except Exception as e:
        logger.warning("Redis store error: %s", e)


def _find_matching_seed_key(norm: str) -> Optional[str]:
    """Find closest matching seed category key for normalized string."""
    if norm in DEFAULT_SEED_RESPONSES:
        return norm
    if re.match(r"^h+i+$", norm) or norm in ("hii", "hiii", "hiiii", "hie", "hlo", "hlw"):
        return "hi"
    if re.match(r"^h+e+y+$", norm) or norm in ("heyy", "heyyy"):
        return "hey"
    if re.match(r"^h+e+l+o+$", norm) or norm in ("helloo", "hola"):
        return "hello"
    if "kaise ho" in norm or "kya hal" in norm or "kya haal" in norm:
        return "kaise ho"
    if "namaste" in norm or "namaskar" in norm:
        return "namaste"
    if norm in ("gm", "good morning"):
        return "gm"
    if norm in ("gn", "good night"):
        return "gn"
    return None


async def _seed_defaults_if_empty():
    """Seed initial default response pools into Redis if keys do not exist."""
    if redis_client is None:
        return
    try:
        for prompt, resp_list in DEFAULT_SEED_RESPONSES.items():
            key = f"cache:responses:{prompt}"
            exists = await redis_client.exists(key)
            if not exists:
                await redis_client.sadd(key, *resp_list)
                await redis_client.expire(key, REDIS_CACHE_TTL)
                logger.info("Seeded Redis cache key '%s'", key)
    except Exception as e:
        logger.warning("Error seeding Redis default responses: %s", e)
