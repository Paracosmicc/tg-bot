from telegram import Update
from telegram.ext import ContextTypes

from config import BOT_NAME
import db


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



async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    text = (
        "yeh sab kar sakte ho mere saath:\n\n"
        "💬 *Chat*\n"
        "/start — mujhse mil lo\n"
        "/help — yeh list\n\n"
        "💘 *Group masti* (group mein use karo)\n"
        "/couple — aaj ka couple dekho\n"
        "/loveboard — top couples ka board\n"
        "/mylove — apne love stats dekho\n"
        "/breakup — top couple ko break karo 💔\n"
        "/compliment — kisi ko reply karke bhejo, main compliment de dungi\n"
        "/roast — kisi ko reply karke bhejo, thoda roast kar dungi 😈"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

