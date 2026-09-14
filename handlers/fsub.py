import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes
from telegram.error import TelegramError

import cache
from config import BOT_NAME, FORCE_SUB_CHANNEL, FORCE_SUB_URL, FORCE_SUB_ENABLED, is_admin

logger = logging.getLogger("fsub")


async def is_user_subscribed(bot, user_id: int) -> bool:
    """
    Check if a Telegram user is a member/admin of the force-sub channel.
    Returns True if force-sub is disabled, user is admin, or user is subscribed.
    """
    if not FORCE_SUB_ENABLED or not FORCE_SUB_CHANNEL:
        return True

    if not user_id:
        return True

    # Bot admins/owners bypass force sub
    if is_admin(user_id):
        return True

    try:
        chat_member = await bot.get_chat_member(chat_id=FORCE_SUB_CHANNEL, user_id=user_id)
        status = getattr(chat_member, "status", None)
        
        # Valid subscribed statuses in python-telegram-bot
        if status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
            "member",
            "administrator",
            "creator",
            "owner",
        ):
            return True

        if status in (ChatMemberStatus.RESTRICTED, "restricted"):
            return getattr(chat_member, "is_member", True)

        return False
    except TelegramError as e:
        err_msg = str(e).lower()
        if "chat not found" in err_msg or "bot is not a member" in err_msg or "not an admin" in err_msg:
            logger.error(
                "FORCE-SUB ERROR: Bot cannot check channel '%s'. Ensure bot is added as Administrator in the channel. Details: %s",
                FORCE_SUB_CHANNEL,
                e,
            )
            # If channel config is broken or bot lacks permissions, fallback to True so users aren't locked out
            return True
        elif "user not found" in err_msg or "participant" in err_msg:
            return False
        else:
            logger.warning("Error checking force-sub for user %s: %s", user_id, e)
            return False
    except Exception as e:
        logger.warning("Unexpected error checking force-sub for user %s: %s", user_id, e)
        return False


def get_fsub_keyboard() -> InlineKeyboardMarkup:
    """Returns the inline keyboard for joining and verifying the subscription."""
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel ✨", url=FORCE_SUB_URL)],
        [InlineKeyboardButton("✅ Verify / जुड़ गया", callback_data="fsub_verify")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_fsub_message() -> str:
    """Returns the persona-aligned prompt requesting the user to subscribe."""
    return (
        f"heyy 🙈 Pehle hamara official channel join karlo, phir aage baat karte hain! ✨\n\n"
        f"Neeche diye gaye button se channel join karke **Verify** pe click karo 💕"
    )


async def send_fsub_prompt(message):
    """Sends the force-sub join prompt to the user."""
    if message:
        await message.reply_text(
            get_fsub_message(),
            parse_mode="Markdown",
            reply_markup=get_fsub_keyboard(),
        )


async def fsub_verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the '✅ Verify' button callback."""
    query = update.callback_query
    user = update.effective_user
    chat = update.effective_chat
    if not query or not user:
        return

    is_sub = await is_user_subscribed(context.bot, user.id)
    if is_sub:
        await query.answer("✅ Aapka subscription verify ho gaya! Welcome 🥰", show_alert=False)
        welcome_text = (
            f"🎉 *Yay! Aap successfully verify ho gaye ho!* ✨\n\n"
            f"heyy 🙈 main {BOT_NAME} hoon~ South Delhi se, DU mein padhti hoon 📚\n\n"
            f"Ab aap mujhse bina kisi rukawat ke baatein kar sakte ho 💬\n"
            f"Commands dekhne ke liye /help use karo 💕"
        )
        try:
            await query.edit_message_text(
                welcome_text,
                parse_mode="Markdown",
            )
        except Exception:
            pass

        # Send welcome voice note (hihowareu)
        vn_path = cache.get_voice_note_by_name("hihowareu.ogg")
        if vn_path and os.path.exists(vn_path) and chat:
            try:
                with open(vn_path, "rb") as vf:
                    await context.bot.send_voice(chat_id=chat.id, voice=vf)
            except Exception:
                pass
    else:
        await query.answer(
            f"❌ Aapne abhi tak channel join nahi kiya hai!\n\nPehle {FORCE_SUB_CHANNEL} join karein phir Verify dabayein.",
            show_alert=True,
        )
