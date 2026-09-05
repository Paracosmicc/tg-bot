import os
from telegram import Update
from telegram.ext import ContextTypes

from config import BOT_NAME
import db
import cache


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    await db.upsert_user(user.id, user.username, user.first_name)

    text = (
        f"heyy 🙈 main {BOT_NAME} hoon~ South Delhi se, DU mein padhti hoon 📚\n\n"
        "bas normally baat karo mujhse, jaise kisi dost se karte ho 💬\n"
        "group mein add kiya hai toh /help bhej ke dekh lo, kya kya masti kar sakte ho 😏"
    )
    await update.message.reply_text(text)

    # Send welcome voice note (hihowareu)
    vn_path = cache.get_voice_note_by_name("hihowareu.ogg")
    if vn_path and os.path.exists(vn_path):
        try:
            with open(vn_path, "rb") as vf:
                await update.message.reply_voice(voice=vf)
        except Exception:
            pass



async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    text = (
        "yeh sab kar sakte ho mere saath:\n\n"
        "💬 *Chat & Media*\n"
        "/start — mujhse mil lo\n"
        "/pic — meri cute selfie dekho 📸\n"
        "/voice — meri voice note suno 🎙️\n"
        "/help — yeh list\n\n"
        "💘 *Group masti* (group mein use karo)\n"
        "/couple — aaj ka couple dekho\n"
        "/loveboard — top couples ka board\n"
        "/mylove — apne love stats dekho\n"
        "/breakup — top couple ko break karo 💔\n"
        "/compliment — kisi ko reply karke bhejo, main compliment de dungi\n"
        "/roast — kisi ko reply karke bhejo, thoda roast kar dungi 😈\n\n"
        "💖 *Support*\n"
        "/donate — mujhe support karo Telegram Stars se! ✨"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

