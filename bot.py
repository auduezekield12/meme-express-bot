import asyncio
import logging
import os
import hashlib
import time
from typing import Dict, List, Optional, Tuple
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8013194385:AAEbnDdJzNFcLyRwl0bdsdxFGs4C-mB-3Jw")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6553775216"))
CHANNEL = os.getenv("CHANNEL", "@DogeOracle")

pending = {}

BYBIT_API = "https://api.bybit.com/v5/market"

COINS = [
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "SHIB",
    "PEPE", "FLOKI", "BONK", "WIF", "BOME", "BRETT", "MEME", "NEIRO",
    "POPCAT", "TURBO", "PNUT", "ACT", "GOAT", "TRUMP", "NEAR", "APT",
    "ARB", "OP", "INJ", "SUI", "TIA", "JUP", "WLD", "FET", "RENDER",
    "LINK", "UNI", "ATOM", "DOT", "MATIC", "LTC", "ORDI", "SATS",
    "GIGA", "MOODENG", "CHILLGUY", "MOG", "MYRO", "SLERF", "PONKE",
]

def uid(s: str) -> str:
    return hashlib.md5(f"{s}{time.time()}".encode()).hexdigest()[:8]

def fp(p: float) -> str:
    if p == 0: return "$0"
    if p < 0.000001: return f"${p:.10f}"
    if p < 0.0001: return f"${p:.8f}"
    if p < 0.01: return f"${p:.6f}"
    if p < 1: return f"${p:.4f}"
    if p < 10000: return f"${p:.2f}"
    return f"${p:,.0f}"

def fn(n: float) -> str:
    if n >= 1_000_000_000: return f"${n/1_000_000_000:.2f}B"
    if n >= 1_000_000: return f"${n/1_000_000:.2f}M"
    if n >= 1_000: return f"${n/1_000:.1f}K"
    return f"${n:.0f}"

async def fetch(session: aiohttp.ClientSession, url: str, params: dict = None):
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        logger.error(f"Fetch error: {e}")
    return None

def calc_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(abs(min(d, 0)))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0: return 100.0
    return round(100 - (100 / (1 + ag/al)), 1)

def calc_ema(closes: List[float], period: int) -> float:
    if len(closes) < period: return closes[-1] if closes else 0
    m = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for p in closes[period:]:
        ema = (p - ema) * m + ema
    return round(ema, 8)

def calc_bb(closes: List[float], period: int = 20) -> Dict:
    if len(closes) < period:
        last = closes[-1] if closes else 0
        return {"upper": last, "middle": last, "lower": last, "width": 0}
    r = closes[-period:]
    mid = sum(r) / period
    std = (sum((x-mid)**2 for x in r) / period) ** 0.5
    upper = mid + 2*std
    lower = mid - 2*std
    return {"upper": upper, "middle": mid, "lower": lower,
            "width": round((upper-lower)/mid*100, 2) if mid > 0 else 0}

async def get_coin_data(session: aiohttp.ClientSession, symbol: str) -> Optional[Dict]:
    try:
        ticker = await fetch(session, f"{BYBIT_API}/tickers",
                           params={"category": "spot", "symbol": f"{symbol}USDT"})
        if not ticker:
            return None
        tlist = ticker.get("result", {}).get("list", [])
        if not tlist:
            return None
        t = tlist[0]

        price = float(t.get("lastPrice", 0))
        if price == 0:
            return None

        prev24 = float(t.get("prevPrice24h", price))
        high24 = float(t.get("highPrice24h", price))
        low24 = float(t.get("lowPrice24h", price))
        vol24usd = float(t.get("turnover24h", 0))
        bid = float(t.get("bid1Price", price))
        ask = float(t.get("ask1Price", price))
        ch24 = ((price - prev24) / prev24 * 100) if prev24 > 0 else 0

        klines = await fetch(session, f"{BYBIT_API}/kline",
                           params={"category": "spot", "symbol": f"{symbol}USDT",
                                   "interval": "60", "limit": 50})
        closes = []
        vols = []
        if klines:
            for k in reversed(klines.get("result", {}).get("list", [])):
                try:
                    closes.append(float(k[4]))
                    vols.append(float(k[5]))
                except: pass

        if len(closes) < 5:
            return None

        rsi = calc_rsi(closes)
        ema9 = calc_ema(closes, 9)
        ema21 = calc_ema(closes, 21)
        ema50 = calc_ema(closes, min(50, len(closes)))
        bb = calc_bb(closes)
        ch1h = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 else 0
        ch4h = ((closes[-1] - closes[-4]) / closes[-4] * 100) if len(closes) >= 4 else 0
        stoch = round(min(max((rsi - 20) / 60 * 100, 0), 100), 1)
        avg_vol = sum(vols[-20:]) / 20 if len(vols) >= 20 else 1
        vol_surge = round(vols[-1] / avg_vol, 1) if avg_vol > 0 and vols else 1.0

        if ema9 > ema21 > ema50 and price > ema9:
            trend, ticon = "STRONG UPTREND", "🚀"
        elif ema9 > ema21 and price > ema21:
            trend, ticon = "UPTREND", "📈"
        elif ema9 < ema21 < ema50 and price < ema9:
            trend, ticon = "STRONG DOWNTREND", "📉"
        elif ema9 < ema21:
            trend, ticon = "DOWNTREND", "🔻"
        else:
            trend, ticon = "SIDEWAYS", "➡️"

        bb_pos = "MIDDLE"
        if price >= bb["upper"] * 0.98: bb_pos = "UPPER"
        elif price <= bb["lower"] * 1.02: bb_pos = "LOWER"

        return {
            "symbol": symbol, "price": price,
            "ch1h": round(ch1h, 2), "ch4h": round(ch4h, 2), "ch24h": round(ch24, 2),
            "high24": high24, "low24": low24, "vol24usd": vol24usd,
            "vol_surge": vol_surge, "rsi": rsi, "stoch": stoch,
            "bb": bb, "bb_pos": bb_pos, "ema9": ema9, "ema21": ema21, "ema50": ema50,
            "trend": trend, "ticon": ticon,
            "support": low24, "resistance": high24,
            "atr": (high24 - low24) * 0.1,
            "bid": bid, "ask": ask,
        }
    except Exception as e:
        logger.error(f"get_coin_data error {symbol}: {e}")
        return None

def score_coin(c: Dict) -> Tuple[float, List[str], str]:
    score = 0.0
    reasons = []
    rsi = c["rsi"]
    stoch = c["stoch"]
    trend = c["trend"]
    vol_surge = c["vol_surge"]
    bb_pos = c["bb_pos"]
    ch1h = c["ch1h"]
    ch24h = c["ch24h"]
    bb = c["bb"]
    price = c["price"]
    ema9 = c["ema9"]
    ema21 = c["ema21"]

    if ch1h <= 0 and ch24h <= 0:
        return 0, [], "👀 WEAK"

    if rsi < 25:
        score += 2.5; reasons.append(f"RSI severely oversold ({rsi})")
    elif rsi < 35:
        score += 1.5; reasons.append(f"RSI oversold ({rsi})")
    elif rsi > 70 and ch1h > 0:
        score += 2.0; reasons.append(f"RSI strong momentum ({rsi})")
    elif 45 <= rsi <= 60 and ch1h > 0:
        score += 1.0; reasons.append(f"RSI healthy zone ({rsi})")

    if stoch < 20:
        score += 1.5; reasons.append(f"Stoch RSI oversold (K:{stoch})")
    elif stoch > 80 and ch1h > 0:
        score += 1.5; reasons.append(f"Stoch RSI momentum (K:{stoch})")

    if bb_pos == "UPPER" and ch1h > 0:
        score += 2.0; reasons.append("Breaking upper Bollinger Band")
    elif bb_pos == "LOWER":
        score += 1.5; reasons.append("At lower Bollinger Band support")

    if trend == "STRONG UPTREND":
        score += 3.0; reasons.append("EMA9>EMA21>EMA50 — Strong uptrend")
    elif trend == "UPTREND":
        score += 2.0; reasons.append("EMA uptrend confirmed")

    if vol_surge > 4:
        score += 2.5; reasons.append(f"Massive volume surge {vol_surge}x")
    elif vol_surge > 2.5:
        score += 1.5; reasons.append(f"Strong volume {vol_surge}x above avg")
    elif vol_surge > 1.5:
        score += 1.0; reasons.append(f"Volume elevated {vol_surge}x")

    if ch1h > 5:
        score += 2.0; reasons.append(f"Strong 1H move (+{ch1h:.1f}%)")
    elif ch1h > 2:
        score += 1.0; reasons.append(f"Positive 1H momentum (+{ch1h:.1f}%)")

    if ch24h > 15:
        score += 1.5; reasons.append(f"Strong 24H trend (+{ch24h:.1f}%)")
    elif ch24h > 8:
        score += 1.0

    low24 = c.get("low24", 0)
    if low24 > 0 and price > 0:
        dist = (price - low24) / low24 * 100
        if dist < 3:
            score += 1.5; reasons.append(f"Near 24H support ({fp(low24)})")

    score = round(min(score, 15), 1)
    if score >= 12: label = "🔥🔥🔥 VERY STRONG SIGNAL"
    elif score >= 9: label = "🔥🔥 STRONG SIGNAL"
    elif score >= 6: label = "🔥 MODERATE SIGNAL"
    else: label = "👀 WEAK SIGNAL"

    return score, reasons[:5], label

def get_trade_plan(c: Dict) -> Dict:
    price = c["price"]
    atr = c.get("atr", price * 0.03)
    trend = c["trend"]
    rsi = c["rsi"]
    if price <= 0: return {}
    if atr == 0: atr = price * 0.03

    if "UPTREND" in trend and rsi < 75:
        tp1 = price + atr * 2.0
        tp2 = price + atr * 4.0
        sl = price - atr * 1.0
        direction = "LONG 🟢"
    elif rsi < 32:
        tp1 = price + atr * 1.8
        tp2 = price + atr * 3.5
        sl = price - atr * 0.8
        direction = "LONG (Oversold Bounce) 🟡"
    else:
        tp1 = price * 1.08
        tp2 = price * 1.15
        sl = price * 0.95
        direction = "LONG (Wait for Dip) 🟡"

    risk = price - sl
    reward = tp1 - price
    rr = round(reward / risk, 2) if risk > 0 else 0
    return {
        "direction": direction, "entry": price,
        "tp1": tp1, "tp1_pct": (tp1-price)/price*100,
        "tp2": tp2, "tp2_pct": (tp2-price)/price*100,
        "sl": sl, "sl_pct": (sl-price)/price*100, "rr": rr,
    }

def get_timing(c: Dict) -> str:
    rsi = c["rsi"]
    trend = c["trend"]
    vol_surge = c["vol_surge"]
    stoch = c["stoch"]
    ch1h = c["ch1h"]
    if "STRONG UPTREND" in trend and vol_surge > 2 and rsi < 72:
        return "⚡ TRADE NOW — Strong momentum confirmed"
    elif "UPTREND" in trend and stoch < 65 and ch1h > 0:
        return "✅ GOOD ENTRY — Trend aligned"
    elif rsi < 30 and stoch < 25:
        return "🎯 OVERSOLD BOUNCE — High probability reversal"
    elif rsi > 78:
        return "⚠️ OVERBOUGHT — Wait for pullback"
    elif "DOWNTREND" in trend:
        return "🚫 AVOID — Downtrend active"
    else:
        return "⏳ WAIT — Setup developing"

def build_signal(c: Dict, score: float, reasons: List[str], label: str) -> Tuple[str, str]:
    symbol = c["symbol"]
    tp = get_trade_plan(c)
    timing = get_timing(c)
    sid = uid(symbol)
    spread = round((c["ask"]-c["bid"])/c["bid"]*100, 3) if c["bid"] > 0 else 0

    text = (
        f"⚡ *MEME EXPRESS SIGNAL* ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *${symbol}/USDT* — Bybit Spot\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Price: `{fp(c['price'])}`\n"
        f"📊 1H: `{c['ch1h']:+.2f}%` | 4H: `{c['ch4h']:+.2f}%` | 24H: `{c['ch24h']:+.2f}%`\n"
        f"🕯 High: `{fp(c['high24'])}` | Low: `{fp(c['low24'])}`\n"
        f"{c['ticon']} Trend: *{c['trend']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🧠 *WHY THIS SETUP ({score}/15):*\n"
    )
    for r in reasons:
        text += f"  • {r}\n"

    text += (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Rating: {label}\n"
        f"⏱ *WHEN TO TRADE:* {timing}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    if tp:
        text += (
            f"📐 *TRADE PLAN ({tp['direction']})*\n"
            f"🎯 Entry:     `{fp(tp['entry'])}`\n"
            f"✅ TP1:       `{fp(tp['tp1'])}` (`{tp['tp1_pct']:+.1f}%`)\n"
            f"✅ TP2:       `{fp(tp['tp2'])}` (`{tp['tp2_pct']:+.1f}%`)\n"
            f"🛑 Stop Loss: `{fp(tp['sl'])}` (`{tp['sl_pct']:+.1f}%`)\n"
            f"⚖️ R:R Ratio: `1:{tp['rr']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )

    bb = c["bb"]
    text += (
        f"📊 *KEY LEVELS:*\n"
        f"Support: `{fp(c['support'])}` | Resistance: `{fp(c['resistance'])}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 *INDICATORS:*\n"
        f"RSI: `{c['rsi']}` | Stoch K: `{c['stoch']}` | BB Width: `{bb['width']}%`\n"
        f"BB Upper: `{fp(bb['upper'])}` | BB Lower: `{fp(bb['lower'])}`\n"
        f"EMA9: `{fp(c['ema9'])}` | EMA21: `{fp(c['ema21'])}` | EMA50: `{fp(c['ema50'])}`\n"
        f"Vol Surge: `{c['vol_surge']}x` | Spread: `{spread}%`\n"
        f"Vol 24H: `{fn(c['vol24usd'])}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 [Trade Bybit](https://www.bybit.com/trade/spot/{symbol}/USDT) | "
        f"[Chart](https://www.tradingview.com/chart/?symbol=BYBIT:{symbol}USDT)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ _DYOR. Not financial advice. Always set SL._\n"
        f"📢 @DogeOracle | 🧙 *Meme Express*"
    )
    return text, sid

async def run_scan(context: ContextTypes.DEFAULT_TYPE, msg=None):
    async with aiohttp.ClientSession() as session:
        results = []
        for i in range(0, len(COINS), 8):
            batch = COINS[i:i+8]
            tasks = [get_coin_data(session, s) for s in batch]
            batch_res = await asyncio.gather(*tasks, return_exceptions=True)
            for r in batch_res:
                if isinstance(r, dict):
                    results.append(r)
            await asyncio.sleep(0.3)

    signals = []
    for c in results:
        score, reasons, label = score_coin(c)
        if score >= 9:
            signals.append((score, c, reasons, label))

    signals.sort(key=lambda x: x[0], reverse=True)

    if not signals:
        if msg:
            await msg.edit_text("No signals scored 9+ right now. Market may be quiet. Try /market for overview.")
        return

    for score, c, reasons, label in signals[:5]:
        text, sid = build_signal(c, score, reasons, label)
        pending[sid] = text
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ POST", callback_data=f"post_{sid}"),
            InlineKeyboardButton("❌ Skip", callback_data=f"skip_{sid}")
        ]])
        await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=kb)
        await asyncio.sleep(1)

    if msg:
        await msg.edit_text(f"✅ {len(signals)} signal(s) found. Review above 👆")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This bot is private.")
        return
    await update.message.reply_text(
        "🧙 *MEME EXPRESS BOT ONLINE*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📡 *Commands:*\n"
        "/scan — Scan all Bybit coins now\n"
        "/trending — Top trending coins\n"
        "/market — Market overview\n"
        "/win — Post a win card\n"
        "/status — Bot status\n\n"
        "🔄 Auto-scan every 15 mins\n"
        "🎯 Only signals scoring 9+/15 shown",
        parse_mode="Markdown"
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(
        "✅ *BOT STATUS*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 Channel: `{CHANNEL}`\n"
        f"🪙 Coins tracked: {len(COINS)}\n"
        "🎯 Min score: 9/15\n"
        "🔄 Auto-scan: Every 15 mins\n"
        "📊 Data: Bybit API (real candles)\n"
        "⚡ Status: *ONLINE*",
        parse_mode="Markdown"
    )

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("🔍 Scanning all Bybit coins...")
    await run_scan(context, msg)

async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("📊 Fetching trending coins...")
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, f"{BYBIT_API}/tickers", params={"category": "spot"})
    if not data:
        await msg.edit_text("Could not fetch data.")
        return
    tickers = data.get("result", {}).get("list", [])
    our = [t for t in tickers if t.get("symbol","").replace("USDT","") in COINS]
    top = sorted(our, key=lambda x: float(x.get("price24hPcnt",0)), reverse=True)[:15]
    lines = ["🔥 *TOP TRENDING ON BYBIT*\n━━━━━━━━━━━━━━━━━━━━\n"]
    for i, t in enumerate(top, 1):
        sym = t.get("symbol","").replace("USDT","")
        ch = round(float(t.get("price24hPcnt",0))*100, 2)
        price = float(t.get("lastPrice",0))
        vol = float(t.get("turnover24h",0))
        arrow = "🟢" if ch > 0 else "🔴"
        lines.append(f"{i}. {arrow} *${sym}*: `{ch:+.2f}%` @ `{fp(price)}`\n   Vol: `{fn(vol)}`\n")
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")

async def market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = await update.message.reply_text("🌍 Analyzing market...")
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, f"{BYBIT_API}/tickers", params={"category": "spot"})
    if not data:
        await msg.edit_text("Could not fetch market data.")
        return
    tickers = data.get("result", {}).get("list", [])
    usdt = [t for t in tickers if t.get("symbol","").endswith("USDT")]
    gainers = [t for t in usdt if float(t.get("price24hPcnt",0)) > 0]
    losers = [t for t in usdt if float(t.get("price24hPcnt",0)) < 0]
    bull = len(gainers)/len(usdt)*100 if usdt else 50
    total_vol = sum(float(t.get("turnover24h",0)) for t in usdt)
    btc = next((t for t in tickers if t.get("symbol")=="BTCUSDT"), None)
    eth = next((t for t in tickers if t.get("symbol")=="ETHUSDT"), None)
    sol = next((t for t in tickers if t.get("symbol")=="SOLUSDT"), None)
    btc_ch = round(float(btc.get("price24hPcnt",0))*100,2) if btc else 0
    btc_p = float(btc.get("lastPrice",0)) if btc else 0
    eth_ch = round(float(eth.get("price24hPcnt",0))*100,2) if eth else 0
    sol_ch = round(float(sol.get("price24hPcnt",0))*100,2) if sol else 0

    if bull > 60 and btc_ch > 1: sent = "🟢 BULLISH"; advice = "Market up. Look for breakouts."
    elif bull > 55: sent = "🟢 MILDLY BULLISH"; advice = "Selective buying works."
    elif bull > 45: sent = "🟡 NEUTRAL"; advice = "Mixed. Trade only high conviction setups."
    else: sent = "🔴 BEARISH"; advice = "Avoid entries. Protect capital."

    our = [t for t in tickers if t.get("symbol","").replace("USDT","") in COINS]
    top5 = sorted(our, key=lambda x: float(x.get("price24hPcnt",0)), reverse=True)[:5]
    top_lines = ""
    for t in top5:
        sym = t.get("symbol","").replace("USDT","")
        ch = round(float(t.get("price24hPcnt",0))*100,2)
        top_lines += f"  🔥 ${sym}: `{ch:+.2f}%`\n"

    await msg.edit_text(
        f"🌍 *BYBIT MARKET OVERVIEW*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Sentiment: *{sent}*\n"
        f"📈 Gainers: `{len(gainers)}` | 📉 Losers: `{len(losers)}`\n"
        f"💹 Bull Ratio: `{bull:.1f}%`\n"
        f"💰 Total Vol 24H: `{fn(total_vol)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"₿ BTC: `{btc_ch:+.2f}%` @ `{fp(btc_p)}`\n"
        f"Ξ ETH: `{eth_ch:+.2f}%`\n"
        f"◎ SOL: `{sol_ch:+.2f}%`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *Advice:* {advice}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🚀 *Top Gainers:*\n{top_lines}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 @DogeOracle | 🧙 Meme Express",
        parse_mode="Markdown"
    )

async def win_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(
        "🏆 Send win details:\nFormat: `$TOKEN MULTIPLIER`\nExample: `$PEPE 15X`",
        parse_mode="Markdown"
    )
    context.user_data["win"] = True

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if context.user_data.get("win"):
        context.user_data["win"] = False
        parts = update.message.text.strip().split()
        if len(parts) >= 2:
            token = parts[0].upper()
            mult = parts[1].upper()
            if not token.startswith("$"): token = f"${token}"
            wid = uid(token)
            text = (
                f"🏆 *WIN CARD* 🏆\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 Token: *{token}*\n"
                f"💰 Return: *{mult}* 🚀\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Called it. We printed it.\n"
                f"Members who followed made it. 💸\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔥 Join for live signals: @DogeOracle\n"
                f"🧙 *Meme Express* | The Alpha Source"
            )
            pending[wid] = text
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🏆 POST WIN", callback_data=f"post_{wid}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"skip_{wid}")
            ]])
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

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

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("trending", trending_cmd))
    app.add_handler(CommandHandler("market", market_cmd))
    app.add_handler(CommandHandler("win", win_cmd))
    app.add_handler(CallbackQueryHandler(button_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.job_queue.run_repeating(auto_scan, interval=900, first=60)
    logger.info("Bot started.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
