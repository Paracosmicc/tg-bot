import os
import shutil
import time
import asyncio
import logging
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, status
from telegram.error import RetryAfter, Forbidden, BadRequest, TelegramError

import db
import cache
from config import GROK_MODEL, get_uptime_str, DASHBOARD_PASSWORD
from api.auth import verify_admin

logger = logging.getLogger("api.routes")
router = APIRouter()

PHOTO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "photos")
VOICE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "voices")

os.makedirs(PHOTO_DIR, exist_ok=True)
os.makedirs(VOICE_DIR, exist_ok=True)


class LoginRequest(BaseModel):
    password: str


class BroadcastRequest(BaseModel):
    message: str
    target: str = "users"  # "users", "groups", or "all"
    pin: bool = False


class SendMessageRequest(BaseModel):
    chat_id: int
    message: str
    pin: bool = False


# Public Health Endpoint
@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "vaidehi_bot_api", "timestamp": int(time.time())}


# Auth Login
@router.post("/api/auth/login")
async def login(req: LoginRequest):
    if req.password == DASHBOARD_PASSWORD:
        return {"token": DASHBOARD_PASSWORD, "authenticated": True, "message": "Login successful"}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect password",
    )


# System Statistics
@router.get("/api/stats", dependencies=[Depends(verify_admin)])
async def get_stats():
    counts = await db.get_system_counts()
    c_stats = cache.get_cache_stats()
    photos_cnt = cache.get_photo_count()
    voices_cnt = cache.get_voice_count()
    uptime = get_uptime_str()

    return {
        "uptime": uptime,
        "model": GROK_MODEL,
        "counts": counts,
        "cache": c_stats,
        "media": {
            "photos": photos_cnt,
            "voices": voices_cnt,
        }
    }


# Groups List
@router.get("/api/groups", dependencies=[Depends(verify_admin)])
async def get_groups():
    groups = await db.get_all_groups()
    res = []
    for g in groups:
        chat_id = g.get("chat_id") or g.get("_id")
        title = g.get("title") or "Unnamed Group"
        created_at = g.get("created_at")
        res.append({
            "chat_id": chat_id,
            "title": title,
            "created_at": str(created_at) if created_at else None,
        })
    return {"groups": res, "total": len(res)}


# Users List
@router.get("/api/users", dependencies=[Depends(verify_admin)])
async def get_users():
    user_ids = await db.get_all_user_ids()
    return {"total_users": len(user_ids), "user_ids": user_ids[:200]}


# Photos API
@router.get("/api/media/photos", dependencies=[Depends(verify_admin)])
async def list_photos(request: Request):
    base_url = str(request.base_url).rstrip("/")
    valid_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
    files = []
    for f in os.listdir(PHOTO_DIR):
        if f.lower().endswith(valid_exts):
            full_path = os.path.join(PHOTO_DIR, f)
            stat = os.stat(full_path)
            files.append({
                "filename": f,
                "url": f"{base_url}/media/photos/{f}",
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": int(stat.st_mtime),
            })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"photos": files, "count": len(files)}


@router.post("/api/media/photos/upload", dependencies=[Depends(verify_admin)])
async def upload_photo(file: UploadFile = File(...)):
    valid_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
    filename = file.filename or f"photo_{int(time.time())}.jpg"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in valid_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Allowed: {valid_exts}")

    clean_name = os.path.basename(filename)
    dest_path = os.path.join(PHOTO_DIR, clean_name)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"message": "Photo uploaded successfully", "filename": clean_name}


@router.delete("/api/media/photos/{filename}", dependencies=[Depends(verify_admin)])
async def delete_photo(filename: str):
    clean_name = os.path.basename(filename)
    dest_path = os.path.join(PHOTO_DIR, clean_name)
    if not os.path.exists(dest_path):
        raise HTTPException(status_code=404, detail="Photo not found")

    os.remove(dest_path)
    return {"message": "Photo deleted successfully", "filename": clean_name}


# Voice Notes API
VOICE_INTENT_DESCRIPTIONS = {
    "hihowareu.ogg": "Greeting / /start / Hi",
    "goodnightiwilltalktoutomorrow.ogg": "Good Night / GN / Sleep",
    "ihavealimit.ogg": "DM Rate Limit Reached",
    "tobehonestilikeu.ogg": "Flirt / Love / Like",
    "plsadvicesomemovie.ogg": "Movie Recommendation",
    "sorryihavebeenbusy.ogg": "Late Reply / Busy Excuse",
    "iamworkingandwhatudo.ogg": "What are you doing / Working",
    "whatrudoingnow.ogg": "What are you doing now",
    "areunotbusyrightnow.ogg": "Are you busy right now",
    "whatrudoingforday.ogg": "Day plan / Routine",
    "yess.ogg": "Yes / Agreement",
}


@router.get("/api/media/voices", dependencies=[Depends(verify_admin)])
async def list_voices(request: Request):
    base_url = str(request.base_url).rstrip("/")
    valid_exts = (".ogg", ".oga", ".mp3", ".m4a", ".wav")
    files = []
    for f in os.listdir(VOICE_DIR):
        if f.lower().endswith(valid_exts):
            full_path = os.path.join(VOICE_DIR, f)
            stat = os.stat(full_path)
            intent = VOICE_INTENT_DESCRIPTIONS.get(f, "Custom Voice Note")
            files.append({
                "filename": f,
                "url": f"{base_url}/media/voices/{f}",
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 1),
                "intent": intent,
                "modified": int(stat.st_mtime),
            })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"voices": files, "count": len(files)}


@router.post("/api/media/voices/upload", dependencies=[Depends(verify_admin)])
async def upload_voice(file: UploadFile = File(...)):
    valid_exts = (".ogg", ".oga", ".mp3", ".m4a", ".wav")
    filename = file.filename or f"voice_{int(time.time())}.ogg"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in valid_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Allowed: {valid_exts}")

    clean_name = os.path.basename(filename)
    dest_path = os.path.join(VOICE_DIR, clean_name)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"message": "Voice note uploaded successfully", "filename": clean_name}


@router.delete("/api/media/voices/{filename}", dependencies=[Depends(verify_admin)])
async def delete_voice(filename: str):
    clean_name = os.path.basename(filename)
    dest_path = os.path.join(VOICE_DIR, clean_name)
    if not os.path.exists(dest_path):
        raise HTTPException(status_code=404, detail="Voice note not found")

    os.remove(dest_path)
    return {"message": "Voice note deleted successfully", "filename": clean_name}


# Direct Message / Say API
@router.post("/api/send", dependencies=[Depends(verify_admin)])
async def send_direct_message(req: SendMessageRequest, request: Request):
    tg_app = getattr(request.app.state, "tg_app", None)
    if not tg_app or not tg_app.bot:
        raise HTTPException(status_code=503, detail="Telegram bot instance not attached to server")

    try:
        sent_msg = await tg_app.bot.send_message(
            chat_id=req.chat_id,
            text=req.message,
        )
        if req.pin and req.chat_id < 0:
            try:
                await tg_app.bot.pin_chat_message(chat_id=req.chat_id, message_id=sent_msg.message_id, disable_notification=True)
            except Exception:
                pass
        return {"success": True, "message_id": sent_msg.message_id, "chat_id": req.chat_id}
    except Exception as e:
        logger.error("Failed to send direct message to %s: %s", req.chat_id, e)
        raise HTTPException(status_code=500, detail=str(e))


# Broadcast API
@router.post("/api/broadcast", dependencies=[Depends(verify_admin)])
async def trigger_broadcast(req: BroadcastRequest, request: Request):
    tg_app = getattr(request.app.state, "tg_app", None)
    if not tg_app or not tg_app.bot:
        raise HTTPException(status_code=503, detail="Telegram bot instance not attached to server")

    target_mode = req.target.lower()
    if target_mode == "users":
        recipients = await db.get_all_user_ids()
    elif target_mode == "groups":
        recipients = await db.get_all_group_ids()
    elif target_mode == "all":
        u_ids = await db.get_all_user_ids()
        g_ids = await db.get_all_group_ids()
        recipients = list(dict.fromkeys(u_ids + g_ids))
    else:
        raise HTTPException(status_code=400, detail="Invalid target. Use 'users', 'groups', or 'all'.")

    recipients = [rid for rid in recipients if isinstance(rid, int) and rid != tg_app.bot.id]

    if not recipients:
        return {
            "success": True,
            "total_targeted": 0,
            "successful": 0,
            "failed": 0,
            "blocked": 0,
            "message": "No recipients found in database"
        }

    # Execute Broadcast delivery in background task
    async def run_delivery():
        success_count = 0
        blocked_count = 0
        failed_count = 0

        for chat_id in recipients:
            try:
                sent = await tg_app.bot.send_message(
                    chat_id=chat_id,
                    text=req.message,
                )
                if req.pin and chat_id < 0 and sent:
                    try:
                        await tg_app.bot.pin_chat_message(chat_id=chat_id, message_id=sent.message_id, disable_notification=True)
                    except Exception:
                        pass
                success_count += 1
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 0.5)
            except Forbidden:
                blocked_count += 1
                failed_count += 1
            except Exception:
                failed_count += 1

            await asyncio.sleep(0.04)

        logger.info("Web broadcast finished: targeted=%d, success=%d, failed=%d", len(recipients), success_count, failed_count)

    asyncio.create_task(run_delivery())

    return {
        "success": True,
        "message": f"Broadcast queued and delivering to {len(recipients)} recipients.",
        "target": target_mode,
        "total_targeted": len(recipients)
    }
