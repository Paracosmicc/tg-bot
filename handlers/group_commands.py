import random
import logging
from telegram import Update
from telegram.ext import ContextTypes

import db
from grok_client import GrokClient

logger = logging.getLogger("group_commands")
grok = GrokClient()


def _mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{name}</a>'


async def _require_group(update: Update) -> bool:
    if not update.effective_chat or not update.message:
        return False
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("yeh command sirf group mein kaam karta hai 😌")
        return False
    return True


async def couple_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/couple — shows the current couple, creating a fresh random pairing if none exists."""
    if not await _require_group(update) or not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id

    # Always track the user invoking the command for this group
    if update.effective_user:
        await db.upsert_user(update.effective_user.id, update.effective_user.username, update.effective_user.first_name)
        await db.track_group_member(chat_id, update.effective_user.id)

    existing = await db.get_active_couple(chat_id)
    if existing:
        u1_id = int(existing["user_id_1"])
        u2_id = int(existing["user_id_2"])
        n1 = await db.get_username(u1_id)
        n2 = await db.get_username(u2_id)
        await update.message.reply_text(
            f"aaj ka couple: {_mention(u1_id, n1)} ❤️ "
            f"{_mention(u2_id, n2)} (love score: {existing['love_score']}%)",
            parse_mode="HTML",
        )
        return

    bot_id = context.bot.id
    member_ids = await db.get_group_member_ids(chat_id)
    member_ids = [uid for uid in member_ids if uid != bot_id]

    # If less than 2 members seen, auto-populate from group administrators
    if len(member_ids) < 2:
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            for admin in admins:
                if admin.user and not admin.user.is_bot:
                    await db.upsert_user(admin.user.id, admin.user.username, admin.user.first_name)
                    await db.track_group_member(chat_id, admin.user.id)
            member_ids = await db.get_group_member_ids(chat_id)
            member_ids = [uid for uid in member_ids if uid != bot_id]
        except Exception as e:
            logger.warning("Could not fetch chat admins for group %s: %s", chat_id, e)

    if len(member_ids) < 2:
        await update.message.reply_text(
            "abhi tak is group mein kam se kam 2 members se nahi mili hoon 🙈 thoda aur log message karein group mein, phir try karo!"
        )
        return

    u1, u2 = random.sample(member_ids, 2)
    love_score = random.randint(60, 99)
    await db.create_couple(chat_id, u1, u2, love_score)

    n1, n2 = await db.get_username(u1), await db.get_username(u2)
    await update.message.reply_text(
        f"🎉 aaj ka naya couple ban gaya! {_mention(u1, n1)} ❤️ {_mention(u2, n2)} "
        f"— love score {love_score}%! 24 ghante baad naya couple chunungi 💕",
        parse_mode="HTML",
    )


async def breakup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/breakup — ends the current top couple."""
    if not await _require_group(update) or not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    ok = await db.break_up_top_couple(chat_id)
    if ok:
        await update.message.reply_text("💔 breakup ho gaya... drama complete. /couple bhejo naya pairing ke liye")
    else:
        await update.message.reply_text("abhi koi couple hai hi nahi break karne ko 😅")


async def loveboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/loveboard — top active couples by love score."""
    if not await _require_group(update) or not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    rows = await db.get_loveboard(chat_id)
    if not rows:
        await update.message.reply_text("abhi board khaali hai, /couple try karo pehle 💕")
        return

    lines = ["💘 *Loveboard*"]
    for i, row in enumerate(rows, start=1):
        u1_id = int(row["user_id_1"])
        u2_id = int(row["user_id_2"])
        n1 = await db.get_username(u1_id)
        n2 = await db.get_username(u2_id)
        lines.append(f"{i}. {n1} ❤️ {n2} — {row['love_score']}%")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")



async def mylove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mylove — the sender's own stats in this group."""
    if not await _require_group(update) or not update.effective_chat or not update.message or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    user = update.effective_user
    stats = await db.get_love_stats(chat_id, user.id)
    await update.message.reply_text(
        f"📊 {user.first_name} ke love stats:\n"
        f"💑 Matched: {stats['times_matched']}\n"
        f"💔 Breakups: {stats['times_broken_up']}\n"
        f"💌 Compliments: {stats['compliments_received']}\n"
        f"🔥 Roasts: {stats['roasts_received']}"
    )


COMPLIMENT_FALLBACKS = [
    "tum bohot sweet ho yaar, seriously 🥺❤️",
    "aaj toh tum kaafi confident lag rahe ho, i like that 😌",
    "tumhare saath baat karke acha lagta hai, no cap 💖",
]

ROAST_FALLBACKS = [
    "arre tum toh WiFi jaise ho, kabhi kabhi connect hi nahi hote 😂",
    "itni der lagate ho reply karne mein, courier se fast nahi ho tum 💀",
    "tumhara sense of humor bhi utna hi slow hai jitna tumhara reply time 😭",
]


async def compliment_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/compliment — reply to someone's message to have Vaidehi compliment them."""
    if not await _require_group(update) or not update.effective_chat or not update.message:
        return
    target = update.message.reply_to_message
    if not target or not target.from_user:
        await update.message.reply_text("kisi ke message ko reply karke /compliment bhejo 🙈")
        return

    target_user = target.from_user
    try:
        text = await grok.generate(
            [
                {
                    "role": "system",
                    "content": (
                        "You are Vaidehi, a sweet Hinglish-speaking college girl. Give a short, "
                        "warm, playful one-line compliment to a group member. Keep it wholesome, "
                        "no more than 20 words, in Hinglish. Output only the compliment."
                    ),
                },
                {"role": "user", "content": f"Compliment {target_user.first_name}"},
            ],
            max_tokens=60,
        )
    except Exception:
        text = random.choice(COMPLIMENT_FALLBACKS)

    await db.bump_compliment(update.effective_chat.id, target_user.id)
    await update.message.reply_text(f"{_mention(target_user.id, target_user.first_name)}: {text}", parse_mode="HTML")


async def roast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/roast — reply to someone's message to have Vaidehi roast them (playfully)."""
    if not await _require_group(update) or not update.effective_chat or not update.message:
        return
    target = update.message.reply_to_message
    if not target or not target.from_user:
        await update.message.reply_text("kisi ke message ko reply karke /roast bhejo 😈")
        return

    target_user = target.from_user
    try:
        text = await grok.generate(
            [
                {
                    "role": "system",
                    "content": (
                        "You are Vaidehi, a witty Hinglish-speaking college girl. Give a short, "
                        "playful, LIGHT roast of a group member — teasing, never mean, never about "
                        "appearance, family, or anything genuinely hurtful. Max 20 words, Hinglish. "
                        "Output only the roast."
                    ),
                },
                {"role": "user", "content": f"Roast {target_user.first_name} playfully"},
            ],
            max_tokens=60,
        )
    except Exception:
        text = random.choice(ROAST_FALLBACKS)

    await db.bump_roast(update.effective_chat.id, target_user.id)
    await update.message.reply_text(f"{_mention(target_user.id, target_user.first_name)}: {text}", parse_mode="HTML")
