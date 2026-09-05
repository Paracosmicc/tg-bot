import logging
from telegram import Update, LabeledPrice
from telegram.ext import ContextTypes

from config import BOT_NAME
import db

logger = logging.getLogger("donate")

# Donation amounts in Telegram Stars (1 Star ≈ $0.013 USD)
DONATION_TIERS = [
    {"stars": 50, "label": "Coffee ☕", "description": "Buy me a coffee!"},
    {"stars": 100, "label": "Lunch 🍕", "description": "Treat me to lunch!"},
    {"stars": 250, "label": "Dinner 🍱", "description": "Fancy dinner date!"},
    {"stars": 500, "label": "Gift 🎁", "description": "Special gift for Vaidehi!"},
    {"stars": 1000, "label": "VIP 💎", "description": "Ultimate supporter!"},
]


async def donate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show donation options with inline buttons using Telegram Stars."""
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    await db.upsert_user(user.id, user.username, user.first_name)

    text = (
        f"heyy {user.first_name}! 💖\n\n"
        f"agar tum mujhe support karna chahte ho, toh Telegram Stars bhej sakte ho! ✨\n\n"
        f"yeh stars mujhe aur better banane mein help karenge~ 🥺\n\n"
        f"select amount below 👇"
    )

    # Create inline keyboard with donation tiers
    keyboard = []
    for tier in DONATION_TIERS:
        keyboard.append([
            {
                "text": f"{tier['label']} - {tier['stars']} Stars ⭐",
                "callback_data": f"donate_{tier['stars']}"
            }
        ])

    # Add custom amount option
    keyboard.append([
        {"text": "💰 Custom Amount", "callback_data": "donate_custom"}
    ])

    await update.message.reply_text(
        text,
        reply_markup={"inline_keyboard": keyboard}
    )


async def pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pre-checkout query from Telegram."""
    query = update.pre_checkout_query
    
    # Validate the invoice (you can add custom validation here)
    if query.invoice_payload.startswith("donate_"):
        try:
            stars = int(query.invoice_payload.replace("donate_", ""))
            if stars > 0:
                await query.answer(ok=True)
                logger.info(f"Pre-checkout approved for {query.from_user.id} - {stars} stars")
                return
        except ValueError:
            pass
    
    # Reject invalid payments
    await query.answer(ok=False, error_message="Invalid donation amount. Please try again.")
    logger.warning(f"Pre-checkout rejected for {query.from_user.id}")


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful payment."""
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    payment = update.message.successful_payment
    
    try:
        # Extract donation amount from payload
        stars = int(payment.invoice_payload.replace("donate_", ""))
        
        # Save donation to database
        await db.save_donation(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            stars=stars,
            currency=payment.currency,
            total_amount=payment.total_amount,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
        )
        
        # Send thank you message
        thank_you_text = (
            f"omg thank you so much {user.first_name}! 🥺💖\n\n"
            f"tumne {stars} Stars donate kiye! yeh bohot pyaar bhara gift hai~ ✨\n\n"
            f"tumhare support se main aur bhi better ban paungi! love you! 💕\n\n"
            f"(Donation ID: {payment.telegram_payment_charge_id[:8]}...)"
        )
        
        await update.message.reply_text(thank_you_text)
        logger.info(f"Successful donation: User {user.id} donated {stars} stars")
        
    except Exception as e:
        logger.error(f"Error processing successful payment: {e}")
        await update.message.reply_text(
            "thank you for your support! 💖 (payment received but something went wrong saving it)"
        )


async def handle_donation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks for donation tiers."""
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    if data == "donate_custom":
        # Prompt for custom amount
        await query.edit_message_text(
            f"heyy {user.first_name}! 💖\n\n"
            f"enter custom amount in stars (minimum 10):\n\n"
            f"just send me a number like: `50` or `200`\n\n"
            f"type /cancel to go back",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_custom_donation"] = True
        return
    
    try:
        stars = int(data.replace("donate_", ""))
        if stars < 10:
            await query.edit_message_text("minimum 10 stars required! try again 🥺")
            return
        
        await _send_invoice(bot=query.bot, user=user, stars=stars, description="Donation")
    except ValueError:
        await query.edit_message_text("invalid amount! please try again 🥺")


async def _send_invoice(bot, user, stars: int, description: str):
    """Send Telegram Stars invoice to user."""
    from telegram import LabeledPrice
    
    # Convert stars to the smallest currency unit (Telegram Stars are already integers)
    total_amount = stars
    
    await bot.send_invoice(
        chat_id=user.id,
        title=f"Support {BOT_NAME}",
        description=f"{description} - {stars} Telegram Stars ✨",
        payload=f"donate_{stars}",
        provider_token="",  # Empty for Telegram Stars (native payments)
        currency="XTR",  # Telegram Stars currency code
        prices=[LabeledPrice(label="Stars", amount=total_amount)],
        start_parameter=f"donate_{stars}",
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False,
    )
    
    logger.info(f"Sent invoice to {user.id} for {stars} stars")


def setup_donation_handlers(application):
    """Register donation handlers with the application."""
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    
    # Handle donation button clicks
    application.add_handler(CallbackQueryHandler(handle_donation_callback, pattern="^donate_"))
    
    # Handle custom amount input
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_donation_input))


async def handle_custom_donation_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom donation amount input."""
    if not update.message or not update.effective_user:
        return
    
    user_data = context.user_data
    if not user_data.get("awaiting_custom_donation"):
        return
    
    text = update.message.text.strip()
    
    # Check for cancel command
    if text.lower() in ["cancel", "/cancel"]:
        user_data["awaiting_custom_donation"] = False
        await update.message.reply_text("donation cancelled. type /donate to start again 💖")
        return
    
    try:
        stars = int(text)
        if stars < 10:
            await update.message.reply_text("minimum 10 stars required! please enter a higher amount 🥺")
            return
        
        user_data["awaiting_custom_donation"] = False
        
        # Send invoice
        await _send_invoice(bot=update.message.bot, user=update.effective_user, stars=stars, description="Custom Donation")
        
    except ValueError:
        await update.message.reply_text("please enter a valid number! like 50 or 100 🥺")
