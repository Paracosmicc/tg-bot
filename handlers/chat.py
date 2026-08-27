import random
import logging
from telegram import Update
from telegram.ext import ContextTypes

import db
import cache
from config import RANDOM_CHIME_PROBABILITY
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
        is_mention = bot_username and f"@{bot_username}" in message.text
        is_reply_to_bot = (
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == context.bot.id
        )
        is_random_chime = random.random() < RANDOM_CHIME_PROBABILITY
        if not (is_mention or is_reply_to_bot or is_random_chime):
            return

    user_text = message.text
    await db.save_message(chat.id, user.id, "user", user_text)

    # Check Redis cache for generic greetings / responses
    is_generic = cache.is_generic_greeting(user_text)
    if is_generic:
        cached_reply = await cache.get_cached_response(user_text)
        if cached_reply:
            logger.info("Serving generic cached response for chat_id %s: '%s'", chat.id, user_text)
            await db.save_message(chat.id, None, "assistant", cached_reply)
            await message.reply_text(cached_reply)
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

