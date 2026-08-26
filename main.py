import os
import asyncio
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN
from handlers.start import start, help_command
from handlers.chat import on_message, on_bot_added_to_group
from handlers.group_commands import (
    couple_cmd,
    breakup_cmd,
    loveboard_cmd,
    mylove_cmd,
    compliment_cmd,
    roast_cmd,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("main")


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


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Core commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Group game commands
    app.add_handler(CommandHandler("couple", couple_cmd))
    app.add_handler(CommandHandler("breakup", breakup_cmd))
    app.add_handler(CommandHandler("loveboard", loveboard_cmd))
    app.add_handler(CommandHandler("mylove", mylove_cmd))
    app.add_handler(CommandHandler("compliment", compliment_cmd))
    app.add_handler(CommandHandler("roast", roast_cmd))

    # New members
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added_to_group))

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
