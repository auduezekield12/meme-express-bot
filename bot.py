import asyncio
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8013194385:AAHRFcTr2T5kObSxBPQ-tdNw6AzNOGsMes0")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6553775216"))
CHANNEL = os.getenv("CHANNEL", "@DogeOracle")

pending = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This bot is private.")
        return
    await update.message.reply_text(
        "🧙 *MEME EXPRESS BOT ONLINE*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📡 *Commands:*\n"
        "/scan — Scan all chains for signals\n"
        "/whales — Whale activity alerts\n"
        "/trending — Top trending tokens\n"
        "/market — Full market overview\n"
        "/analyze `ADDRESS` — Analyze any token\n"
        "/win — Post a win card\n"
        "/status — Bot status\n\n"
        "🔄 Auto-scan: every 15 mins\n"
        "🐋 Whale scan: every 20 mins\n"
        "🎯 Only signals scoring 9+/15 are shown",
        parse_mode="Markdown"
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "✅ *BOT STATUS*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 Channel: `{CHANNEL}`\n"
        "⛓ Chains: BTC, SOL, ETH, BSC, Base, ARB\n"
        "🎯 Min Signal Score: 9/15\n"
        "🔄 Auto-scan: Every 15 mins\n"
        "🐋 Whale scan: Every 20 mins\n"
        "⚡ Status: *ONLINE*",
        parse_mode="Markdown"
    )

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = await update.message.reply_text("🔍 Scanning all chains...")
    await run_scan(context, msg)

async def run_scan(context, msg=None):
    from scanner import scan_all
    from analyzer import analyze
    pairs = await scan_all()
    if not pairs:
        if msg:
            await msg.edit_text("❌ No data returned. Try again in a minute.")
        return
    found = 0
    for pair in pairs:
        try:
            result = await analyze(pair)
            if not result:
                continue
            text, sid = result
            pending[sid] = text
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ POST", callback_data=f"post_{sid}"),
                InlineKeyboardButton("❌ Skip", callback_data=f"skip_{sid}")
            ]])
            await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=kb)
            found += 1
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Scan error: {e}")
    if msg:
        if found == 0:
            await msg.edit_text("No signals scored 9+ this round. Market may be quiet.")
        else:
            await msg.edit_text(f"✅ {found} signal(s) found. Review above 👆")

async def whales_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = await update.message.reply_text("🐋 Scanning whale activity...")
    from scanner import scan_whales
    from analyzer import format_whale
    alerts = await scan_whales()
    if not alerts:
        await msg.edit_text("No significant whale moves right now.")
        return
    for pair in alerts[:5]:
        try:
            text, aid = format_whale(pair)
            pending[aid] = text
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📢 POST", callback_data=f"post_{aid}"),
                InlineKeyboardButton("❌ Skip", callback_data=f"skip_{aid}")
            ]])
            await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            logger.error(f"Whale error: {e}")
    await msg.edit_text(f"🐋 {len(alerts)} whale move(s) found. Review above 👆")

async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = await update.message.reply_text("📊 Fetching trending tokens...")
    from scanner import scan_all
    pairs = await scan_all(mode="trending")
    if not pairs:
        await msg.edit_text("Could not fetch trending data.")
        return
    lines = ["🔥 *TOP TRENDING TOKENS*\n━━━━━━━━━━━━━━━━━━━━\n"]
    for i, p in enumerate(pairs[:15], 1):
        sym = p.get("baseToken", {}).get("symbol", "???")
        ch1 = p.get("priceChange", {}).get("h1", 0) or 0
        ch24 = p.get("priceChange", {}).get("h24", 0) or 0
        vol = p.get("volume", {}).get("h24", 0) or 0
        chain = p.get("chainId", "?").upper()
        arrow = "🟢" if ch1 > 0 else "🔴"
        lines.append(
            f"{i}. {arrow} *${sym}* `[{chain}]`\n"
            f"   1H: `{ch1:+.1f}%` | 24H: `{ch24:+.1f}%`\n"
            f"   Vol: `${vol:,.0f}`\n"
        )
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")

async def market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = await update.message.reply_text("🌍 Analyzing market...")
    from scanner import market_overview
    text = await market_overview()
    await msg.edit_text(text, parse_mode="Markdown")

async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /analyze `CONTRACT_ADDRESS`", parse_mode="Markdown")
        return
    address = context.args[0].strip()
    msg = await update.message.reply_text(f"🔬 Analyzing `{address[:10]}...`", parse_mode="Markdown")
    from scanner import fetch_by_address
    from analyzer import analyze
    pair = await fetch_by_address(address)
    if not pair:
        await msg.edit_text("❌ Token not found. Check the address.")
        return
    result = await analyze(pair, force=True)
    if not result:
        await msg.edit_text("❌ Could not analyze this token.")
        return
    text, sid = result
    pending[sid] = text
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ POST", callback_data=f"post_{sid}"),
        InlineKeyboardButton("❌ Skip", callback_data=f"skip_{sid}")
    ]])
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=kb)

async def win_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "🏆 Send win details:\n\nFormat: `$TOKEN MULTIPLIER`\nExample: `$MACRO 198X`",
        parse_mode="Markdown"
    )
    context.user_data["win"] = True

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if context.user_data.get("win"):
        context.user_data["win"] = False
        parts = update.message.text.strip().split()
        if len(parts) >= 2:
            from analyzer import win_card
            token, mult = parts[0].upper(), parts[1].upper()
            text, wid = win_card(token, mult)
            pending[wid] = text
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🏆 POST WIN", callback_data=f"post_{wid}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"skip_{wid}")
            ]])
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text("Format: `$TOKEN MULTIPLIER`", parse_mode="Markdown")

async def button_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("post_"):
        sid = q.data[5:]
        text = pending.get(sid)
        if text:
            await context.bot.send_message(CHANNEL, text, parse_mode="Markdown")
            await q.edit_message_reply_markup(reply_markup=None)
            await q.message.reply_text(f"✅ Posted to {CHANNEL}")
            pending.pop(sid, None)
    elif q.data.startswith("skip_"):
        sid = q.data[5:]
        pending.pop(sid, None)
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text("⏭ Skipped.")

async def auto_scan(context: ContextTypes.DEFAULT_TYPE):
    try:
        await run_scan(context)
    except Exception as e:
        logger.error(f"Auto-scan error: {e}")

async def auto_whale(context: ContextTypes.DEFAULT_TYPE):
    try:
        from scanner import scan_whales
        from analyzer import format_whale
        alerts = await scan_whales()
        for pair in alerts[:3]:
            try:
                text, aid = format_whale(pair)
                pending[aid] = text
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("📢 POST", callback_data=f"post_{aid}"),
                    InlineKeyboardButton("❌ Skip", callback_data=f"skip_{aid}")
                ]])
                await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=kb)
            except Exception as e:
                logger.error(f"Auto-whale inner: {e}")
    except Exception as e:
        logger.error(f"Auto-whale error: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("whales", whales_cmd))
    app.add_handler(CommandHandler("trending", trending_cmd))
    app.add_handler(CommandHandler("market", market_cmd))
    app.add_handler(CommandHandler("analyze", analyze_cmd))
    app.add_handler(CommandHandler("win", win_cmd))
    app.add_handler(CallbackQueryHandler(button_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    jq = app.job_queue
    jq.run_repeating(auto_scan, interval=900, first=60)
    jq.run_repeating(auto_whale, interval=1200, first=120)
    logger.info("Bot started.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
