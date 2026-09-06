import logging
from datetime import datetime, timezone
from telegram import Update, LabeledPrice
from telegram.ext import ContextTypes

import db

logger = logging.getLogger("premium")

PREMIUM_STARS_PRICE = 50
PREMIUM_STARS_PRICE = 50
PREMIUM_DURATION_DAYS = 60


async def premium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /premium or /vip — Sends a Telegram Stars invoice to unlock Vaidehi VIP (Unlimited DMs).
    """
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    # Track user
    await db.upsert_user(user.id, user.username, user.first_name)

    # Check if user is already premium
    prem_info = await db.get_premium_info(user.id)
    if prem_info["is_premium"]:
        exp = prem_info["expires_at"]
        exp_str = exp.strftime("%d %b %Y") if exp else "Lifetime"
        await message.reply_text(
            f"👑 *Aap already Vaidehi ke VIP member ho!* 💕\n\n"
            f"✨ **Status:** Active\n"
            f"📅 **Expiry:** {exp_str}\n"
            f"💬 **DM Limits:** Unlimited\n\n"
            f"Bina kisi limit ke jitna marzi chat karo! 🥰",
            parse_mode="Markdown",
        )
        return

    # If invoked in group, guide them or send invoice directly
    is_group = chat.type in ("group", "supergroup")

    title = "⭐ Vaidehi VIP Membership"
    description = (
        "Unlock 2 months of unlimited private DMs with Vaidehi, zero daily cooldowns & VIP badge! 💕"
    )
    payload = f"vaidehi_vip_{user.id}_{PREMIUM_STARS_PRICE}_stars"
    prices = [LabeledPrice(label=f"⭐ Vaidehi VIP (2 Months)", amount=PREMIUM_STARS_PRICE)]

    try:
        await context.bot.send_invoice(
            chat_id=chat.id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",  # Must be empty string for Telegram Stars (XTR)
            currency="XTR",
            prices=prices,
            start_parameter="premium-unlock",
        )
        logger.info("Sent Stars invoice (%d XTR) to user %s (chat %s)", PREMIUM_STARS_PRICE, user.id, chat.id)
    except Exception as e:
        logger.error("Failed to send Stars invoice to %s: %s", user.id, e)
        await message.reply_text(
            "Invoice generate karne mein thodi dikkat aayi 🥺 Thodi der baad try karo ya DM mein /premium bhejo!"
        )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles pre-checkout queries from Telegram for Stars payment validation.
    """
    query = update.pre_checkout_query
    if not query:
        return

    # Validate invoice payload format
    if not query.invoice_payload.startswith("vaidehi_vip_"):
        logger.warning("Rejected unknown invoice payload: %s", query.invoice_payload)
        await query.answer(ok=False, error_message="Yeh invoice expire ho gaya hai. Dobara /premium try karein.")
        return

    # Confirm checkout is valid
    logger.info("Pre-checkout approved for user %s, payload: %s", query.from_user.id, query.invoice_payload)
    await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles successful payment callback when Stars payment is confirmed by Telegram.
    """
    message = update.effective_message
    user = update.effective_user

    if not message or not user or not message.successful_payment:
        return

    payment = message.successful_payment
    charge_id = payment.telegram_payment_charge_id
    total_stars = payment.total_amount

    logger.info(
        "Stars payment SUCCESS: user_id=%s, charge_id=%s, amount=%d Stars",
        user.id,
        charge_id,
        total_stars,
    )

    # Grant VIP / Premium status in MongoDB for 2 months (60 days)
    await db.set_user_premium(
        user_id=user.id,
        duration_days=PREMIUM_DURATION_DAYS,
        charge_id=charge_id,
        stars_amount=total_stars,
    )

    celebration_text = (
        "🎉 **OMG THANK YOU SO MUCH!** 💖✨\n\n"
        "Ab aap officially mere **VIP Member** ban gaye ho! 👑\n\n"
        "🌟 **Aapke VIP Perks:**\n"
        "• 💬 **Unlimited DMs** — Koi 25 message limit ya 8-hour cooldown nahi!\n"
        "• ⚡ **Priority Replies** — Vaidehi aapko hamesha pehle reply karegi.\n"
        "• 📅 **Validity:** 2 Months (60 Days)\n\n"
        "Chalo ab batao, aaj ka din kaisa raha aapka? 🥰"
    )

    await message.reply_text(celebration_text, parse_mode="Markdown")
