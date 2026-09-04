"""
Redis caching layer for generic responses and greetings in Vaidehi Telegram Bot.
"""
import re
import random
import logging
from typing import Optional
import redis.asyncio as redis

from config import REDIS_URI, REDIS_CACHE_TTL, DM_WINDOW_SECONDS

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


CACHE_HITS: int = 0
CACHE_MISSES: int = 0


async def get_cached_response(user_text: str) -> Optional[str]:
    """Retrieve a random cached response for a generic prompt from Redis."""
    global CACHE_HITS, CACHE_MISSES
    norm = normalize_text(user_text)
    if not norm:
        return None

    if redis_client is None:
        # Fallback to local seed if redis is unavailable
        seed_key = _find_matching_seed_key(norm)
        if seed_key and seed_key in DEFAULT_SEED_RESPONSES:
            CACHE_HITS += 1
            return random.choice(DEFAULT_SEED_RESPONSES[seed_key])
        CACHE_MISSES += 1
        return None

    try:
        key = f"cache:responses:{norm}"
        # Try fetching a random member from Redis set
        res = await redis_client.srandmember(key)
        str_res = _to_str(res)
        if str_res:
            CACHE_HITS += 1
            logger.info("Redis cache HIT for prompt '%s'", norm)
            return str_res

        # Check broader seed key match in Redis
        seed_key = _find_matching_seed_key(norm)
        if seed_key:
            seed_redis_key = f"cache:responses:{seed_key}"
            res = await redis_client.srandmember(seed_redis_key)
            str_seed_res = _to_str(res)
            if str_seed_res:
                CACHE_HITS += 1
                logger.info("Redis cache HIT (seed pattern '%s') for prompt '%s'", seed_key, norm)
                return str_seed_res

    except Exception as e:
        logger.warning("Redis fetch error: %s", e)

    CACHE_MISSES += 1
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


# DM Rate Limit Cache & Messages
DM_EXHAUSTED_MESSAGES = [
    "thodi der baat krte hai ab mai bore hogyi hu 🥱",
    "baad mein aana! aaj mera man nahi ab 🙈",
    "aaj man nhi ab... thodi der mein baat karte hain 💕",
    "ab kitna bologe! mai thak gayi hu, baad mein aana 😴",
    "aaj ka quota khatam ji! 8 ghante baad milte hain Sweetheart 💖",
    "bohot baatein ho gayi, ab mai bore ho gayi hu 🥱 baad mein aana!",
    "bas bas, thodi der ke liye itna hi! baad mein baat krte hai 😴",
]


def get_random_dm_exhausted_message() -> str:
    """Return a random refusal/bored response when DM message limit is reached."""
    return random.choice(DM_EXHAUSTED_MESSAGES)


async def incr_dm_count_redis(user_id: int, ttl: int = DM_WINDOW_SECONDS) -> Optional[int]:
    """Increment user's DM message count in Redis. Sets 8h TTL on initial key creation."""
    if redis_client is None:
        return None
    try:
        key = f"dm_count:{user_id}"
        val = await redis_client.incr(key)
        if val == 1:
            await redis_client.expire(key, ttl)
        return val
    except Exception as e:
        logger.warning("Redis incr_dm_count error: %s", e)
        return None


async def reset_dm_count_redis(user_id: int, set_val: int = 1, ttl: int = DM_WINDOW_SECONDS) -> Optional[int]:
    """Reset user's DM message count in Redis to set_val with a fresh 8h TTL."""
    if redis_client is None:
        return None
    try:
        key = f"dm_count:{user_id}"
        await redis_client.set(key, set_val, ex=ttl)
        return set_val
    except Exception as e:
        logger.warning("Redis reset_dm_count error: %s", e)
        return None


async def get_dm_count_redis(user_id: int) -> Optional[int]:
    """Get user's DM message count from Redis."""
    if redis_client is None:
        return None
    try:
        key = f"dm_count:{user_id}"
        val = await redis_client.get(key)
        if val is not None:
            return int(val)
    except Exception as e:
        logger.warning("Redis get_dm_count error: %s", e)
    return None


# Sticker loading & pool
LOADED_STICKER_IDS: list[str] = []
DEFAULT_STICKERS = [
    "CAACAgIAAxkBAAIBYmO5b...1",
]


async def load_sticker_packs(bot):
    """Fetch sticker file_ids dynamically from configured Telegram sticker set names (e.g. LuKucing)."""
    global LOADED_STICKER_IDS
    from config import STICKER_PACKS
    fetched = []
    for pack in STICKER_PACKS:
        try:
            sticker_set = await bot.get_sticker_set(name=pack)
            if sticker_set and sticker_set.stickers:
                ids = [s.file_id for s in sticker_set.stickers]
                fetched.extend(ids)
                logger.info("Loaded %d stickers from Telegram pack '%s'", len(ids), pack)
        except Exception as e:
            logger.warning("Could not fetch sticker pack '%s': %s", pack, e)

    if fetched:
        # Deduplicate while preserving order
        LOADED_STICKER_IDS = list(dict.fromkeys(fetched))


def get_random_sticker_id() -> Optional[str]:
    """Return a random sticker file_id from loaded pack, configured, or default list."""
    from config import STICKER_FILE_IDS
    pool = LOADED_STICKER_IDS or STICKER_FILE_IDS or DEFAULT_STICKERS
    pool = [s for s in pool if s and s != "CAACAgIAAxkBAAIBYmO5b...1"]
    if pool:
        return random.choice(pool)
    return None


# Local Photos Management (Zero AI API calls for pictures)
import os

PHOTO_DIR = os.path.join(os.path.dirname(__file__), "assets", "photos")

PHOTO_CAPTIONS = [
    "yeh lo meri selfie 🙈 kaisi lag rahi hoon?",
    "aaj ka look ✨ kaisa lag raha hai?",
    "ek cute selfie aapke liye 🥰",
    "dost ne click ki thi kal 💖 kaisa laga?",
    "just took this! batao kaisi hoon? 🙈",
]

PHOTO_KEYWORDS = {
    "pic", "photo", "nude","selfie", "dp", "image", "tasveer", "photu",
    "photos", "pics", "selfies",'nangi'
}

PHOTO_PHRASES = [
    "photo bhejo","nude bhejo", "pic bhejo", "selfie bhejo", "apni pic", "apni photo",
    "apni selfie", "photo dikhao", "pic dikhao", "selfie dikhao", "bhejo pic",
    "bhejo photo", "bhejo selfie", "show pic", "show photo", "send pic",
    "send photo", "send selfie", "dikhaye pic", "dikhaye photo", "picture bhejo"
]


def is_photo_request(text: str) -> bool:
    """Check if the user is requesting a photo/pic/selfie."""
    norm = normalize_text(text)
    if not norm:
        return False
    words = set(norm.split())
    if words.intersection(PHOTO_KEYWORDS):
        return True
    if any(phrase in norm for phrase in PHOTO_PHRASES):
        return True
    return False


def get_random_local_photo() -> Optional[str]:
    """Return absolute path of a random image file from assets/photos/."""
    if not os.path.exists(PHOTO_DIR):
        return None
    valid_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
    files = [
        os.path.join(PHOTO_DIR, f)
        for f in os.listdir(PHOTO_DIR)
        if f.lower().endswith(valid_exts)
    ]
    if files:
        return random.choice(files)
    return None


def get_random_photo_caption() -> str:
    """Return a random caption for photo reply."""
    return random.choice(PHOTO_CAPTIONS)


def get_photo_count() -> int:
    """Return total count of pre-saved photos available on disk."""
    if not os.path.exists(PHOTO_DIR):
        return 0
    valid_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
    return len([f for f in os.listdir(PHOTO_DIR) if f.lower().endswith(valid_exts)])


# Local Voice Notes Management (Zero AI API calls for voice memos)
VOICE_DIR = os.path.join(os.path.dirname(__file__), "assets", "voices")

VOICE_CAPTIONS = [
    "suno na... 🙈",
    "yeh lo meri voice note 🥰",
    "kuch kehna tha tumse ✨",
    "kaisi lagi meri aawaz? 💖",
    "special audio message sirf aapke liye 🙈💕",
]

VOICE_KEYWORDS = {
    "voice", "vn", "audio", "aawaz", "awaz", "bolo", "boliye",
    "gaana", "sunao", "voices", "audios"
}

VOICE_PHRASES = [
    "voice note bhejo", "vn bhejo", "audio bhejo", "apni aawaz sunao",
    "apni awaz sunao", "kuch bolo", "kuch bolo na", "voice bhejo",
    "voice message bhejo", "audio message bhejo", "send voice",
    "send audio", "send vn", "aawaz sunao", "awaz sunao",
    "aawaz sunao na", "awaz sunao na", "bolo na", "bol do na",
    "voice note", "audio note"
]

VOICE_MAP = {
    "hihowareu": "hihowareu.ogg",
    "goodnight": "goodnightiwilltalktoutomorrow.ogg",
    "limit": "ihavealimit.ogg",
    "working": "iamworkingandwhatudo.ogg",
    "busy": "sorryihavebeenbusy.ogg",
    "not_busy": "areunotbusyrightnow.ogg",
    "movie": "plsadvicesomemovie.ogg",
    "like_you": "tobehonestilikeu.ogg",
    "day_plan": "whatrudoingforday.ogg",
    "doing_now": "whatrudoingnow.ogg",
    "yes": "yess.ogg",
}


def is_voice_request(text: str) -> bool:
    """Check if user is asking for a voice note / audio message."""
    norm = normalize_text(text)
    if not norm:
        return False
    words = set(norm.split())
    if words.intersection(VOICE_KEYWORDS):
        if any(phrase in norm for phrase in VOICE_PHRASES):
            return True
        if "voice" in words or "vn" in words or "audio" in words:
            return True
    return False


def get_voice_note_by_name(filename: str) -> Optional[str]:
    """Return path to a specific voice note file if it exists."""
    if not filename:
        return None
    path = os.path.join(VOICE_DIR, filename)
    if os.path.exists(path):
        return path
    return None


def get_random_local_voice_note() -> Optional[str]:
    """Return absolute path of a random voice note file from assets/voices/."""
    if not os.path.exists(VOICE_DIR):
        return None
    valid_exts = (".ogg", ".oga", ".mp3", ".m4a", ".wav")
    files = [
        os.path.join(VOICE_DIR, f)
        for f in os.listdir(VOICE_DIR)
        if f.lower().endswith(valid_exts)
    ]
    if files:
        return random.choice(files)
    return None


def get_voice_for_text(text: str) -> Optional[str]:
    """
    Contextually pick the most appropriate voice note based on the user's message.
    Returns the file path if found, or None.
    """
    norm = normalize_text(text)
    if not norm:
        return None

    # 1. Good Night
    if any(k in norm for k in ("good night", "goodnight", "gn", "so jao", "so rahi", "so rha", "sleep", "shubh ratri", "sweet dreams")):
        return get_voice_note_by_name(VOICE_MAP["goodnight"])

    # 2. Greeting / Hello / Hi
    if is_generic_greeting(norm) or any(k in norm for k in ("hi", "hii", "hiii", "hello", "hey", "heyy", "namaste")):
        return get_voice_note_by_name(VOICE_MAP["hihowareu"])

    # 3. Flirt / Love / Like
    if any(k in norm for k in ("i love you", "i like you", "love u", "like u", "pasand", "pyaar", "crush", "girlfriend", "propose", "cute", "sundar", "dil")):
        return get_voice_note_by_name(VOICE_MAP["like_you"])

    # 4. Movie / Recommendation
    if any(k in norm for k in ("movie", "film", "series", "kya dekhu", "recommend", "cinema", "show", "netflix")):
        return get_voice_note_by_name(VOICE_MAP["movie"])

    # 5. Busy inquiry / Delay
    if any(k in norm for k in ("late reply", "itni der", "kahan thi", "busy thi", "reply nahi", "ignore")):
        return get_voice_note_by_name(VOICE_MAP["busy"])

    # 6. What are you doing today / Day plan
    if any(k in norm for k in ("aaj kya kar", "today plan", "kya plan hai", "what are you doing today", "din kaisa")):
        return get_voice_note_by_name(VOICE_MAP["day_plan"])

    # 7. What are you doing now / Working
    if any(k in norm for k in ("kya kar rahi ho", "kya kr rhi ho", "kya kar rahe ho", "what are you doing", "busy ho kya", "kya kr rhey")):
        # Alternate between working and what are you doing now
        choice = random.choice([VOICE_MAP["working"], VOICE_MAP["doing_now"], VOICE_MAP["not_busy"]])
        return get_voice_note_by_name(choice)

    # 8. Confirmation / Sach mein / Haan
    if norm in ("haan", "ha", "yes", "yess", "sach mein", "sach", "pakka", "really"):
        return get_voice_note_by_name(VOICE_MAP["yes"])

    return None


def get_random_voice_caption() -> str:
    """Return a random flirty caption for voice note reply."""
    return random.choice(VOICE_CAPTIONS)


def get_voice_count() -> int:
    """Return total count of pre-saved voice notes available on disk."""
    if not os.path.exists(VOICE_DIR):
        return 0
    valid_exts = (".ogg", ".oga", ".mp3", ".m4a", ".wav")
    return len([f for f in os.listdir(VOICE_DIR) if f.lower().endswith(valid_exts)])


def get_cache_stats() -> dict:
    """Return cache stats and hit rate calculation for bot status report."""
    total = CACHE_HITS + CACHE_MISSES
    rate = (CACHE_HITS / total * 100) if total > 0 else 0.0
    connected = redis_client is not None
    return {
        "connected": connected,
        "hits": CACHE_HITS,
        "misses": CACHE_MISSES,
        "total": total,
        "hit_rate": f"{rate:.1f}%",
    }






