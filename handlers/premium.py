import logging
from datetime import datetime, timezone
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import os
import db
import cache

logger = logging.getLogger("premium")

PREMIUM_STARS_PRICE = 50
PREMIUM_DURATION_DAYS = 30

MODE_NAMES = {
    "flirty": "💕 Flirty & Romantic",
    "sweet": "🌸 Sweet Bestie",
    "savage": "😈 Savage Roast Queen",
    "adult": "🔞 Adult & Uncensored",
}

MODE_DESCRIPTIONS = {
    "flirty": "Extra bold, romantic, seductive teasing & charming Hinglish banter! 😏",
    "sweet": "Wholesome, caring, emotionally supportive DU college bestie vibe! 🥰",
    "savage": "Delhi roast queen, sharp sarcasm, hilarious comebacks & witty banter! 😂",
    "adult": "Completely uncensored, bold, seductive & explicit romantic chat without limits! 🔥",
}


def get_mode_keyboard(current_mode: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                f"{'✅ ' if current_mode == 'flirty' else ''}💕 Flirty",
                callback_data="set_mode:flirty",
            ),
            InlineKeyboardButton(
                f"{'✅ ' if current_mode == 'sweet' else ''}🌸 Sweet",
                callback_data="set_mode:sweet",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{'✅ ' if current_mode == 'savage' else ''}😈 Savage",
                callback_data="set_mode:savage",
            ),
            InlineKeyboardButton(
                f"{'✅ ' if current_mode == 'adult' else ''}🔞 Adult",
                callback_data="set_mode:adult",
            ),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


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
        current_mode = await db.get_user_mode(user.id)
        await message.reply_text(
            f"👑 *Aap already Vaidehi ke VIP member ho!* 💕\n\n"
            f"✨ **Status:** Active\n"
            f"📅 **Expiry:** {exp_str}\n"
            f"💬 **DM Limits:** Unlimited\n"
            f"🎭 **Persona Mode:** {MODE_NAMES.get(current_mode, '💕 Flirty')} (/mode)\n\n"
            f"Bina kisi limit ke jitna marzi chat karo! 🥰",
            parse_mode="Markdown",
        )
        return

    # If invoked in group, guide them or send invoice directly
    is_group = chat.type in ("group", "supergroup")

    title = "⭐ Vaidehi VIP Membership"
    description = (
        "Unlock 1 month of unlimited private DMs with Vaidehi, zero daily cooldowns & VIP badge! 💕"
    )
    payload = f"vaidehi_vip_{user.id}_{PREMIUM_STARS_PRICE}_stars"
    prices = [LabeledPrice(label=f"⭐ Vaidehi VIP (1 Month)", amount=PREMIUM_STARS_PRICE)]

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

    # Grant VIP / Premium status in MongoDB for 1 month (30 days)
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
        "• 🎭 **Persona Switcher** — /mode bhejkar meri vibe (Flirty, Sweet, Savage) customize karo!\n"
        "• ⚡ **Priority Replies** — Vaidehi aapko hamesha pehle reply karegi.\n"
        "• 📅 **Validity:** 1 Month (30 Days)\n\n"
        "Chalo ab batao, aaj ka din kaisa raha aapka? 🥰"
    )

    await message.reply_text(celebration_text, parse_mode="Markdown")


async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /mode — VIP Exclusive: Customize Vaidehi's persona vibe ('flirty', 'sweet', 'savage').
    """
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    await db.upsert_user(user.id, user.username, user.first_name)
    is_vip = await db.is_user_premium(user.id)

    if not is_vip:
        upgrade_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⭐ Unlock VIP (50 Stars)", callback_data="buy_vip_prompt")]]
        )
        await message.reply_text(
            "👑 *Vaidehi Persona Mode Switcher*\n\n"
            "Yeh feature sirf **VIP Members** ke liye reserved hai! 🙈\n\n"
            "VIP members Vaidehi ka mood aur baat karne ka style customize kar sakte hain:\n"
            "• 💕 **Flirty** — Extra bold, romantic & teasing\n"
            "• 🌸 **Sweet** — Wholesome, caring DU college bestie\n"
            "• 😈 **Savage** — Delhi roast queen & sarcastic banter\n"
            "• 🔞 **Adult** — Uncensored, passionate & explicit chat\n\n"
            "⭐ /premium bhejkar VIP unlock karo!",
            parse_mode="Markdown",
            reply_markup=upgrade_kb,
        )
        return

    args = context.args or []
    if args:
        target_mode = args[0].lower().strip()
        if target_mode in ("flirty", "sweet", "savage", "adult"):
            await db.set_user_mode(user.id, target_mode)
            desc = MODE_DESCRIPTIONS[target_mode]
            await message.reply_text(
                f"✨ **Vaidehi Mood Updated!**\n\n"
                f"🎭 Current Mode: **{MODE_NAMES[target_mode]}**\n"
                f"📝 {desc}",
                parse_mode="Markdown",
                reply_markup=get_mode_keyboard(target_mode),
            )
            return

    current_mode = await db.get_user_mode(user.id)
    await message.reply_text(
        f"🎭 *Vaidehi Persona Mode Selector (VIP Exclusive)*\n\n"
        f"Aap mujhse kis vibe mein baat karna chahte ho? Neeche se apna favorite mode choose karo:\n\n"
        f"• 💕 **Flirty** — Extra bold, romantic & seductive teasing\n"
        f"• 🌸 **Sweet** — Wholesome, caring DU college bestie\n"
        f"• 😈 **Savage** — Delhi roast queen & sarcastic humor\n"
        f"• 🔞 **Adult** — Completely uncensored & explicit romantic roleplay\n\n"
        f"📌 *Current Active Mode:* **{MODE_NAMES.get(current_mode, '💕 Flirty & Romantic')}**",
        parse_mode="Markdown",
        reply_markup=get_mode_keyboard(current_mode),
    )


async def mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles inline button clicks for changing persona mode.
    """
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return

    if query.data == "buy_vip_prompt":
        await query.answer()
        await premium_cmd(update, context)
        return

    if not query.data or not query.data.startswith("set_mode:"):
        await query.answer()
        return

    is_vip = await db.is_user_premium(user.id)
    if not is_vip:
        await query.answer("Yeh feature sirf VIP members ke liye hai ⭐ /premium se unlock karo!", show_alert=True)
        return

    await query.answer()
    selected_mode = query.data.split(":", 1)[1].lower().strip()
    if selected_mode in ("flirty", "sweet", "savage", "adult"):
        await db.set_user_mode(user.id, selected_mode)
        desc = MODE_DESCRIPTIONS[selected_mode]
        text = (
            f"✨ **Vaidehi Mood Updated!**\n\n"
            f"🎭 Current Mode: **{MODE_NAMES[selected_mode]}**\n"
            f"📝 {desc}"
        )
        try:
            await query.edit_message_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=get_mode_keyboard(selected_mode),
            )
        except Exception:
            pass


async def vippic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /vippic or /vipselfie — VIP Exclusive selfie photos.
    Only accessible to active VIP members.
    """
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    is_vip = await db.is_user_premium(user.id)
    if not is_vip:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ Unlock VIP Membership", callback_data="buy_vip_prompt")]
        ])
        await message.reply_text(
            "🔒 *Yeh feature sirf Vaidehi VIP Members ke liye reserved hai!* 👑\n\n"
            "Exclusive selfies, zero DM limits, aur Adult/Flirty persona modes unlock karne ke liye ⭐ **/premium** order karein!",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return

    photo_path = cache.get_random_local_vip_photo()
    caption = cache.get_random_vip_photo_caption()
    if photo_path and os.path.exists(photo_path):
        with open(photo_path, "rb") as photo_file:
            await message.reply_photo(photo=photo_file, caption=caption)
    else:
        await message.reply_text(
            "aaj VIP lounge mein nayi selfie upload nahi hui hai abhi tak 🙈 `assets/vip_photos/` folder mein photos add kar do!",
            parse_mode="Markdown",
        )
