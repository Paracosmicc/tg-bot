import os
import asyncio
import random
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, RANDOM_JOB_INTERVAL_MINUTES
from handlers.start import start, help_command
from handlers.chat import (
    on_message,
    on_bot_added_to_group,
    on_sticker_received,
    pic_cmd,
    botstatus_cmd,
)
from handlers.group_commands import (
    couple_cmd,
    breakup_cmd,
    loveboard_cmd,
    mylove_cmd,
    compliment_cmd,
    roast_cmd,
)
from persona import build_system_prompt
from grok_client import GrokClient
import db
import cache

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("main")
grok = GrokClient()


async def start_health_server():
    """Simple HTTP health server for Render Free Web Service compatibility."""
    port = int(os.getenv("PORT", "8080"))

    async def handle_client(reader, writer):
        await reader.read(512)
        resp = "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"
        writer.write(resp.encode("utf-8"))
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle_client, "0.0.0.0", port)
    logger.info("Health check HTTP server running on port %d", port)
    return server


async def periodic_flirty_job(app: Application):
    """Background loop that periodically posts a random flirty message/icebreaker into registered groups."""
    interval_seconds = max(300, RANDOM_JOB_INTERVAL_MINUTES * 60)
    # Initial delay of 60s after bot startup
    await asyncio.sleep(60)

    while True:
        try:
            groups = await db.get_all_groups()
            if groups:
                group = random.choice(groups)
                chat_id = group.get("chat_id") or group.get("_id")

                if chat_id:
                    member_ids = await db.get_group_member_ids(chat_id)
                    user_tag = "everyone"
                    if member_ids:
                        target_user_id = random.choice(member_ids)
                        user_tag = await db.get_user_tag(target_user_id)

                    system_prompt = build_system_prompt(
                        user_display_name=user_tag,
                        chat_type="group",
                    )
                    if user_tag.startswith("@"):
                        prompt_msg = (
                            f"Send a short, bold, seductive, and playfully flirty teasing line or icebreaker "
                            f"tagging {user_tag} to grab everyone's attention! Make sure to explicitly include {user_tag} in your response. "
                            f"Use a charming, seductive tone in casual Hinglish (under 2 lines)."
                        )
                    else:
                        prompt_msg = (
                            f"Send a short, bold, seductive, and playfully flirty teasing line or icebreaker "
                            f"addressing {user_tag} to grab everyone's attention! "
                            f"Use a charming, seductive tone in casual Hinglish (under 2 lines)."
                        )

                    prompt_messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt_msg},
                    ]
                    reply = await grok.generate(prompt_messages)
                    if user_tag.startswith("@") and user_tag not in reply:
                        reply = f"{user_tag} {reply}"

                    await db.save_message(chat_id, None, "assistant", reply)
                    await app.bot.send_message(chat_id=chat_id, text=reply)
                    logger.info("Sent periodic flirty drop-in to group %s", chat_id)
        except Exception as e:
            logger.error("Error in periodic flirty job: %s", e)

        await asyncio.sleep(interval_seconds)

async def post_init(app: Application) -> None:
    """Callback after application initialization to start background tasks."""
    logger.info("Initializing Redis connection...")
    await cache.init_redis()
    logger.info("Loading sticker packs from Telegram API...")
    await cache.load_sticker_packs(app.bot)
    asyncio.create_task(periodic_flirty_job(app))



async def post_shutdown(app: Application) -> None:
    """Callback after application shutdown to close resources."""
    logger.info("Closing Redis connection...")
    await cache.close_redis()


def build_app() -> Application:
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Core commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("pic", pic_cmd))
    app.add_handler(CommandHandler("selfie", pic_cmd))
    app.add_handler(CommandHandler("botstatus", botstatus_cmd))

    # Group game commands
    app.add_handler(CommandHandler("couple", couple_cmd))
    app.add_handler(CommandHandler("breakup", breakup_cmd))
    app.add_handler(CommandHandler("loveboard", loveboard_cmd))
    app.add_handler(CommandHandler("mylove", mylove_cmd))
    app.add_handler(CommandHandler("compliment", compliment_cmd))
    app.add_handler(CommandHandler("roast", roast_cmd))

    # New members
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added_to_group))

    # Stickers
    app.add_handler(MessageHandler(filters.Sticker.ALL, on_sticker_received))


    # Fallback chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))


    return app


if __name__ == "__main__":
    import db

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    logger.info("Initializing MongoDB database connection...")
    loop.run_until_complete(db.init_db())

    # Start health server for free web service deployment
    if os.getenv("PORT"):
        loop.create_task(start_health_server())

    application = build_app()
    logger.info("Vaidehi bot starting (polling)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
