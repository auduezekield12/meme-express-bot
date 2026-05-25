import hashlib
import time
import logging
from typing import Dict, Tuple, Optional, List

logger = logging.getLogger(__name__)

def uid(s: str) -> str:
    return hashlib.md5(f"{s}{time.time()}".encode()).hexdigest()[:8]

def fmtn(n: float) -> str:
    if n >= 1_000_000_000: return f"${n/1_000_000_000:.2f}B"
    if n >= 1_000_000: return f"${n/1_000_000:.2f}M"
    if n >= 1_000: return f"${n/1_000:.1f}K"
    return f"${n:.0f}"

def fmtp(p: float) -> str:
    if p == 0: return "$0"
    if p < 0.000001: return f"${p:.10f}"
    if p < 0.0001: return f"${p:.8f}"
    if p < 0.01: return f"${p:.6f}"
    if p < 1: return f"${p:.4f}"
    if p < 100: return f"${p:.4f}"
    if p < 10000: return f"${p:.2f}"
    return f"${p:,.0f}"

def score_setup(coin: Dict) -> Tuple[float, List[str], str]:
    score = 0.0
    reasons = []

    rsi = coin.get("rsi_1h", 50)
    stoch = coin.get("stoch_k", 50)
    trend = coin.get("trend", "")
    vol_surge = coin.get("vol_surge", 1)
    bb_pos = coin.get("bb_position", "MIDDLE")
    macd = coin.get("macd", {})
    ch1h = coin.get("ch1h", 0)
    ch4h = coin.get("ch4h", 0)
    ch24h = coin.get("ch24h", 0)
    bb = coin.get("bb", {})
    price = coin.get("price", 0)
    ema9 = coin.get("ema9", 0)
    ema21 = coin.get("ema21", 0)
    ema50 = coin.get("ema50", 0)

    # RSI scoring
    if rsi < 25:
        score += 2.5
        reasons.append(f"RSI severely oversold ({rsi})")
    elif rsi < 35:
        score += 1.5
        reasons.append(f"RSI oversold ({rsi})")
    elif rsi > 70 and ch1h > 0:
        score += 2.0
        reasons.append(f"RSI strong momentum ({rsi})")
    elif 45 <= rsi <= 60 and ch1h > 0:
        score += 1.0
        reasons.append(f"RSI in healthy zone ({rsi})")

    # Stoch RSI
    if stoch < 20:
        score += 1.5
        reasons.append(f"Stoch RSI deeply oversold (K:{stoch})")
    elif stoch > 80 and ch1h > 0:
        score += 1.5
        reasons.append(f"Stoch RSI strong momentum (K:{stoch})")

    # Bollinger Bands
    if bb_pos == "UPPER" and ch1h > 0:
        score += 2.0
        reasons.append("Price breaking upper Bollinger Band")
    elif bb_pos == "LOWER":
        score += 1.5
        reasons.append(f"Price at lower Bollinger Band (support)")
    if bb.get("width", 0) > 5:
        score += 0.5
        reasons.append(f"BB squeeze breakout (width: {bb.get('width', 0)}%)")

    # EMA Trend
    if trend == "STRONG UPTREND":
        score += 3.0
        reasons.append("EMA9 > EMA21 > EMA50 — Strong uptrend confirmed")
    elif trend == "UPTREND":
        score += 2.0
        reasons.append("EMA9 > EMA21 — Uptrend confirmed")
    elif trend == "STRONG DOWNTREND":
        score += 0
    elif trend == "SIDEWAYS" and rsi < 40:
        score += 1.0
        reasons.append("Consolidating near support — potential breakout")

    # MACD
    macd_val = macd.get("macd", 0)
    macd_sig = macd.get("signal", 0)
    macd_hist = macd.get("histogram", 0)
    if macd_val > macd_sig and macd_hist > 0:
        score += 2.0
        reasons.append("MACD bullish crossover confirmed")
    elif macd_hist > 0:
        score += 1.0
        reasons.append("MACD histogram positive")

    # Volume surge
    if vol_surge > 4:
        score += 2.5
        reasons.append(f"Massive volume surge {vol_surge}x above average")
    elif vol_surge > 2.5:
        score += 1.5
        reasons.append(f"Strong volume surge {vol_surge}x above average")
    elif vol_surge > 1.5:
        score += 1.0
        reasons.append(f"Volume elevated {vol_surge}x above average")

    # Price momentum
    if ch1h > 5:
        score += 2.0
        reasons.append(f"Strong 1H momentum (+{ch1h:.1f}%)")
    elif ch1h > 2:
        score += 1.0
        reasons.append(f"Positive 1H momentum (+{ch1h:.1f}%)")

    if ch24h > 15:
        score += 1.5
        reasons.append(f"Strong 24H trend (+{ch24h:.1f}%)")
    elif ch24h > 8:
        score += 1.0

    # Near support
    low_24h = coin.get("low_24h", 0)
    if low_24h > 0 and price > 0:
        dist_from_support = ((price - low_24h) / low_24h * 100)
        if dist_from_support < 3:
            score += 1.5
            reasons.append(f"Price near key support (${fmtp(low_24h)})")

    score = round(min(score, 15), 1)

    if score >= 12:
        label = "🔥🔥🔥 VERY STRONG SIGNAL"
    elif score >= 9:
        label = "🔥🔥 STRONG SIGNAL"
    elif score >= 6:
        label = "🔥 MODERATE SIGNAL"
    else:
        label = "👀 WEAK SIGNAL"

    return score, reasons[:6], label

def trade_plan(coin: Dict) -> Dict:
    price = coin.get("price", 0)
    atr = coin.get("atr", 0)
    trend = coin.get("trend", "")
    rsi = coin.get("rsi_1h", 50)
    support = coin.get("support", 0)
    resistance = coin.get("resistance", 0)

    if price <= 0:
        return {}
    if atr == 0:
        atr = price * 0.03

    if "UPTREND" in trend and rsi < 75:
        tp1 = price + atr * 2.0
        tp2 = price + atr * 4.0
        sl = max(price - atr * 1.0, support * 0.99) if support > 0 else price - atr * 1.0
        direction = "LONG 🟢"
    elif rsi < 32:
        tp1 = price + atr * 1.8
        tp2 = price + atr * 3.5
        sl = price - atr * 0.8
        direction = "LONG (Oversold Bounce) 🟡"
    else:
        tp1 = min(price * 1.08, resistance * 0.99) if resistance > 0 else price * 1.08
        tp2 = price * 1.15
        sl = price * 0.95
        direction = "LONG (Wait for Dip) 🟡"

    risk = price - sl
    reward = tp1 - price
    rr = round(reward / risk, 2) if risk > 0 else 0

    return {
        "direction": direction,
        "entry": price,
        "tp1": tp1,
        "tp1_pct": (tp1 - price) / price * 100,
        "tp2": tp2,
        "tp2_pct": (tp2 - price) / price * 100,
        "sl": sl,
        "sl_pct": (sl - price) / price * 100,
        "rr": rr,
    }

def get_timing(coin: Dict) -> str:
    rsi = coin.get("rsi_1h", 50)
    trend = coin.get("trend", "")
    vol_surge = coin.get("vol_surge", 1)
    stoch = coin.get("stoch_k", 50)
    ch1h = coin.get("ch1h", 0)
    macd = coin.get("macd", {})
    macd_hist = macd.get("histogram", 0)

    if "STRONG UPTREND" in trend and vol_surge > 2 and rsi < 72 and macd_hist > 0:
        return "⚡ TRADE NOW — Strong momentum, volume and MACD confirmed"
    elif "UPTREND" in trend and stoch < 65 and ch1h > 0:
        return "✅ GOOD ENTRY — Trend up, indicators aligned"
    elif rsi < 30 and stoch < 25:
        return "🎯 OVERSOLD BOUNCE — High probability reversal zone"
    elif rsi < 40 and macd_hist > 0:
        return "✅ EARLY ENTRY — RSI recovering with MACD confirmation"
    elif rsi > 78:
        return "⚠️ OVERBOUGHT — Wait for pullback to enter"
    elif "SIDEWAYS" in trend:
        return "⏳ WAIT — No clear direction. Wait for breakout"
    elif "DOWNTREND" in trend:
        return "🚫 AVOID — Downtrend active. Wait for reversal"
    else:
        return "👀 MONITOR — Setup developing, not ready yet"

def get_market_condition(coin: Dict) -> str:
    rsi = coin.get("rsi_1h", 50)
    trend = coin.get("trend", "")
    ch24h = coin.get("ch24h", 0)
    vol_surge = coin.get("vol_surge", 1)
    bb_pos = coin.get("bb_position", "MIDDLE")

    conditions = []

    if ch24h > 20:
        conditions.append("📈 Strong 24H rally in progress")
    elif ch24h > 10:
        conditions.append("📈 Healthy 24H upward movement")
    elif ch24h < -10:
        conditions.append("📉 Significant 24H sell-off")

    if vol_surge > 3:
        conditions.append("🔊 Unusually high volume — big players active")
    elif vol_surge > 2:
        conditions.append("🔊 Above average volume")

    if bb_pos == "UPPER":
        conditions.append("📊 Trading at upper Bollinger Band — momentum high")
    elif bb_pos == "LOWER":
        conditions.append("📊 Trading at lower Bollinger Band — potential bounce")

    if rsi > 70:
        conditions.append("⚠️ Overbought territory — pullback possible")
    elif rsi < 30:
        conditions.append("💡 Oversold territory — reversal likely")

    if not conditions:
        conditions.append("Market conditions normal")

    return "\n".join(f"  • {c}" for c in conditions[:3])

async def analyze(coin: Dict, force: bool = False) -> Optional[Tuple[str, str]]:
    try:
        symbol = coin.get("symbol", "???").upper()
        price = coin.get("price", 0)
        ch1h = coin.get("ch1h", 0)
        ch4h = coin.get("ch4h", 0)
        ch24h = coin.get("ch24h", 0)
        high_24h = coin.get("high_24h", 0)
        low_24h = coin.get("low_24h", 0)
        vol_24h_usd = coin.get("vol_24h_usd", 0)
        vol_surge = coin.get("vol_surge", 1)
        rsi_1h = coin.get("rsi_1h", 50)
        rsi_15m = coin.get("rsi_15m", 50)
        stoch_k = coin.get("stoch_k", 50)
        bb = coin.get("bb", {})
        macd = coin.get("macd", {})
        ema9 = coin.get("ema9", 0)
        ema21 = coin.get("ema21", 0)
        ema50 = coin.get("ema50", 0)
        trend = coin.get("trend", "SIDEWAYS")
        trend_icon = coin.get("trend_icon", "➡️")
        support = coin.get("support", 0)
        resistance = coin.get("resistance", 0)
        atr = coin.get("atr", 0)
        bid = coin.get("bid", 0)
        ask = coin.get("ask", 0)

        score, reasons, label = score_setup(coin)

        if score < 9 and not force:
            return None

        tp = trade_plan(coin)
        timing = get_timing(coin)
        market_cond = get_market_condition(coin)

        sid = uid(symbol + str(price))

        spread = round((ask - bid) / bid * 100, 3) if bid > 0 else 0

        text = (
            f"⚡ *MEME EXPRESS SIGNAL* ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 *${symbol}/USDT* — Bybit Spot\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Price: `{fmtp(price)}`\n"
            f"📊 1H: `{ch1h:+.2f}%`\n"
            f"📊 4H: `{ch4h:+.2f}%`\n"
            f"📊 24H: `{ch24h:+.2f}%`\n"
            f"🕯 24H High: `{fmtp(high_24h)}`\n"
            f"🕯 24H Low: `{fmtp(low_24h)}`\n"
            f"{trend_icon} Trend: *{trend}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 *WHY THIS SETUP ({score}/15):*\n"
        )

        for r in reasons:
            text += f"  • {r}\n"

        text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Rating: {label}\n"
            f"⏱ *WHEN TO TRADE:*\n"
            f"{timing}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌍 *MARKET CONDITIONS:*\n"
            f"{market_cond}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )

        if tp:
            text += (
                f"📐 *TRADE PLAN ({tp['direction']})*\n"
                f"🎯 Entry:     `{fmtp(tp['entry'])}`\n"
                f"✅ TP1:       `{fmtp(tp['tp1'])}` (`{tp['tp1_pct']:+.1f}%`)\n"
                f"✅ TP2:       `{fmtp(tp['tp2'])}` (`{tp['tp2_pct']:+.1f}%`)\n"
                f"🛑 Stop Loss: `{fmtp(tp['sl'])}` (`{tp['sl_pct']:+.1f}%`)\n"
                f"⚖️ R:R Ratio: `1:{tp['rr']}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
            )

        text += (
            f"📊 *KEY LEVELS:*\n"
            f"Support:    `{fmtp(support)}`\n"
            f"Resistance: `{fmtp(resistance)}`\n"
            f"ATR:        `{fmtp(atr)}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *INDICATORS:*\n"
            f"RSI 1H: `{rsi_1h}` | RSI 15M: `{rsi_15m}`\n"
            f"Stoch K: `{stoch_k}` | BB Width: `{bb.get('width', 0)}%`\n"
            f"BB Upper: `{fmtp(bb.get('upper', 0))}`\n"
            f"BB Lower: `{fmtp(bb.get('lower', 0))}`\n"
            f"MACD: `{macd.get('macd', 0):.8f}`\n"
            f"Signal: `{macd.get('signal', 0):.8f}`\n"
            f"Histogram: `{macd.get('histogram', 0):.8f}`\n"
            f"EMA9: `{fmtp(ema9)}` | EMA21: `{fmtp(ema21)}`\n"
            f"EMA50: `{fmtp(ema50)}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💧 Vol Surge: `{vol_surge}x`\n"
            f"💰 Vol 24H: `{fmtn(vol_24h_usd)}`\n"
            f"📋 Bid: `{fmtp(bid)}` | Ask: `{fmtp(ask)}`\n"
            f"📏 Spread: `{spread}%`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 [Trade on Bybit](https://www.bybit.com/trade/spot/{symbol}/USDT) | "
            f"[Chart](https://www.tradingview.com/chart/?symbol=BYBIT:{symbol}USDT)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ _DYOR. Not financial advice. Always set SL._\n"
            f"📢 @DogeOracle | 🧙 *Meme Express*"
        )

        return text, sid

    except Exception as e:
        logger.error(f"Analyze error: {e}")
        return None

def format_whale(coin: Dict) -> Tuple[str, str]:
    symbol = coin.get("symbol", "???").upper()
    price = coin.get("price", 0)
    ch24h = coin.get("ch24h", 0)
    vol_24h_usd = coin.get("vol_24h_usd", 0)
    label = coin.get("_whale_label", "High Volume Activity")

    aid = uid(symbol + "whale")

    text = (
        f"🐋 *WHALE ALERT* 🐋\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *${symbol}/USDT* — Bybit\n"
        f"🔍 Signal: {label}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Price: `{fmtp(price)}`\n"
        f"📈 24H: `{ch24h:+.2f}%`\n"
        f"💰 Vol 24H: `{fmtn(vol_24h_usd)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 [Trade on Bybit](https://www.bybit.com/trade/spot/{symbol}/USDT)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ _DYOR. Not financial advice._\n"
        f"📢 @DogeOracle | 🧙 *Meme Express*"
    )
    return text, aid

def win_card(token: str, mult: str) -> Tuple[str, str]:
    if not token.startswith("$"):
        token = f"${token}"
    wid = uid(token + mult)
    text = (
        f"🏆 *WIN CARD* 🏆\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Token: *{token.upper()}*\n"
        f"💰 Return: *{mult.upper()}* 🚀\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Called it. We printed it.\n"
        f"Members who followed made it. 💸\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 Want signals before everyone else?\n"
        f"👇 Join: @DogeOracle\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🧙 *Meme Express* | The Alpha Source"
    )
    return text, wid
