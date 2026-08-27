"""
MongoDB data access layer using Motor (async driver for pymongo).
"""
import logging
from datetime import datetime, timezone
import motor.motor_asyncio

import certifi

from typing import Any

from config import MONGODB_URI, MONGODB_DB_NAME, MAX_HISTORY_MESSAGES

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
    groups = await cursor.to_list(length=1000)
    return groups


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

async def get_active_couple(chat_id: int):
    await init_db()
    couple = await db.couples.find_one(
        {"chat_id": chat_id, "is_active": True},
        sort=[("love_score", -1)],
    )
    if not couple:
        return None
    return {
        "id": str(couple["_id"]),
        "user_id_1": couple["user_id_1"],
        "user_id_2": couple["user_id_2"],
        "love_score": couple["love_score"],
    }


async def create_couple(chat_id: int, user_id_1: int, user_id_2: int, love_score: int):
    await init_db()
    await db.couples.insert_one(
        {
            "chat_id": chat_id,
            "user_id_1": user_id_1,
            "user_id_2": user_id_2,
            "love_score": love_score,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
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
