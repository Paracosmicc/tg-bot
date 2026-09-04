import os
import random
import logging
from telegram import Update
from telegram.ext import ContextTypes

import db
import cache
from config import (
    RANDOM_CHIME_PROBABILITY,
    STICKER_REPLY_PROBABILITY,
    GROK_MODEL,
    is_admin,
    get_uptime_str,
)
from persona import build_system_prompt
from grok_client import GrokClient

logger = logging.getLogger("chat")
grok = GrokClient()



async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat or not message.text:
        return

    # Track identities
    await db.upsert_user(user.id, user.username, user.first_name)
    if chat.type in ("group", "supergroup"):
        await db.upsert_group(chat.id, chat.title)
        await db.track_group_member(chat.id, user.id)

    # In groups, respond when mentioned/replied-to, or with a small random probability (Method 1)
    if chat.type in ("group", "supergroup"):
        bot_username = context.bot.username
        is_mention = bool(bot_username and f"@{bot_username.lower()}" in message.text.lower())
        is_reply_to_bot = bool(
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == context.bot.id
        )
        is_random_chime = random.random() < RANDOM_CHIME_PROBABILITY
        if not (is_mention or is_reply_to_bot or is_random_chime):
            return

    user_text = message.text

    # DM Rate Limiting: Max 25 messages per 8 hours per user in DM; group chats are unlimited
    if chat.type not in ("group", "supergroup"):
        current_cnt, is_exceeded = await db.increment_and_check_dm_limit(user.id)
        if is_exceeded:
            user_disp = user.first_name or user.username or str(user.id)
            logger.info("DM message limit exhausted for user %s (ID: %s, DM Count: %d)", user_disp, user.id, current_cnt)
            exhausted_reply = cache.get_random_dm_exhausted_message()
            await db.save_message(chat.id, user.id, "user", user_text)
            await db.save_message(chat.id, None, "assistant", exhausted_reply)
            await message.reply_text(exhausted_reply)
            # Send limit voice note if available
            limit_vn = cache.get_voice_note_by_name("ihavealimit.ogg")
            if limit_vn and os.path.exists(limit_vn):
                with open(limit_vn, "rb") as vf:
                    await message.reply_voice(voice=vf)
            return

    await db.save_message(chat.id, user.id, "user", user_text)

    # Check if user is asking for a photo / pic / selfie (Zero AI API cost!)
    if cache.is_photo_request(user_text):
        photo_path = cache.get_random_local_photo()
        caption = cache.get_random_photo_caption()
        if photo_path and os.path.exists(photo_path):
            logger.info("Sending local photo '%s' for chat_id %s", photo_path, chat.id)
            await db.save_message(chat.id, None, "assistant", f"[Photo: {caption}]")
            with open(photo_path, "rb") as photo_file:
                await message.reply_photo(photo=photo_file, caption=caption)
            return
        else:
            no_photo_reply = "aaj selfie nahi li abhi tak 🙈 thodi der mein upload karti hoon!"
            await db.save_message(chat.id, None, "assistant", no_photo_reply)
            await message.reply_text(no_photo_reply)
            return

    # Check if user is explicitly asking for a voice note / audio
    if cache.is_voice_request(user_text):
        voice_path = cache.get_voice_for_text(user_text) or cache.get_random_local_voice_note()
        if voice_path and os.path.exists(voice_path):
            caption = cache.get_random_voice_caption()
            logger.info("Sending local voice note '%s' for chat_id %s", voice_path, chat.id)
            await db.save_message(chat.id, None, "assistant", f"[Voice: {os.path.basename(voice_path)}]")
            with open(voice_path, "rb") as vf:
                await message.reply_voice(voice=vf, caption=caption)
            return
        else:
            no_voice_reply = "aaj thoda gala kharab hai 🙈 thodi der mein voice note bhejti hoon!"
            await db.save_message(chat.id, None, "assistant", no_voice_reply)
            await message.reply_text(no_voice_reply)
            return

    # Check for contextual voice note (e.g. Good Night or Greeting)
    matched_vn = cache.get_voice_for_text(user_text)

    # Check Redis cache for generic greetings / responses
    is_generic = cache.is_generic_greeting(user_text)
    if is_generic:
        cached_reply = await cache.get_cached_response(user_text)
        if cached_reply:
            logger.info("Serving generic cached response for chat_id %s: '%s'", chat.id, user_text)
            await db.save_message(chat.id, None, "assistant", cached_reply)
            await message.reply_text(cached_reply)

            # If it's a greeting or matched voice, also send the voice note!
            if matched_vn and os.path.exists(matched_vn):
                with open(matched_vn, "rb") as vf:
                    await message.reply_voice(voice=vf)
            return

    # Occasional sticker reply (Zero Grok API cost!)
    if random.random() < STICKER_REPLY_PROBABILITY:
        sticker_id = cache.get_random_sticker_id()
        if sticker_id:
            logger.info("Replying with random sticker '%s' for chat_id %s", sticker_id, chat.id)
            await db.save_message(chat.id, None, "assistant", f"[Sticker: {sticker_id}]")
            await message.reply_sticker(sticker=sticker_id)
            return

    history = await db.get_recent_context(chat.id)
    system_prompt = build_system_prompt(
        user_display_name=user.first_name or user.username or "someone",
        chat_type=chat.type,
    )

    messages = [{"role": "system", "content": system_prompt}] + history

    try:
        reply = await grok.generate(messages)
        # Store newly generated reply in Redis cache if generic
        if is_generic and reply:
            await cache.set_cached_response(user_text, reply)
    except Exception as e:
        logger.error("Grok generation failed: %s", e)
        reply = "hmm mera dimaag thoda hang ho gaya abhi 🥲 thodi der mein try karo?"

    await db.save_message(chat.id, None, "assistant", reply)
    await message.reply_text(reply)

    # If user message matched good night / greeting or specific voice intent, also send voice note
    if matched_vn and os.path.exists(matched_vn):
        try:
            with open(matched_vn, "rb") as vf:
                await message.reply_voice(voice=vf)
        except Exception as e:
            logger.warning("Could not send contextual voice note: %s", e)


async def on_sticker_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fires when a user sends a sticker to the bot; replies with a cute sticker back."""
    message = update.effective_message
    chat = update.effective_chat
    if not message or not message.sticker or not chat:
        return

    # In groups, only reply if the sticker is directly replying to the bot
    if chat.type in ("group", "supergroup"):
        is_reply_to_bot = bool(
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == context.bot.id
        )
        if not is_reply_to_bot:
            return

    file_id = message.sticker.file_id
    logger.info("Received sticker from user %s: file_id=%s", update.effective_user.id if update.effective_user else "unknown", file_id)

    reply_sticker = cache.get_random_sticker_id()
    if reply_sticker:
        await message.reply_sticker(sticker=reply_sticker)
    else:
        await message.reply_text(f"Aww cute sticker! 🥰 (file_id: `{file_id}`)", parse_mode="Markdown")


async def on_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fires when the bot (or anyone) is added to a group; registers the group and
    seeds group_members with whoever is visible in the update."""
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    new_members = message.new_chat_members or []

    await db.upsert_group(chat.id, chat.title)

    bot_id = context.bot.id
    for member in new_members:
        if member.id == bot_id:
            await context.bot.send_message(
                chat.id,
                "hii sab log! main Vaidehi hoon 🙈 mujhe @-mention karke ya reply karke "
                "baat kar sakte ho. /help bhejo commands ke liye 💕",
            )
        else:
            await db.upsert_user(member.id, member.username, member.first_name)
            await db.track_group_member(chat.id, member.id)


async def pic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/pic or /selfie — sends a pre-saved selfie from assets/photos/."""
    message = update.effective_message
    if not message:
        return
    photo_path = cache.get_random_local_photo()
    caption = cache.get_random_photo_caption()
    if photo_path and os.path.exists(photo_path):
        with open(photo_path, "rb") as photo_file:
            await message.reply_photo(photo=photo_file, caption=caption)
    else:
        await message.reply_text("aaj selfie nahi li abhi tak 🙈 `assets/photos/` folder mein photos add kar do!", parse_mode="Markdown")


async def voice_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/voice, /vn, or /audio — sends a pre-saved voice note from assets/voices/."""
    message = update.effective_message
    if not message:
        return
    voice_path = cache.get_random_local_voice_note()
    caption = cache.get_random_voice_caption()
    if voice_path and os.path.exists(voice_path):
        with open(voice_path, "rb") as voice_file:
            await message.reply_voice(voice=voice_file, caption=caption)
    else:
        await message.reply_text("aaj thoda gala kharab hai 🙈 `assets/voices/` folder mein voice notes add kar do!", parse_mode="Markdown")


async def botstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/botstatus — Admin-only command showing live bot uptime, activity, and cache stats."""
    user = update.effective_user
    if not user or not is_admin(user):
        if update.effective_message:
            await update.effective_message.reply_text("yeh secret command sirf mere creator ke liye reserved hai 🙈")
        return

    counts = await db.get_system_counts()
    c_stats = cache.get_cache_stats()
    photos_cnt = cache.get_photo_count()
    voices_cnt = cache.get_voice_count()
    uptime = get_uptime_str()
    redis_icon = "🟢 Connected" if c_stats["connected"] else "🔴 Disconnected"

    status_text = (
        f"🤖 *Vaidehi Bot — Live Status & Health*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ *Live Uptime:* `{uptime}`\n"
        f"🧠 *AI Model:* `{GROK_MODEL}`\n\n"
        f"📊 *Activity & Database:*\n"
        f"• 💬 *Total Messages:* `{counts['messages']:,}`\n"
        f"• 👥 *Total Users:* `{counts['users']:,}`\n"
        f"• 🏰 *Active Groups:* `{counts['groups']:,}`\n"
        f"• 💑 *Active Couples:* `{counts['active_couples']:,}`\n"
        f"• 🖼️ *Pre-saved Photos:* `{photos_cnt}`\n"
        f"• 🎤 *Pre-saved Voice Notes:* `{voices_cnt}`\n\n"
        f"⚡ *Redis Cache:*\n"
        f"• *Status:* {redis_icon}\n"
        f"• *Hits / Total:* `{c_stats['hits']} / {c_stats['total']}`\n"
        f"• *Hit Rate:* `{c_stats['hit_rate']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ *Server Status:* Healthy & Active 🚀"
    )

    if update.effective_message:
        await update.effective_message.reply_text(status_text, parse_mode="Markdown")



