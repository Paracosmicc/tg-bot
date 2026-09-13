"""
MongoDB data access layer using Motor (async driver for pymongo).
"""
import logging
from datetime import datetime, timezone
import motor.motor_asyncio

import certifi
from pymongo import ReturnDocument

from typing import Any

from config import MONGODB_URI, MONGODB_DB_NAME, MAX_HISTORY_MESSAGES, DM_MESSAGE_LIMIT, DM_WINDOW_SECONDS
import cache

logger = logging.getLogger("db")

client: motor.motor_asyncio.AsyncIOMotorClient | None = None
db: Any = None


async def init_db():
    """Initialize MongoDB client and create indexes if needed."""
    global client, db
    if client is None:
        try:
            client = motor.motor_asyncio.AsyncIOMotorClient(
                MONGODB_URI,
                tlsCAFile=certifi.where()
            )
        except Exception:
            client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
        db = client[MONGODB_DB_NAME]


        # Create indexes asynchronously
        try:
            await db.messages.create_index([("chat_id", 1), ("created_at", -1)])
            await db.couples.create_index([("chat_id", 1), ("is_active", 1), ("love_score", -1)])
            await db.group_members.create_index([("chat_id", 1)])
            await db.dm_counts.create_index([("user_id", 1), ("date", 1)])
            await db.premium_users.create_index([("user_id", 1)])
            await db.premium_users.create_index([("is_active", 1), ("premium_expires_at", -1)])
        except Exception as e:
            logger.warning("MongoDB index creation warning: %s", e)



async def close_db():
    global client
    if client is not None:
        client.close()
        client = None


# ---------- users / groups ----------

async def upsert_user(user_id: int, username: str | None, first_name: str | None):
    await init_db()
    display_name = first_name or (f"@{username.lstrip('@')}" if username else str(user_id))
    await db.users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "display_name": display_name,
                "username": username,
                "first_name": first_name,
            },
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )
    # If user exists in premium_users collection, keep display_name up to date
    await db.premium_users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "display_name": display_name,
                "username": username,
                "first_name": first_name,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )


async def upsert_group(chat_id: int, title: str | None):
    await init_db()
    await db.groups.update_one(
        {"_id": chat_id},
        {
            "$set": {
                "chat_id": chat_id,
                "title": title,
            },
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )


async def get_all_groups() -> list[dict]:
    await init_db()
    cursor = db.groups.find({})
    groups = await cursor.to_list(length=10000)
    return groups


async def get_all_users() -> list[dict]:
    await init_db()
    cursor = db.users.find({})
    users = await cursor.to_list(length=50000)
    return users


async def get_all_users_detailed(limit: int = 10000) -> list[dict]:
    """Returns detailed user records formatted for dashboard and admin panels."""
    await init_db()
    cursor = db.users.find({}).sort("created_at", -1).limit(limit)
    users = await cursor.to_list(length=limit)
    res = []
    now = datetime.now(timezone.utc)
    for u in users:
        uid = u.get("user_id") or u.get("_id")
        if not isinstance(uid, int):
            continue
        is_prem = bool(u.get("is_premium", False))
        expires_at = u.get("premium_expires_at")
        if expires_at:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now > expires_at:
                is_prem = False

        res.append({
            "user_id": uid,
            "display_name": u.get("display_name") or u.get("first_name") or str(uid),
            "username": u.get("username"),
            "first_name": u.get("first_name"),
            "is_premium": is_prem,
            "coins": int(u.get("coins", 0)),
            "referral_count": int(u.get("referral_count", 0)),
            "persona_mode": u.get("persona_mode", "flirty"),
            "premium_expires_at": expires_at.isoformat() if expires_at else None,
            "created_at": u.get("created_at").isoformat() if u.get("created_at") else None,
        })
    return res


async def get_all_user_ids() -> list[int]:
    await init_db()
    cursor = db.users.find({}, {"_id": 1, "user_id": 1})
    docs = await cursor.to_list(length=50000)
    user_ids = []
    for d in docs:
        uid = d.get("user_id") or d.get("_id")
        if uid is not None and isinstance(uid, int):
            user_ids.append(uid)
    return list(dict.fromkeys(user_ids))


async def get_all_group_ids() -> list[int]:
    await init_db()
    cursor = db.groups.find({}, {"_id": 1, "chat_id": 1})
    docs = await cursor.to_list(length=10000)
    group_ids = []
    for d in docs:
        gid = d.get("chat_id") or d.get("_id")
        if gid is not None and isinstance(gid, int):
            group_ids.append(gid)
    return list(dict.fromkeys(group_ids))


async def track_group_member(chat_id: int, user_id: int):
    await init_db()
    doc_id = f"{chat_id}_{user_id}"
    await db.group_members.update_one(
        {"_id": doc_id},
        {
            "$set": {
                "chat_id": chat_id,
                "user_id": user_id,
                "last_seen": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


async def get_group_member_ids(chat_id: int) -> list[int]:
    await init_db()
    cursor = db.group_members.find({"chat_id": chat_id}, {"user_id": 1})
    members = await cursor.to_list(length=1000)
    return [m["user_id"] for m in members if "user_id" in m]


async def get_username(user_id: int) -> str:
    await init_db()
    user = await db.users.find_one({"_id": user_id})
    if user:
        return user.get("first_name") or user.get("username") or str(user_id)
    return str(user_id)


async def get_user_tag(user_id: int) -> str:
    await init_db()
    user = await db.users.find_one({"_id": user_id})
    if user:
        username = user.get("username")
        if username and username.strip():
            u = username.strip()
            return u if u.startswith("@") else f"@{u}"
        first_name = user.get("first_name")
        if first_name and first_name.strip():
            return first_name.strip()
    return str(user_id)


# ---------- messages / memory ----------

async def save_message(chat_id: int, user_id: int | None, role: str, content: str):
    await init_db()
    await db.messages.insert_one(
        {
            "chat_id": chat_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def get_recent_context(chat_id: int, limit: int = MAX_HISTORY_MESSAGES) -> list[dict]:
    """Returns oldest-to-newest list of {"role", "content"} for building prompt context."""
    await init_db()
    cursor = db.messages.find({"chat_id": chat_id}).sort("created_at", -1).limit(limit)
    messages = await cursor.to_list(length=limit)
    return [{"role": m["role"], "content": m["content"]} for m in reversed(messages)]


async def semantic_search(chat_id: int, query: str, top_k: int = 5) -> list[str]:
    await init_db()
    cursor = db.messages.find({"chat_id": chat_id}).sort("created_at", -1).limit(top_k)
    messages = await cursor.to_list(length=top_k)
    return [m["content"] for m in messages]


# ---------- couples / group games ----------

async def get_active_couple(chat_id: int, max_age_seconds: int = 86400):
    await init_db()
    couple = await db.couples.find_one(
        {"chat_id": chat_id, "is_active": True},
        sort=[("created_at", -1)],
    )
    if not couple:
        return None

    created_at = couple.get("created_at")
    if created_at:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if (now - created_at).total_seconds() >= max_age_seconds:
            # Couple is older than 24 hours! Auto-expire this couple
            await db.couples.update_one(
                {"_id": couple["_id"]},
                {"$set": {"is_active": False, "expired_at": now}},
            )
            return None

    return {
        "id": str(couple["_id"]),
        "user_id_1": couple["user_id_1"],
        "user_id_2": couple["user_id_2"],
        "love_score": couple["love_score"],
    }


async def create_couple(chat_id: int, user_id_1: int, user_id_2: int, love_score: int):
    await init_db()
    now = datetime.now(timezone.utc)
    # Deactivate previous active couples for this group
    await db.couples.update_many(
        {"chat_id": chat_id, "is_active": True},
        {"$set": {"is_active": False, "expired_at": now}}
    )
    await db.couples.insert_one(
        {
            "chat_id": chat_id,
            "user_id_1": user_id_1,
            "user_id_2": user_id_2,
            "love_score": love_score,
            "is_active": True,
            "created_at": now,
        }
    )
    for uid in (user_id_1, user_id_2):
        doc_id = f"{chat_id}_{uid}"
        await db.love_stats.update_one(
            {"_id": doc_id},
            {
                "$inc": {"times_matched": 1},
                "$setOnInsert": {
                    "chat_id": chat_id,
                    "user_id": uid,
                    "times_broken_up": 0,
                    "compliments_received": 0,
                    "roasts_received": 0,
                },
            },
            upsert=True,
        )


async def break_up_top_couple(chat_id: int) -> bool:
    await init_db()
    couple = await db.couples.find_one(
        {"chat_id": chat_id, "is_active": True},
        sort=[("love_score", -1)],
    )
    if not couple:
        return False

    await db.couples.update_one(
        {"_id": couple["_id"]},
        {"$set": {"is_active": False, "broken_up_at": datetime.now(timezone.utc)}},
    )
    for uid in (couple["user_id_1"], couple["user_id_2"]):
        doc_id = f"{chat_id}_{uid}"
        await db.love_stats.update_one(
            {"_id": doc_id},
            {
                "$inc": {"times_broken_up": 1},
                "$setOnInsert": {
                    "chat_id": chat_id,
                    "user_id": uid,
                    "times_matched": 0,
                    "compliments_received": 0,
                    "roasts_received": 0,
                },
            },
            upsert=True,
        )
    return True


async def get_loveboard(chat_id: int, limit: int = 5) -> list[dict]:
    await init_db()
    cursor = db.couples.find(
        {"chat_id": chat_id, "is_active": True}
    ).sort("love_score", -1).limit(limit)
    couples = await cursor.to_list(length=limit)
    return [
        {
            "user_id_1": c["user_id_1"],
            "user_id_2": c["user_id_2"],
            "love_score": c["love_score"],
        }
        for c in couples
    ]


async def get_love_stats(chat_id: int, user_id: int) -> dict:
    await init_db()
    doc_id = f"{chat_id}_{user_id}"
    stat = await db.love_stats.find_one({"_id": doc_id})
    if not stat:
        return {"times_matched": 0, "times_broken_up": 0, "compliments_received": 0, "roasts_received": 0}
    return {
        "times_matched": stat.get("times_matched", 0),
        "times_broken_up": stat.get("times_broken_up", 0),
        "compliments_received": stat.get("compliments_received", 0),
        "roasts_received": stat.get("roasts_received", 0),
    }


async def bump_compliment(chat_id: int, user_id: int):
    await _bump_stat(chat_id, user_id, "compliments_received")


async def bump_roast(chat_id: int, user_id: int):
    await _bump_stat(chat_id, user_id, "roasts_received")


async def _bump_stat(chat_id: int, user_id: int, field: str):
    await init_db()
    doc_id = f"{chat_id}_{user_id}"
    await db.love_stats.update_one(
        {"_id": doc_id},
        {
            "$inc": {field: 1},
            "$setOnInsert": {
                "chat_id": chat_id,
                "user_id": user_id,
                "times_matched": 0,
                "times_broken_up": 0,
                "compliments_received": 0,
                "roasts_received": 0,
            },
        },
        upsert=True,
    )


# ---------- VIP / Premium ----------

async def is_user_premium(user_id: int) -> bool:
    """Checks whether the given user has an active VIP/Premium status."""
    from config import ADMIN_USER_IDS
    if user_id in ADMIN_USER_IDS:
        return True

    await init_db()
    user = await db.users.find_one({"_id": user_id})
    if not user or not user.get("is_premium"):
        return False

    expires_at = user.get("premium_expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            # Expired
            await db.users.update_one(
                {"_id": user_id},
                {"$set": {"is_premium": False}}
            )
            await db.premium_users.update_one(
                {"user_id": user_id},
                {"$set": {"is_active": False}}
            )
            return False
    return True


async def set_user_premium(
    user_id: int,
    duration_days: int | None = 30,
    charge_id: str | None = None,
    stars_amount: int = 50,
) -> bool:
    """Grants VIP / Premium status to a user for duration_days (default 30 days / 1 month, or permanent if None).
    Saves to both 'users' and dedicated 'premium_users' collection with display_name.
    """
    await init_db()
    now = datetime.now(timezone.utc)
    expires_at = None
    if duration_days is not None:
        from datetime import timedelta
        expires_at = now + timedelta(days=duration_days)

    payment_record = {
        "charge_id": charge_id,
        "stars_amount": stars_amount,
        "paid_at": now,
        "expires_at": expires_at,
    }

    # Fetch existing user details for display_name
    user_doc = await db.users.find_one({"_id": user_id})
    first_name = user_doc.get("first_name") if user_doc else None
    username = user_doc.get("username") if user_doc else None
    display_name = first_name or (f"@{username.lstrip('@')}" if username else str(user_id))
    persona_mode = user_doc.get("persona_mode", "flirty") if user_doc else "flirty"

    # 1. Update in 'users' collection
    await db.users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "is_premium": True,
                "display_name": display_name,
                "premium_since": now,
                "premium_expires_at": expires_at,
            },
            "$push": {
                "payment_history": payment_record
            },
        },
        upsert=True,
    )

    # 2. Save in dedicated 'premium_users' collection
    await db.premium_users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "display_name": display_name,
                "username": username,
                "first_name": first_name,
                "is_active": True,
                "persona_mode": persona_mode,
                "premium_since": now,
                "premium_expires_at": expires_at,
                "last_charge_id": charge_id,
                "updated_at": now,
            },
            "$push": {
                "payment_history": payment_record
            },
        },
        upsert=True,
    )
    return True


async def revoke_user_premium(user_id: int) -> bool:
    """Revokes VIP/Premium status from a user."""
    await init_db()
    await db.users.update_one({"_id": user_id}, {"$set": {"is_premium": False}})
    await db.premium_users.update_one({"_id": user_id}, {"$set": {"is_active": False}})
    return True


async def get_premium_info(user_id: int) -> dict:
    """Returns premium details for the user."""
    await init_db()
    user = await db.users.find_one({"_id": user_id})
    if not user:
        return {"is_premium": False, "expires_at": None, "since": None}

    is_prem = await is_user_premium(user_id)
    return {
        "is_premium": is_prem,
        "expires_at": user.get("premium_expires_at") if is_prem else None,
        "since": user.get("premium_since") if is_prem else None,
    }


async def set_user_mode(user_id: int, mode: str) -> bool:
    """Sets the persona mode for a VIP user ('flirty', 'sweet', 'savage', 'adult'). Only allowed if user is active VIP."""
    await init_db()
    if not await is_user_premium(user_id):
        return False
    normalized_mode = mode.lower().strip()
    if normalized_mode not in ("flirty", "sweet", "savage", "adult"):
        normalized_mode = "flirty"
    await db.users.update_one(
        {"_id": user_id},
        {"$set": {"persona_mode": normalized_mode}},
        upsert=True,
    )
    await db.premium_users.update_one(
        {"_id": user_id},
        {"$set": {"persona_mode": normalized_mode, "updated_at": datetime.now(timezone.utc)}},
    )
    return True


async def get_user_mode(user_id: int) -> str:
    """Gets the active persona mode for the user. Only active VIP users get custom modes; free users always get default 'flirty'."""
    await init_db()
    if not await is_user_premium(user_id):
        return "flirty"
    user = await db.users.find_one({"_id": user_id})
    if user and user.get("persona_mode"):
        return user["persona_mode"]
    return "flirty"


async def get_all_premium_users() -> list[dict]:
    """Returns all records from the dedicated premium_users collection."""
    await init_db()
    cursor = db.premium_users.find({}).sort("premium_since", -1)
    return await cursor.to_list(length=5000)


# ---------- DM AI Rate Limits ----------

async def increment_and_check_dm_limit(user_id: int, limit: int = DM_MESSAGE_LIMIT, window_seconds: int = DM_WINDOW_SECONDS) -> tuple[int, bool, int]:
    """Increment DM AI API call count for user_id and automatically reset every 8 hours (28800 seconds).
    Returns (current_count, is_exceeded, remaining_seconds).
    VIP/Premium users and Group chats are exempt and have unlimited AI calls. Zero-cost actions (stickers, cached replies) do not consume this limit.
    """
    # Premium users have unlimited DMs with zero cooldowns
    if await is_user_premium(user_id):
        return 0, False, 0

    await init_db()
    now = datetime.now(timezone.utc)
    doc = await db.dm_counts.find_one({"_id": user_id})

    if not doc or "first_msg_at" not in doc:
        # First message in DM for this user
        current_cnt = 1
        await db.dm_counts.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "count": 1,
                    "first_msg_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )
        await cache.reset_dm_count_redis(user_id, set_val=1, ttl=window_seconds)
        remaining_seconds = window_seconds
    else:
        first_msg_at = doc.get("first_msg_at")
        if first_msg_at and first_msg_at.tzinfo is None:
            first_msg_at = first_msg_at.replace(tzinfo=timezone.utc)

        elapsed = (now - first_msg_at).total_seconds() if first_msg_at else window_seconds + 1

        if elapsed >= window_seconds:
            # 8 hours have passed! Automatically reset limit for this user & start a new 8h window
            current_cnt = 1
            await db.dm_counts.update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "count": 1,
                        "first_msg_at": now,
                        "updated_at": now,
                    }
                },
            )
            await cache.reset_dm_count_redis(user_id, set_val=1, ttl=window_seconds)
            remaining_seconds = window_seconds
        else:
            # Within the 8-hour window: increment count
            db_cnt = doc.get("count", 0) + 1
            remaining_ttl = max(1, int(window_seconds - elapsed))
            await db.dm_counts.update_one(
                {"_id": user_id},
                {
                    "$set": {"count": db_cnt, "updated_at": now},
                },
            )
            await cache.reset_dm_count_redis(user_id, set_val=db_cnt, ttl=remaining_ttl)
            current_cnt = db_cnt
            remaining_seconds = remaining_ttl

    is_exceeded = current_cnt > limit
    return current_cnt, is_exceeded, remaining_seconds


async def get_user_quota_info(user_id: int, limit: int = DM_MESSAGE_LIMIT, window_seconds: int = DM_WINDOW_SECONDS) -> dict:
    """Get current quota details for a user: used count, limit, remaining seconds until reset, is_vip, and total messages sent."""
    await init_db()
    is_vip = await is_user_premium(user_id)
    total_messages = await db.messages.count_documents({"user_id": user_id})

    if is_vip:
        user_doc = await db.users.find_one({"_id": user_id})
        expires_at = user_doc.get("premium_expires_at") if user_doc else None
        if expires_at:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            expiry_str = expires_at.strftime("%d %b %Y, %I:%M %p UTC")
        else:
            expiry_str = "Permanent / Lifetime VIP 👑"

        return {
            "is_vip": True,
            "used_count": 0,
            "limit": limit,
            "remaining_count": limit,
            "remaining_seconds": 0,
            "total_messages": total_messages,
            "reset_str": "Unlimited (VIP)",
            "expiry_str": expiry_str,
        }

    now = datetime.now(timezone.utc)
    doc = await db.dm_counts.find_one({"_id": user_id})

    if not doc or "first_msg_at" not in doc:
        return {
            "is_vip": False,
            "used_count": 0,
            "limit": limit,
            "remaining_count": limit,
            "remaining_seconds": 0,
            "total_messages": total_messages,
            "reset_str": "Not started (25 left)",
        }

    first_msg_at = doc.get("first_msg_at")
    if first_msg_at and first_msg_at.tzinfo is None:
        first_msg_at = first_msg_at.replace(tzinfo=timezone.utc)

    elapsed = (now - first_msg_at).total_seconds() if first_msg_at else window_seconds + 1

    if elapsed >= window_seconds:
        return {
            "is_vip": False,
            "used_count": 0,
            "limit": limit,
            "remaining_count": limit,
            "remaining_seconds": 0,
            "total_messages": total_messages,
            "reset_str": "Reset ready (25 left)",
        }

    used_cnt = doc.get("count", 0)
    remaining_secs = max(0, int(window_seconds - elapsed))
    hours = remaining_secs // 3600
    minutes = (remaining_secs % 3600) // 60

    if hours > 0:
        reset_str = f"{hours}h {minutes}m"
    else:
        reset_str = f"{minutes}m"

    return {
        "is_vip": False,
        "used_count": used_cnt,
        "limit": limit,
        "remaining_count": max(0, limit - used_cnt),
        "remaining_seconds": remaining_secs,
        "total_messages": total_messages,
        "reset_str": reset_str,
    }


# ---------- system statistics ----------

async def get_system_counts() -> dict:
    """Return live system counts for admin status report."""
    await init_db()
    now = datetime.now(timezone.utc)
    users_cnt = await db.users.count_documents({})
    groups_cnt = await db.groups.count_documents({})
    messages_cnt = await db.messages.count_documents({})
    couples_cnt = await db.couples.count_documents({"is_active": True})
    referrals_cnt = await db.referrals.count_documents({})
    premium_cnt = await db.users.count_documents({
        "is_premium": True,
        "$or": [
            {"premium_expires_at": {"$gt": now}},
            {"premium_expires_at": None}
        ]
    })
    return {
        "users": users_cnt,
        "groups": groups_cnt,
        "messages": messages_cnt,
        "active_couples": couples_cnt,
        "premium_users": premium_cnt,
        "referrals": referrals_cnt,
    }


# ---------- coins & daily streak ----------

async def get_user_wallet(user_id: int) -> dict:
    """Return user's coins, streak count, and gift count."""
    await init_db()
    u = await db.users.find_one({"_id": user_id})
    if not u:
        return {
            "coins": 0,
            "streak_count": 0,
            "last_streak_claim": None,
            "gifts_sent": 0,
        }
    return {
        "coins": int(u.get("coins", 0)),
        "streak_count": int(u.get("streak_count", 0)),
        "last_streak_claim": u.get("last_streak_claim"),
        "gifts_sent": int(u.get("gifts_sent", 0)),
    }


async def claim_daily_coins(user_id: int) -> dict:
    """
    Claims 100 daily coins.
    Checks 24-hour cooldown:
    - If already claimed within 24h: returns {"success": False, "remaining_seconds": ..., "coins": ..., "streak": ...}
    - If claimed between 24h and 48h: streak increments by 1.
    - If first time or claimed > 48h ago: streak resets to 1.
    Awards +100 coins.
    """
    await init_db()
    now = datetime.now(timezone.utc)
    u = await db.users.find_one({"_id": user_id})

    current_coins = int(u.get("coins", 0)) if u else 0
    current_streak = int(u.get("streak_count", 0)) if u else 0
    last_claim = u.get("last_streak_claim") if u else None

    if last_claim:
        if last_claim.tzinfo is None:
            last_claim = last_claim.replace(tzinfo=timezone.utc)
        elapsed = (now - last_claim).total_seconds()

        # 24 hours cooldown = 86400 seconds
        if elapsed < 86400:
            remaining_seconds = int(86400 - elapsed)
            hours = remaining_seconds // 3600
            minutes = (remaining_seconds % 3600) // 60
            reset_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            return {
                "success": False,
                "reason": "cooldown",
                "remaining_seconds": remaining_seconds,
                "reset_str": reset_str,
                "coins": current_coins,
                "streak": current_streak,
            }
        elif elapsed <= 172800:
            new_streak = current_streak + 1
        else:
            new_streak = 1
    else:
        new_streak = 1

    new_coins = current_coins + 100
    await db.users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "coins": new_coins,
                "streak_count": new_streak,
                "last_streak_claim": now,
            },
            "$setOnInsert": {
                "user_id": user_id,
                "created_at": now,
            },
        },
        upsert=True,
    )
    return {
        "success": True,
        "coins_earned": 100,
        "coins": new_coins,
        "streak": new_streak,
    }


async def deduct_user_coins(user_id: int, amount: int) -> tuple[bool, int]:
    """
    Atomically deducts `amount` coins if the user has enough coins.
    Returns (success: bool, remaining_coins: int).
    """
    await init_db()
    res = await db.users.find_one_and_update(
        {"_id": user_id, "coins": {"$gte": amount}},
        {"$inc": {"coins": -amount}},
        return_document=ReturnDocument.AFTER,
    )
    if res:
        return True, int(res.get("coins", 0))

    w = await get_user_wallet(user_id)
    return False, w["coins"]


async def record_gift_sent(user_id: int, gift_type: str):
    """Increment user's total gifts sent counter."""
    await init_db()
    await db.users.update_one(
        {"_id": user_id},
        {"$inc": {"gifts_sent": 1, f"gifts.{gift_type}": 1}},
    )


async def refund_user_coins(user_id: int, amount: int):
    """Refund user coins on failure/unavailable items."""
    await init_db()
    await db.users.update_one(
        {"_id": user_id},
        {"$inc": {"coins": amount}},
    )


# ---------- referrals ----------

async def get_user_referral_stats(user_id: int) -> dict:
    """Return user's referral statistics, count of invites, and referral earnings."""
    await init_db()
    u = await db.users.find_one({"_id": user_id})
    if not u:
        return {
            "referral_count": 0,
            "referral_earnings": 0,
            "coins": 0,
        }
    return {
        "referral_count": int(u.get("referral_count", 0)),
        "referral_earnings": int(u.get("referral_earnings", 0)),
        "coins": int(u.get("coins", 0)),
    }


async def process_referral(
    new_user_id: int,
    new_username: str | None,
    new_first_name: str | None,
    referrer_id: int,
    coins_reward: int = 1000,
) -> dict:
    """
    Process referral reward when a new user joins via ?start=ref_<referrer_id>.
    Returns:
      {
        "success": bool,
        "reason": str,  # 'self_referral', 'already_referred', 'already_registered', 'ok'
        "referrer_id": int,
        "referrer_coins": int,
        "coins_awarded": int,
      }
    """
    await init_db()
    if new_user_id == referrer_id:
        return {"success": False, "reason": "self_referral"}

    now = datetime.now(timezone.utc)

    # Check if this user was already recorded as referred
    existing_ref = await db.referrals.find_one({"referred_id": new_user_id})
    if existing_ref:
        return {"success": False, "reason": "already_referred"}

    # Check if the user already existed in the users collection with prior established history
    existing_user = await db.users.find_one({"_id": new_user_id})
    if existing_user:
        if existing_user.get("referred_by"):
            return {"success": False, "reason": "already_referred"}
        created_at = existing_user.get("created_at")
        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            # If account was created more than 2 minutes ago, treat as existing user
            if (now - created_at).total_seconds() > 120:
                return {"success": False, "reason": "already_registered"}

    # Insert referral record
    await db.referrals.insert_one({
        "referrer_id": referrer_id,
        "referred_id": new_user_id,
        "referred_username": new_username,
        "referred_name": new_first_name,
        "coins_awarded": coins_reward,
        "created_at": now,
    })

    # Update referrer: +1000 coins, +1 referral_count, +1000 referral_earnings
    ref_user = await db.users.find_one_and_update(
        {"_id": referrer_id},
        {
            "$inc": {
                "coins": coins_reward,
                "referral_count": 1,
                "referral_earnings": coins_reward,
            },
            "$setOnInsert": {
                "user_id": referrer_id,
                "created_at": now,
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    # Tag new user with referred_by
    display_name = new_first_name or (f"@{new_username.lstrip('@')}" if new_username else str(new_user_id))
    await db.users.update_one(
        {"_id": new_user_id},
        {
            "$set": {
                "user_id": new_user_id,
                "display_name": display_name,
                "username": new_username,
                "first_name": new_first_name,
                "referred_by": referrer_id,
            },
            "$setOnInsert": {
                "created_at": now,
                "coins": 0,
            },
        },
        upsert=True,
    )

    referrer_coins = int(ref_user.get("coins", coins_reward)) if ref_user else coins_reward
    return {
        "success": True,
        "reason": "ok",
        "referrer_id": referrer_id,
        "referrer_coins": referrer_coins,
        "coins_awarded": coins_reward,
    }







