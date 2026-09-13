import os
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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


async def quota_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/quota (or /quote / /limit) — shows how many messages sent, limit remaining, and reset timer."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not update.message or not chat:
        return

    await db.upsert_user(user.id, user.username, user.first_name)
    quota = await db.get_user_quota_info(user.id)

    name = user.first_name or user.username or "Dost"
    total_sent = quota["total_messages"]

    if quota["is_vip"]:
        validity = quota.get("expiry_str", "Active")
        text = (
            f"👑 <b>VIP Quota Status for {html.escape(name)}</b>\n\n"
            f"✨ <b>Status:</b> Premium VIP Member\n"
            f"🚀 <b>DM Messages:</b> Unlimited (No Limits & Zero Cooldown!)\n"
            f"⏳ <b>VIP Validity:</b> {validity}\n"
            f"📬 <b>Total Messages Sent:</b> {total_sent}\n"
            f"🎭 <b>VIP Persona Modes:</b> Unlocked (/mode)\n"
            f"📸 <b>Exclusive VIP Photos:</b> Unlocked (/vippic)\n\n"
            f"You have full unrestricted access to Vaidehi! Enjoy chatting 🥰✨"
        )
        await update.message.reply_text(text, parse_mode="HTML")
        return

    used = quota["used_count"]
    limit = quota["limit"]
    rem = quota["remaining_count"]
    reset_in = quota["reset_str"]

    # Build a visual progress bar (10 blocks)
    ratio = min(1.0, used / limit) if limit > 0 else 0
    filled_blocks = int(ratio * 10)
    empty_blocks = 10 - filled_blocks
    bar = "█" * filled_blocks + "░" * empty_blocks

    if chat and chat.type in ("group", "supergroup"):
        chat_context = "\n\n💡 <i>Group chats have unlimited messages! Limits only apply to 1-on-1 private DMs.</i>"
    else:
        chat_context = ""

    text = (
        f"📊 <b>Message Quota for {html.escape(name)}</b>\n\n"
        f"💬 <b>DM Messages (8h window):</b> {used} / {limit}\n"
        f"<code>[{bar}]</code> {int(ratio * 100)}% used\n\n"
        f"⚡ <b>Remaining DM Messages:</b> {rem}\n"
        f"⏳ <b>Limit Resets In:</b> {reset_in}\n"
        f"📬 <b>Lifetime Messages Sent:</b> {total_sent}"
        f"{chat_context}\n\n"
        f"⭐ Want unlimited messages with zero cooldown? Tap below to unlock VIP!"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Unlock VIP (Unlimited Messages)", callback_data="buy_vip_prompt")]
    ])
    try:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        await update.message.reply_text(text, reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    text = (
        "yeh sab kar sakte ho mere saath:\n\n"
        "💬 *Chat & Media*\n"
        "/start — mujhse mil lo\n"
        "/earncoins — daily 100 coins claim karo aur streak maintain karo 🔥\n"
        "/shop — gifts bhejo aur VIP photos unlock karo 🛍️\n"
        "/quota — message limit and reset timer check karo 📊\n"
        "/pic — meri cute selfie dekho 📸\n"
        "/voice — meri voice note suno 🎙️\n"
        "/premium — Vaidehi VIP unlock karo (50 ⭐ Stars - 1 Month Unlimited DMs)\n"
        "/mode — Vaidehi ka vibe badlo (Flirty, Sweet, Savage, Adult) 👑 VIP\n"
        "/vippic — VIP exclusive selfie photos 📸 👑 VIP\n"
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


