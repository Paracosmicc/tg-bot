import os
import urllib.parse
import logging
from typing import TypedDict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import db
import cache

logger = logging.getLogger("coins")


class GiftItem(TypedDict, total=False):
    name: str
    cost: int
    free_reply: str
    vip_reply: str


GIFT_ITEMS: dict[str, GiftItem] = {
    "coffee": {
        "name": "☕ Coffee",
        "cost": 50,
        "free_reply": "Aww thank you! Needed this for college today 🥰\n\n☕ *Sent Coffee to Vaidehi!*\n💰 Remaining Coins: `{coins}` 🪙",
        "vip_reply": "Aww my VIP! Thank you so much for the coffee! Needed this for college today 🥰☕\n\n👑 *VIP Perk:* Free (0 Coins Deducted)",
    },
    "chocolate": {
        "name": "🍫 Chocolates",
        "cost": 100,
        "free_reply": "You are so sweet yaarr 🙈💖\n\n🍫 *Sent Chocolates to Vaidehi!*\n💰 Remaining Coins: `{coins}` 🪙",
        "vip_reply": "Mmm chocolates! You are so sweet yaarr 🙈💖\n\n👑 *VIP Perk:* Free (0 Coins Deducted)",
    },
    "rose": {
        "name": "🌹 Roses",
        "cost": 200,
        "free_reply": "Uff romantic vibes! Ab batao kya sunna hai? 😏\n\n🌹 *Sent Roses to Vaidehi!*\n💰 Remaining Coins: `{coins}` 🪙",
        "vip_reply": "Uff romantic vibes! Ab batao kya sunna hai mere VIP? 😏🌹\n\n👑 *VIP Perk:* Free (0 Coins Deducted)",
    },
    "pic": {
        "name": "📸 Exclusive Pic",
        "cost": 500,
    },
}


def get_shop_keyboard(is_vip: bool) -> InlineKeyboardMarkup:
    """Build the shop keyboard with VIP badges and referral invite button."""
    badge = " (Free 👑)" if is_vip else ""
    keyboard = [
        [
            InlineKeyboardButton(
                f"☕ Coffee ({'Free' if is_vip else '50 🪙'}){badge}",
                callback_data="shop:coffee",
            ),
            InlineKeyboardButton(
                f"🍫 Chocolates ({'Free' if is_vip else '100 🪙'}){badge}",
                callback_data="shop:chocolate",
            ),
        ],
        [
            InlineKeyboardButton(
                f"🌹 Roses ({'Free' if is_vip else '200 🪙'}){badge}",
                callback_data="shop:rose",
            ),
            InlineKeyboardButton(
                f"📸 Exclusive Pic ({'Free' if is_vip else '500 🪙'}){badge}",
                callback_data="shop:pic",
            ),
        ],
        [
            InlineKeyboardButton("🪙 Claim Daily Coins", callback_data="shop:claim_daily"),
            InlineKeyboardButton("💌 Invite & Earn 1000 🪙", callback_data="shop:refer_info"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh Shop", callback_data="shop:refresh"),
        ],
    ]
    if not is_vip:
        keyboard.append([
            InlineKeyboardButton("⭐ Unlock VIP (All Items Free!)", callback_data="buy_vip_prompt")
        ])
    return InlineKeyboardMarkup(keyboard)


async def earncoins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /earncoins (or /daily, /streak) — Claim 100 daily coins & maintain your streak.
    """
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    await db.upsert_user(user.id, user.username, user.first_name)
    is_vip = await db.is_user_premium(user.id)
    res = await db.claim_daily_coins(user.id)

    if res["success"]:
        streak = res["streak"]
        coins = res["coins"]
        streak_fire = "🔥" * min(5, max(1, streak))

        text = (
            f"🎉 *Daily Streak Claimed!* (+100 Coins)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Current Balance:* `{coins}` 🪙 Coins\n"
            f"{streak_fire} *Daily Streak:* `{streak}` Day{'s' if streak > 1 else ''}\n\n"
            f"Aap kal phir aana streak maintain karne ke liye aur 100 extra coins paane ke liye! 💖\n\n"
            f"💡 *Extra Coins:* Apne dosto ko invite karein (/refer) aur paayein **1,000 Coins** har invite par! 💌\n\n"
            f"Coins ko use karne ke liye **/shop** open karein!"
        )
        if is_vip:
            text += "\n\n👑 *Aap Vaidehi VIP Member ho — Shop ke saare items aur photos aapke liye 100% FREE hain!*"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🛍️ Open Shop", callback_data="shop:refresh"),
                InlineKeyboardButton("💌 Invite Friends (+1000 🪙)", callback_data="shop:refer_info"),
            ]
        ])
        await message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        coins = res["coins"]
        streak = res["streak"]
        reset_str = res.get("reset_str", "kuch der")
        text = (
            f"⏳ *Aaj ke 100 coins aap pehle hi claim kar chuke ho!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Balance:* `{coins}` 🪙 Coins\n"
            f"🔥 *Current Streak:* `{streak}` Days\n"
            f"⏱️ *Next Daily Claim In:* `{reset_str}`\n\n"
            f"💡 *Need More Coins?* Apne dosto ko invite karein (/refer) aur har dost ke invite par instant **1,000 Coins** paayein! 💌\n\n"
            f"Apne coins use karne ke liye **/shop** dekhein ya dosto se chat karein! 💕"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🛍️ Open Shop", callback_data="shop:refresh"),
                InlineKeyboardButton("💌 Invite Friends (+1000 🪙)", callback_data="shop:refer_info"),
            ]
        ])
        await message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def refer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /refer (or /referral, /invite) — Earn 1,000 coins for inviting friends.
    """
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    await db.upsert_user(user.id, user.username, user.first_name)
    bot = context.bot
    bot_username = bot.username
    if not bot_username:
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
        except Exception:
            bot_username = "VaidehiAIBot"

    ref_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    stats = await db.get_user_referral_stats(user.id)
    wallet = await db.get_user_wallet(user.id)

    share_text = (
        "Hey! Meet Vaidehi 🙈💖 Your South Delhi college bestie on Telegram! "
        "Chat with her, hear voice notes & unlock selfies ✨"
    )
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_text)}"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 Share Invite Link", url=share_url),
        ],
        [
            InlineKeyboardButton("🛍️ Spend Coins (/shop)", callback_data="shop:refresh"),
            InlineKeyboardButton("🪙 Daily Coins", callback_data="shop:claim_daily"),
        ],
    ])

    text = (
        f"💌 *Vaidehi Referral Program — Earn Coins!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Apne dosto ko Vaidehi se introduce karo aur har friend ke aane par paao **1,000 Coins** 🪙!\n\n"
        f"📊 *Your Referral Stats:*\n"
        f"• 👥 *Friends Invited:* `{stats['referral_count']}`\n"
        f"• 🪙 *Coins Earned:* `{stats['referral_earnings']:,}` Coins\n"
        f"• 💰 *Wallet Balance:* `{wallet['coins']:,}` Coins\n\n"
        f"🔗 *Your Unique Invite Link:*\n"
        f"`{ref_link}`\n\n"
        f"💡 *Kaise Kaam Karta Hai?*\n"
        f"1️⃣ Apna link copy karein ya **Share Invite Link** dabayein.\n"
        f"2️⃣ Jab aapka dost is link se bot start karega, aapko instantly **1,000 Coins** 🪙 milenge!\n"
        f"3️⃣ Coins ko use karke Vaidehi ko coffee, chocolates, roses bhejo ya exclusive photos unlock karo (/shop) 💕"
    )

    await message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def shop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /shop (or /wallet, /coins) — Interactive shop to spend coins on gifts and VIP pics.
    """
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    await db.upsert_user(user.id, user.username, user.first_name)
    wallet = await db.get_user_wallet(user.id)
    is_vip = await db.is_user_premium(user.id)

    status_str = "👑 VIP Member (All Items Free & Unlimited!)" if is_vip else "👤 Free Member"

    text = (
        f"🛍️ *Vaidehi's Coin Shop & Vault*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Your Balance:* `{wallet['coins']}` 🪙 Coins\n"
        f"🔥 *Daily Streak:* `{wallet['streak_count']}` Days\n"
        f"🎖️ *Status:* {status_str}\n\n"
        f"*Select an item below to send a gift or unlock a photo:*\n"
        f"• ☕ Coffee — `50 🪙`\n"
        f"• 🍫 Chocolates — `100 🪙`\n"
        f"• 🌹 Roses — `200 🪙`\n"
        f"• 📸 Exclusive VIP Pic — `500 🪙`\n"
    )

    await message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_shop_keyboard(is_vip),
    )


async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles all callback queries from the /shop menu.
    """
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    data = query.data
    is_vip = await db.is_user_premium(user.id)

    # 1. Claim Daily button inside shop
    if data == "shop:claim_daily":
        res = await db.claim_daily_coins(user.id)
        if res["success"]:
            wallet = await db.get_user_wallet(user.id)
            await query.answer(f"🎉 +100 Coins Claimed! Balance: {wallet['coins']} 🪙", show_alert=True)
            status_str = "👑 VIP Member (All Items Free!)" if is_vip else "👤 Free Member"
            text = (
                f"🛍️ *Vaidehi's Coin Shop & Vault*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 *Your Balance:* `{wallet['coins']}` 🪙 Coins\n"
                f"🔥 *Daily Streak:* `{wallet['streak_count']}` Days\n"
                f"🎖️ *Status:* {status_str}\n\n"
                f"*Select an item below to send a gift or unlock a photo:*\n"
                f"• ☕ Coffee — `50 🪙`\n"
                f"• 🍫 Chocolates — `100 🪙`\n"
                f"• 🌹 Roses — `200 🪙`\n"
                f"• 📸 Exclusive VIP Pic — `500 🪙`\n"
            )
            try:
                await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=get_shop_keyboard(is_vip))
            except Exception:
                pass
        else:
            reset_str = res.get("reset_str", "kuch der")
            await query.answer(f"⏳ Next claim in {reset_str}!", show_alert=True)
        return

    # 2. Refresh Shop
    if data == "shop:refresh":
        wallet = await db.get_user_wallet(user.id)
        status_str = "👑 VIP Member (All Items Free!)" if is_vip else "👤 Free Member"
        text = (
            f"🛍️ *Vaidehi's Coin Shop & Vault*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Your Balance:* `{wallet['coins']}` 🪙 Coins\n"
            f"🔥 *Daily Streak:* `{wallet['streak_count']}` Days\n"
            f"🎖️ *Status:* {status_str}\n\n"
            f"*Select an item below to send a gift or unlock a photo:*\n"
            f"• ☕ Coffee — `50 🪙`\n"
            f"• 🍫 Chocolates — `100 🪙`\n"
            f"• 🌹 Roses — `200 🪙`\n"
            f"• 📸 Exclusive VIP Pic — `500 🪙`\n"
        )
        try:
            await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=get_shop_keyboard(is_vip))
        except Exception:
            pass
        return

    # 3. Referral Info button inside shop
    if data == "shop:refer_info":
        bot = context.bot
        bot_username = bot.username
        if not bot_username:
            try:
                bot_info = await bot.get_me()
                bot_username = bot_info.username
            except Exception:
                bot_username = "VaidehiAIBot"
        ref_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
        stats = await db.get_user_referral_stats(user.id)
        wallet = await db.get_user_wallet(user.id)

        share_text = (
            "Hey! Meet Vaidehi 🙈💖 Your South Delhi college bestie on Telegram! "
            "Chat with her, hear voice notes & unlock selfies ✨"
        )
        share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_text)}"

        ref_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Share Invite Link", url=share_url)],
            [
                InlineKeyboardButton("🛍️ Back to Shop", callback_data="shop:refresh"),
                InlineKeyboardButton("🪙 Daily Coins", callback_data="shop:claim_daily"),
            ],
        ])

        ref_text = (
            f"💌 *Vaidehi Referral Program — Earn 1,000 Coins!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Apne dosto ko invite karo aur har friend ke bot start karne par paao **1,000 Coins** 🪙!\n\n"
            f"📊 *Your Stats:*\n"
            f"• 👥 *Friends Invited:* `{stats['referral_count']}`\n"
            f"• 🪙 *Coins Earned:* `{stats['referral_earnings']:,}` Coins\n"
            f"• 💰 *Wallet Balance:* `{wallet['coins']:,}` Coins\n\n"
            f"🔗 *Invite Link:*\n"
            f"`{ref_link}`"
        )
        try:
            await query.edit_message_text(text=ref_text, parse_mode="Markdown", reply_markup=ref_keyboard)
        except Exception:
            await context.bot.send_message(chat_id=chat.id, text=ref_text, parse_mode="Markdown", reply_markup=ref_keyboard)
        return

    # 4. Item Purchase (Coffee, Chocolate, Rose, Pic)
    item_key = data.replace("shop:", "")
    if item_key not in GIFT_ITEMS:
        return

    item = GIFT_ITEMS[item_key]

    # Handle Photo Unlock
    if item_key == "pic":
        if is_vip:
            # VIP: Free photo
            photo_path = await cache.get_next_vip_photo_for_user(user.id)
            caption = cache.get_random_vip_photo_caption()
            if photo_path and os.path.exists(photo_path):
                vip_caption = (
                    f"👑 *Exclusive VIP Vault Selfie Unlocked!*\n"
                    f"_{caption}_\n\n"
                    f"✨ *VIP Perk:* Free & Unlimited"
                )
                with open(photo_path, "rb") as photo_file:
                    await context.bot.send_photo(chat_id=chat.id, photo=photo_file, caption=vip_caption, parse_mode="Markdown")
            else:
                await context.bot.send_message(chat_id=chat.id, text="aaj VIP lounge mein nayi selfie upload nahi hui hai abhi tak 🙈 `assets/vip_photos/` folder mein photos add kar do!")
            return

        # Free User: Deduct 500 coins
        cost = item.get("cost", 500)
        ok, rem_coins = await db.deduct_user_coins(user.id, cost)
        if not ok:
            await query.answer(
                f"❌ Insufficient Coins! You have {rem_coins} 🪙, but 500 🪙 is required. Type /earncoins to earn coins!",
                show_alert=True,
            )
            return

        photo_path = await cache.get_next_vip_photo_for_user(user.id)
        caption = cache.get_random_vip_photo_caption()
        if photo_path and os.path.exists(photo_path):
            await db.record_gift_sent(user.id, "pic")
            photo_caption = (
                f"📸 *Exclusive VIP Vault Selfie Unlocked!*\n"
                f"_{caption}_\n\n"
                f"💰 Remaining Coins: `{rem_coins}` 🪙"
            )
            with open(photo_path, "rb") as photo_file:
                await context.bot.send_photo(chat_id=chat.id, photo=photo_file, caption=photo_caption, parse_mode="Markdown")
        else:
            # Refund if no photo available
            await db.refund_user_coins(user.id, cost)
            await context.bot.send_message(chat_id=chat.id, text="aaj selfie upload nahi hui hai abhi tak 🙈 aapke 500 coins wapas kar diye gaye!")
        return

    # Handle Gifts (Coffee, Chocolate, Rose)
    if is_vip:
        # VIP: Free gift reaction
        await db.record_gift_sent(user.id, item_key)
        vip_text = item.get("vip_reply", "")
        if vip_text:
            await context.bot.send_message(chat_id=chat.id, text=vip_text, parse_mode="Markdown")
        return

    cost = item.get("cost", 50)
    ok, rem_coins = await db.deduct_user_coins(user.id, cost)
    if not ok:
        await query.answer(
            f"❌ Insufficient Coins! You have {rem_coins} 🪙, but {cost} 🪙 is required. Type /earncoins!",
            show_alert=True,
        )
        return

    await db.record_gift_sent(user.id, item_key)
    free_tmpl = item.get("free_reply", "")
    if free_tmpl:
        reply_text = free_tmpl.format(coins=rem_coins)
        await context.bot.send_message(chat_id=chat.id, text=reply_text, parse_mode="Markdown")

