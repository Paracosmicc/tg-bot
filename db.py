"""
MongoDB data access layer using Motor (async driver for pymongo).
"""
import logging
from datetime import datetime, timezone
import motor.motor_asyncio

import certifi

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
            await db.donations.create_index([("user_id", 1), ("created_at", -1)])
        except Exception as e:
            logger.warning("MongoDB index creation warning: %s", e)



async def close_db():
    global client
    if client is not None:
        client.close()
        client = None


async def save_donation(user_id: int, username: str | None, first_name: str | None, stars: int, currency: str, total_amount: int, telegram_payment_charge_id: str):
    """Save donation record to database."""
    await init_db()
    await db.donations.insert_one(
        {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "stars": stars,
            "currency": currency,
            "total_amount": total_amount,
            "telegram_payment_charge_id": telegram_payment_charge_id,
            "created_at": datetime.now(timezone.utc),
        }
    )
    logger.info(f"Saved donation: User {user_id} donated {stars} stars")


async def get_user_donations(user_id: int) -> list[dict]:
    """Get all donations by a user."""
    await init_db()
    cursor = db.donations.find({"user_id": user_id}).sort("created_at", -1)
    donations = await cursor.to_list(length=100)
    return donations


async def get_total_donations() -> dict:
    """Get total donation statistics."""
    await init_db()
    pipeline = [
        {"$group": {"_id": None, "total_stars": {"$sum": "$stars"}, "total_count": {"$sum": 1}}},
    ]
    result = await db.donations.aggregate(pipeline).to_list(length=1)
    if result:
        return {"total_stars": result[0].get("total_stars", 0), "total_count": result[0].get("total_count", 0)}
    return {"total_stars": 0, "total_count": 0}


# ---------- users / groups ----------

async def upsert_user(user_id: int, username: str | None, first_name: str | None):
    await init_db()
    await db.users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
            },
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
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


# ---------- DM AI Rate Limits ----------

async def increment_and_check_dm_limit(user_id: int, limit: int = DM_MESSAGE_LIMIT, window_seconds: int = DM_WINDOW_SECONDS) -> tuple[int, bool]:
    """Increment DM AI API call count for user_id and automatically reset every 8 hours (28800 seconds).
    Returns (current_count, is_exceeded).
    Group chats are exempt and keep unlimited AI calls. Zero-cost actions (stickers, cached replies) do not consume this limit.
    """
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

    is_exceeded = current_cnt > limit
    return current_cnt, is_exceeded


# ---------- system statistics ----------

async def get_system_counts() -> dict:
    """Return live system counts for admin status report."""
    await init_db()
    users_cnt = await db.users.count_documents({})
    groups_cnt = await db.groups.count_documents({})
    messages_cnt = await db.messages.count_documents({})
    couples_cnt = await db.couples.count_documents({"is_active": True})
    return {
        "users": users_cnt,
        "groups": groups_cnt,
        "messages": messages_cnt,
        "active_couples": couples_cnt,
    }




