import hashlib
import time
import logging
from typing import Dict, Tuple, Optional, List

logger = logging.getLogger(__name__)

def uid(s: str) -> str:
    return hashlib.md5(f"{s}{time.time()}".encode()).hexdigest()[:8]

def fmtn(n: float) -> str:
    if n >= 1_000_000: return f"${n/1_000_000:.2f}M"
    if n >= 1_000: return f"${n/1_000:.1f}K"
    return f"${n:.0f}"

def fmtp(p: float) -> str:
    if p == 0: return "$0"
    if p < 0.000001: return f"${p:.10f}"
    if p < 0.0001: return f"${p:.8f}"
    if p < 0.01: return f"${p:.6f}"
    if p < 1: return f"${p:.4f}"
    return f"${p:.4f}"

def calc_rsi(ch5m, ch1h, ch6h, ch24h) -> float:
    changes = [ch24h/6, ch24h/6, ch6h/3, ch6h/3, ch1h/2, ch1h/2, ch5m, ch5m]
    gains = [max(c, 0) for c in changes]
    losses = [abs(min(c, 0)) for c in changes]
    ag = sum(gains) / len(gains)
    al = sum(losses) / len(losses)
    if al == 0: return 100.0
    return round(100 - (100 / (1 + ag / al)), 1)

def get_indicators(pair: Dict) -> Dict:
    ch5m = pair.get("priceChange", {}).get("m5", 0) or 0
    ch1h = pair.get("priceChange", {}).get("h1", 0) or 0
    ch6h = pair.get("priceChange", {}).get("h6", 0) or 0
    ch24h = pair.get("priceChange", {}).get("h24", 0) or 0

    rsi = calc_rsi(ch5m, ch1h, ch6h, ch24h)
    stoch = round(min(max((rsi - 20) / 60 * 100, 0), 100), 1)

    try:
        price = float(pair.get("priceUsd", 0) or 0)
    except:
        price = 0.0

    vol_pct = max(abs(ch1h), abs(ch5m) * 2) * 0.5
    upper_bb = price * (1 + vol_pct / 100) if price > 0 else 0
    lower_bb = price * (1 - vol_pct / 100) if price > 0 else 0
    bb_width = round(vol_pct * 2, 2)
    atr = price * (abs(ch1h) * 0.5 + abs(ch6h) * 0.1) / 100 if price > 0 else 0

    vol1 = pair.get("volume", {}).get("h1", 0) or 0
    vol24 = pair.get("volume", {}).get("h24", 0) or 0
    avg_h = vol24 / 24 if vol24 > 0 else 0
    surge = round(vol1 / avg_h, 1) if avg_h > 0 else 1.0

    if ch1h > 8 and ch6h > 15 and ch24h > 20:
        trend, ticon = "STRONG UPTREND", "🚀"
    elif ch1h > 3 and ch6h > 5:
        trend, ticon = "UPTREND", "📈"
    elif ch1h > 0 and ch5m > 2:
        trend, ticon = "EARLY UPTREND", "📈"
    elif ch1h < -8 and ch6h < -15:
        trend, ticon = "STRONG DOWNTREND", "📉"
    elif ch1h < -3:
        trend, ticon = "DOWNTREND", "🔻"
    else:
        trend, ticon = "SIDEWAYS", "➡️"

    return {
        "rsi": rsi, "stoch": stoch, "upper_bb": upper_bb,
        "lower_bb": lower_bb, "bb_width": bb_width,
        "atr": atr, "surge": surge, "trend": trend,
        "ticon": ticon, "price": price,
    }

def score_setup(pair: Dict, ind: Dict) -> Tuple[float, List[str], str]:
    score = 0.0
    reasons = []

    rsi = ind["rsi"]
    stoch = ind["stoch"]
    trend = ind["trend"]
    surge = ind["surge"]
    price = ind["price"]

    ch5m = pair.get("priceChange", {}).get("m5", 0) or 0
    ch1h = pair.get("priceChange", {}).get("h1", 0) or 0
    ch6h = pair.get("priceChange", {}).get("h6", 0) or 0
    liq = pair.get("liquidity", {}).get("usd", 0) or 0
    buys = pair.get("txns", {}).get("h1", {}).get("buys", 0)
    sells = pair.get("txns", {}).get("h1", {}).get("sells", 0)

    # RSI
    if rsi < 25:
        score += 2.5
        reasons.append(f"RSI severely oversold ({rsi})")
    elif rsi < 35:
        score += 1.5
        reasons.append(f"RSI oversold ({rsi})")
    elif rsi > 70:
        score += 2.0
        reasons.append(f"RSI strong momentum ({rsi})")

    # Stoch RSI
    if stoch < 20:
        score += 1.5
        reasons.append(f"Stoch RSI deeply oversold (K:{stoch})")
    elif stoch > 80:
        score += 1.5
        reasons.append(f"Stoch RSI overbought momentum (K:{stoch})")

    # Bollinger Bands
    if price > 0:
        if price >= ind["upper_bb"] * 0.97:
            score += 2.0
            reasons.append("Price breaking upper Bollinger Band")
        elif price <= ind["lower_bb"] * 1.03:
            score += 1.5
            reasons.append(f"Price at key support (${price:.6f})")

    # Trend
    if trend == "STRONG UPTREND":
        score += 3.0
        reasons.append("Strong uptrend across all timeframes")
    elif trend == "UPTREND":
        score += 2.0
        reasons.append("Uptrend confirmed")
    elif trend == "EARLY UPTREND":
        score += 1.5
        reasons.append(f"Positive 1H momentum (+{ch1h:.1f}%)")

    # Volume surge
    if surge > 4:
        score += 2.5
        reasons.append(f"Massive volume surge {surge}x above average")
    elif surge > 2:
        score += 1.5
        reasons.append(f"Volume surge {surge}x above average")

    # Buy pressure
    total = buys + sells
    if total > 0:
        bp = buys / total
        if bp > 0.70:
            score += 2.0
            reasons.append(f"Heavy buy pressure ({buys} buys vs {sells} sells)")
        elif bp > 0.55:
            score += 1.0
            reasons.append(f"Moderate buy pressure ({buys}/{sells})")

    # Liquidity bonus
    if liq > 100_000:
        score += 1.0
        reasons.append(f"Strong liquidity ({fmtn(liq)})")
    elif liq > 50_000:
        score += 0.5

    # 5m momentum bonus
    if ch5m > 10:
        score += 1.5
        reasons.append(f"Strong 5M pump (+{ch5m:.1f}%)")
    elif ch5m > 5:
        score += 1.0

    # 6h trend confirmation
    if ch6h > 30:
        score += 1.0
        reasons.append(f"6H trend confirmed (+{ch6h:.1f}%)")

    score = round(min(score, 15), 1)

    if score >= 12:
        label = "🔥🔥🔥 VERY STRONG SIGNAL"
    elif score >= 9:
        label = "🔥🔥 STRONG SIGNAL"
    elif score >= 6:
        label = "🔥 MODERATE SIGNAL"
    else:
        label = "👀 WEAK SIGNAL"

    return score, reasons[:5], label

def trade_plan(price: float, atr: float, trend: str, rsi: float) -> Dict:
    if price <= 0:
        return {}
    if atr == 0:
        atr = price * 0.04

    if "UPTREND" in trend and rsi < 75:
        tp1 = price + atr * 2.2
        tp2 = price + atr * 4.5
        sl = price - atr * 1.0
        direction = "LONG 🟢"
    elif rsi < 30:
        tp1 = price + atr * 1.8
        tp2 = price + atr * 3.5
        sl = price - atr * 0.8
        direction = "LONG (Oversold Bounce) 🟡"
    else:
        tp1 = price * 1.12
        tp2 = price * 1.25
        sl = price * 0.95
        direction = "LONG (Wait for Dip) 🟡"

    risk = price - sl
    reward = tp1 - price
    rr = round(reward / risk, 2) if risk > 0 else 0

    return {
        "direction": direction,
        "entry": price,
        "tp1": tp1, "tp1_pct": (tp1 - price) / price * 100,
        "tp2": tp2, "tp2_pct": (tp2 - price) / price * 100,
        "sl": sl, "sl_pct": (sl - price) / price * 100,
        "rr": rr,
    }

def timing(rsi, trend, surge, stoch) -> str:
    if "STRONG UPTREND" in trend and surge > 2 and rsi < 72:
        return "⚡ TRADE NOW — Strong momentum with volume"
    elif "UPTREND" in trend and stoch < 60:
        return "✅ GOOD ENTRY — Trend confirmed, not overbought"
    elif rsi < 28 and stoch < 25:
        return "🎯 OVERSOLD BOUNCE — High probability reversal"
    elif rsi > 78:
        return "⚠️ OVERBOUGHT — Wait for pullback before entry"
    elif "SIDEWAYS" in trend:
        return "⏳ WAIT — Consolidating, no clear direction"
    elif "DOWNTREND" in trend:
        return "🚫 AVOID — Downtrend active. Wait for reversal"
    else:
        return "👀 MONITOR — Setup developing"

async def analyze(pair: Dict, force: bool = False) -> Optional[Tuple[str, str]]:
    try:
        sym = pair.get("baseToken", {}).get("symbol", "???").upper()
        name = pair.get("baseToken", {}).get("name", "")
        pair_addr = pair.get("pairAddress", "")
        base_addr = pair.get("baseToken", {}).get("address", "")
        chain = pair.get("chainId", "solana").upper()
        dex = pair.get("dexId", "unknown").title()

        try:
            price = float(pair.get("priceUsd", 0) or 0)
        except:
            price = 0.0

        ch5m = pair.get("priceChange", {}).get("m5", 0) or 0
        ch1h = pair.get("priceChange", {}).get("h1", 0) or 0
        ch6h = pair.get("priceChange", {}).get("h6", 0) or 0
        ch24h = pair.get("priceChange", {}).get("h24", 0) or 0
        vol1h = pair.get("volume", {}).get("h1", 0) or 0
        vol24h = pair.get("volume", {}).get("h24", 0) or 0
        liq = pair.get("liquidity", {}).get("usd", 0) or 0
        buys = pair.get("txns", {}).get("h1", {}).get("buys", 0)
        sells = pair.get("txns", {}).get("h1", {}).get("sells", 0)
        mcap = pair.get("marketCap", 0) or 0
        fdv = pair.get("fdv", 0) or 0

        created = pair.get("pairCreatedAt")
        age = "Unknown"
        if created:
            ah = (time.time() * 1000 - created) / 3600000
            age = f"{int(ah*60)}m" if ah < 1 else (f"{ah:.1f}h" if ah < 24 else f"{ah/24:.1f}d")

        ind = get_indicators(pair)
        score, reasons, label = score_setup(pair, ind)

        # Block anything below 9 unless forced
        if score < 9 and not force:
            return None

        tp = trade_plan(price, ind["atr"], ind["trend"], ind["rsi"])
        when = timing(ind["rsi"], ind["trend"], ind["surge"], ind["stoch"])

        support = price * 0.93 if price > 0 else 0
        resistance = price * 1.20 if price > 0 else 0

        total = buys + sells
        bp_pct = buys / total * 100 if total > 0 else 50
        pressure = "🟢 Bullish" if bp_pct > 55 else ("🔴 Bearish" if bp_pct < 45 else "⚪ Neutral")

        sid = uid(sym + pair_addr)

        text = (
            f"⚡ *MEME EXPRESS SIGNAL* ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 *${sym}* | {name}\n"
            f"⛓ Chain: `{chain}` | 🏦 {dex} | ⏰ {age}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Price: `{fmtp(price)}`\n"
            f"📊 5M: `{ch5m:+.2f}%`\n"
            f"📊 1H: `{ch1h:+.2f}%`\n"
            f"📊 6H: `{ch6h:+.2f}%`\n"
            f"📊 24H: `{ch24h:+.2f}%`\n"
            f"{ind['ticon']} Trend: *{ind['trend']}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 *WHY THIS SETUP ({score}/15):*\n"
        )
        for r in reasons:
            text += f"  • {r}\n"

        text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Rating: {label}\n"
            f"⏱ *WHEN TO TRADE:* {when}\n"
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
            f"ATR:        `{fmtp(ind['atr'])}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *INDICATORS:*\n"
            f"RSI: `{ind['rsi']}` | Stoch K: `{ind['stoch']}` | BB Width: `{ind['bb_width']}%`\n"
            f"Vol Surge: `{ind['surge']}x` | Buy Pressure: `{bp_pct:.0f}%` {pressure}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💧 Liquidity: `{fmtn(liq)}`\n"
            f"📊 Vol 1H: `{fmtn(vol1h)}` | 24H: `{fmtn(vol24h)}`\n"
            f"🔄 Buys/Sells (1H): `{buys}/{sells}`\n"
        )
        if mcap > 0:
            text += f"💎 Market Cap: `{fmtn(mcap)}`\n"
        if fdv > 0:
            text += f"📦 FDV: `{fmtn(fdv)}`\n"

        text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 [DexScreener](https://dexscreener.com/{chain.lower()}/{pair_addr}) | "
            f"[GMGN](https://gmgn.ai/sol/token/{base_addr}) | "
            f"[Birdeye](https://birdeye.so/token/{base_addr})\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ _DYOR. Not financial advice. Always set SL._\n"
            f"📢 @DogeOracle | 🧙 *Meme Express*"
        )
        return text, sid

    except Exception as e:
        logger.error(f"Analyze error: {e}")
        return None

def format_whale(pair: Dict) -> Tuple[str, str]:
    sym = pair.get("baseToken", {}).get("symbol", "???").upper()
    name = pair.get("baseToken", {}).get("name", "")
    chain = pair.get("chainId", "?").upper()
    try:
        price = float(pair.get("priceUsd", 0) or 0)
    except:
        price = 0.0
    ch1h = pair.get("priceChange", {}).get("h1", 0) or 0
    ch24h = pair.get("priceChange", {}).get("h24", 0) or 0
    vol1h = pair.get("volume", {}).get("h1", 0) or 0
    liq = pair.get("liquidity", {}).get("usd", 0) or 0
    pair_addr = pair.get("pairAddress", "")
    base_addr = pair.get("baseToken", {}).get("address", "")
    label = pair.get("_whale_label", "Smart Money Activity")
    boost = pair.get("_boost", 0)

    aid = uid(sym + "whale")
    text = (
        f"🐋 *WHALE ALERT* 🐋\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 *${sym}* | {name}\n"
        f"⛓ Chain: `{chain}` | Signal: {label}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Price: `{fmtp(price)}`\n"
        f"📈 1H: `{ch1h:+.1f}%` | 24H: `{ch24h:+.1f}%`\n"
        f"💧 Liquidity: `{fmtn(liq)}`\n"
        f"📊 Vol 1H: `{fmtn(vol1h)}`\n"
    )
    if boost:
        text += f"🚀 Boost: `${boost:,}`\n"
    text += (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 [Chart](https://dexscreener.com/{chain.lower()}/{pair_addr}) | "
        f"[GMGN](https://gmgn.ai/sol/token/{base_addr})\n"
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
