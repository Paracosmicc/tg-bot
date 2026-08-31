import asyncio
import time
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import RetryAfter, Forbidden, BadRequest, TelegramError

import db
import cache
from config import is_admin, GROK_MODEL, get_uptime_str

logger = logging.getLogger("admin")


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /broadcast — Broadcasts a message or replied media to users and/or groups in the database.
    Only accessible by bot admins.
    """
    user = update.effective_user
    message = update.effective_message

    if not user or not message:
        return

    # 1. Admin Verification
    if not is_admin(user):
        await message.reply_text("yeh secret command sirf mere creator ke liye reserved hai 🙈")
        return

    # 2. Extract content & options
    args = context.args or []
    reply_msg = message.reply_to_message

    target_mode = "users"  # "users", "groups", or "all"
    should_pin = False

    # Check flags in args
    cleaned_args = []
    for arg in args:
        lower_arg = arg.lower()
        if lower_arg in ("--groups", "-g", "--group"):
            target_mode = "groups"
        elif lower_arg in ("--all", "-a"):
            target_mode = "all"
        elif lower_arg in ("--users", "-u", "--user"):
            target_mode = "users"
        elif lower_arg in ("--pin", "-p"):
            should_pin = True
        else:
            cleaned_args.append(arg)

    broadcast_text = " ".join(cleaned_args).strip()

    if not broadcast_text and not reply_msg:
        help_text = (
            "📢 *Vaidehi Broadcast Usage Guide*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• `/broadcast <message>` — Send text to all users in DM\n"
            "• Reply to any message/media with `/broadcast` to copy & send it\n\n"
            "*Target flags (optional):*\n"
            "• `/broadcast <msg>` (default: all users)\n"
            "• `/broadcast --groups <msg>` (all registered groups)\n"
            "• `/broadcast --all <msg>` (all users + groups)\n"
            "• `--pin` (pin broadcast in groups)\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Example: `/broadcast heyy sab log kaise ho! 💖`"
        )
        await message.reply_text(help_text, parse_mode="Markdown")
        return

    # 3. Retrieve target recipients
    status_msg = await message.reply_text("🔄 Fetching broadcast targets from database...")

    recipients: list[int] = []
    if target_mode == "users":
        recipients = await db.get_all_user_ids()
    elif target_mode == "groups":
        recipients = await db.get_all_group_ids()
    elif target_mode == "all":
        u_ids = await db.get_all_user_ids()
        g_ids = await db.get_all_group_ids()
        recipients = list(dict.fromkeys(u_ids + g_ids))

    # Deduplicate and filter out invalid IDs or bot itself
    recipients = [rid for rid in recipients if isinstance(rid, int) and rid != context.bot.id]
    total_recipients = len(recipients)

    if total_recipients == 0:
        await status_msg.edit_text(f"⚠️ No recipients found for target mode `{target_mode}` in database.", parse_mode="Markdown")
        return

    mode_label = "Users (DMs)" if target_mode == "users" else ("Groups" if target_mode == "groups" else "Users + Groups")
    start_text = (
        f"🚀 *Broadcast shuru ho raha hai...*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *Target:* `{mode_label}`\n"
        f"👥 *Total Recipients:* `{total_recipients}`\n"
        f"⏳ *Please wait while messages are delivered...*"
    )
    await status_msg.edit_text(start_text, parse_mode="Markdown")

    # 4. Delivery Loop
    start_time = time.time()
    success_count = 0
    blocked_count = 0
    failed_count = 0

    last_update_time = start_time

    for index, chat_id in enumerate(recipients, start=1):
        sent_msg = None
        max_retries = 2
        for attempt in range(max_retries):
            try:
                if reply_msg:
                    # Uses copy_message to preserve original media, formatting, voice note, sticker, etc.
                    sent_msg = await context.bot.copy_message(
                        chat_id=chat_id,
                        from_chat_id=message.chat_id,
                        message_id=reply_msg.message_id,
                    )
                else:
                    sent_msg = await context.bot.send_message(
                        chat_id=chat_id,
                        text=broadcast_text,
                    )

                if sent_msg and should_pin and chat_id < 0:  # If group chat and pin requested
                    try:
                        await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent_msg.message_id, disable_notification=True)
                    except Exception:
                        pass

                success_count += 1
                break
            except RetryAfter as e:
                logger.warning("Flood control hit during broadcast. Sleeping for %s seconds...", e.retry_after)
                await asyncio.sleep(e.retry_after + 0.5)
            except Forbidden:
                blocked_count += 1
                failed_count += 1
                break
            except (BadRequest, TelegramError) as e:
                logger.warning("Failed to broadcast to %s: %s", chat_id, e)
                failed_count += 1
                break
            except Exception as e:
                logger.error("Unexpected error broadcasting to %s: %s", chat_id, e)
                failed_count += 1
                break

        # Periodic live status update every 5 seconds (for large audiences)
        now = time.time()
        if now - last_update_time >= 5.0 and index < total_recipients:
            progress_percent = int((index / total_recipients) * 100)
            progress_text = (
                f"📡 *Broadcasting in progress...* ({progress_percent}%)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 *Target:* `{mode_label}`\n"
                f"👥 *Progress:* `{index}/{total_recipients}`\n"
                f"✅ *Success:* `{success_count}` | ❌ *Failed:* `{failed_count}`\n"
                f"⏱️ *Elapsed:* `{int(now - start_time)}s`"
            )
            try:
                await status_msg.edit_text(progress_text, parse_mode="Markdown")
                last_update_time = now
            except Exception:
                pass

        # Safe rate limit delay (~20-25 messages/sec)
        await asyncio.sleep(0.04)

    # 5. Final Report
    elapsed_time = max(0.1, time.time() - start_time)
    other_failed = max(0, failed_count - blocked_count)

    summary_text = (
        f"📢 *Broadcast Report — Completed!* 🚀\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *Target Audience:* `{mode_label}`\n"
        f"👥 *Total Targeted:* `{total_recipients}`\n"
        f"✅ *Successful:* `{success_count}`\n"
        f"🚫 *Blocked / Unreachable:* `{blocked_count}`\n"
        f"⚠️ *Other Failures:* `{other_failed}`\n"
        f"⏱️ *Total Time:* `{elapsed_time:.1f}s`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ *Vaidehi Bot Broadcast Finished!*"
    )

    try:
        await status_msg.edit_text(summary_text, parse_mode="Markdown")
    except Exception:
        await message.reply_text(summary_text, parse_mode="Markdown")


async def botstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/botstatus — Admin-only command showing live bot uptime, activity, and cache stats."""
    user = update.effective_user
    if not user or not is_admin(user):
        if update.effective_message:
            await update.effective_message.reply_text("yeh secret command sirf mere creator ke liye reserved hai 🙈")
        return

    counts = await db.get_system_counts()
    c_stats = cache.get_cache_stats()
    photos_cnt = cache.get_photo_count()
    uptime = get_uptime_str()
    redis_icon = "🟢 Connected" if c_stats["connected"] else "🔴 Disconnected"

    status_text = (
        f"🤖 *Vaidehi Bot — Live Status & Health*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ *Live Uptime:* `{uptime}`\n"
        f"🧠 *AI Model:* `{GROK_MODEL}`\n\n"
        f"📊 *Activity & Database:*\n"
        f"• 💬 *Total Messages:* `{counts['messages']:,}`\n"
        f"• 👥 *Total Users:* `{counts['users']:,}`\n"
        f"• 🏰 *Active Groups:* `{counts['groups']:,}`\n"
        f"• 💑 *Active Couples:* `{counts['active_couples']:,}`\n"
        f"• 🖼️ *Pre-saved Photos:* `{photos_cnt}`\n\n"
        f"⚡ *Redis Cache:*\n"
        f"• *Status:* {redis_icon}\n"
        f"• *Hits / Total:* `{c_stats['hits']} / {c_stats['total']}`\n"
        f"• *Hit Rate:* `{c_stats['hit_rate']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ *Server Status:* Healthy & Active 🚀"
    )

    if update.effective_message:
        await update.effective_message.reply_text(status_text, parse_mode="Markdown")


async def groups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/groups or /listgroups — Admin command to list all registered groups with IDs and indices."""
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if not is_admin(user):
        await message.reply_text("yeh secret command sirf mere creator ke liye reserved hai 🙈")
        return

    groups = await db.get_all_groups()
    if not groups:
        await message.reply_text("abhi tak koi group register nahi hua hai database mein 😅")
        return

    lines = ["🏰 *Registered Groups in Database:*", "━━━━━━━━━━━━━━━━━━━━"]
    for i, g in enumerate(groups, start=1):
        gid = g.get("chat_id") or g.get("_id")
        title = g.get("title") or "Unnamed Group"
        lines.append(f"`[{i}]` *{title}*\n    ID: `{gid}`")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 *Usage to send:* `/send <ID or index> <message>`")
    await message.reply_text("\n".join(lines), parse_mode="Markdown")


async def send_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /send <chat_id_or_index> <message>
    Sends a message or copied media to a specific group or user chat ID.
    """
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if not is_admin(user):
        await message.reply_text("yeh secret command sirf mere creator ke liye reserved hai 🙈")
        return

    args = context.args or []
    reply_msg = message.reply_to_message

    if not args and not reply_msg:
        usage = (
            "💬 *Send Message to Specific Group/User*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• `/send <chat_id> <message>`\n"
            "• `/send <group_index> <message>` (e.g. `/send 1 Hello!` using index from `/groups`)\n"
            "• Reply to any photo/media with `/send <chat_id or index>`\n"
            "• Add `--pin` to pin message in group\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💡 Use `/groups` to see all group IDs and indices."
        )
        await message.reply_text(usage, parse_mode="Markdown")
        return

    raw_target = args[0] if args else None
    if not raw_target:
        await message.reply_text("⚠️ Please provide a target chat ID or group index. Example: `/send -1001234567890 Hello`", parse_mode="Markdown")
        return

    should_pin = False
    cleaned_args = []
    for a in args[1:]:
        if a.lower() in ("--pin", "-p"):
            should_pin = True
        else:
            cleaned_args.append(a)

    text_to_send = " ".join(cleaned_args).strip()

    # Resolve target chat_id
    target_chat_id = None
    try:
        val = int(raw_target)
        # Check if small index from /groups
        if 1 <= val <= 500:
            groups = await db.get_all_groups()
            if 1 <= val <= len(groups):
                g = groups[val - 1]
                target_chat_id = g.get("chat_id") or g.get("_id")
            else:
                target_chat_id = val
        else:
            target_chat_id = val
    except ValueError:
        await message.reply_text("⚠️ Invalid chat ID or group index. Must be numeric (e.g. `-1001234567890` or `1`).", parse_mode="Markdown")
        return

    if target_chat_id is None:
        await message.reply_text("⚠️ Could not resolve a valid target chat ID.", parse_mode="Markdown")
        return

    if not text_to_send and not reply_msg:
        await message.reply_text("⚠️ Please provide a message or reply to a media message.", parse_mode="Markdown")
        return

    try:
        sent_msg = None
        if reply_msg:
            sent_msg = await context.bot.copy_message(
                chat_id=target_chat_id,
                from_chat_id=message.chat_id,
                message_id=reply_msg.message_id,
            )
        else:
            sent_msg = await context.bot.send_message(
                chat_id=target_chat_id,
                text=text_to_send,
            )

        if sent_msg and should_pin:
            try:
                await context.bot.pin_chat_message(chat_id=target_chat_id, message_id=sent_msg.message_id, disable_notification=True)
            except Exception:
                pass

        await message.reply_text(f"✅ *Message successfully sent to `{target_chat_id}`!*", parse_mode="Markdown")
    except Exception as e:
        logger.error("Failed to send message to %s: %s", target_chat_id, e)
        await message.reply_text(f"❌ *Failed to send message to `{target_chat_id}`:*\n`{e}`", parse_mode="Markdown")


async def say_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /say <message> — When used inside a group, sends text directly as Vaidehi and deletes the admin's command message.
    """
    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat

    if not user or not message or not chat:
        return
    if not is_admin(user):
        await message.reply_text("yeh secret command sirf mere creator ke liye reserved hai 🙈")
        return

    args = context.args or []
    reply_msg = message.reply_to_message
    text_to_say = " ".join(args).strip()

    if not text_to_say and not reply_msg:
        await message.reply_text("Usage: `/say <message>` (or reply to media with `/say`)", parse_mode="Markdown")
        return

    try:
        try:
            await message.delete()
        except Exception:
            pass

        if reply_msg:
            await context.bot.copy_message(
                chat_id=chat.id,
                from_chat_id=chat.id,
                message_id=reply_msg.message_id,
            )
        else:
            await context.bot.send_message(
                chat_id=chat.id,
                text=text_to_say,
            )
    except Exception as e:
        logger.error("Error in /say command: %s", e)

