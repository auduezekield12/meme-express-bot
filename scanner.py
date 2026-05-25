import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# All major altcoins and memecoins available on Bybit
BYBIT_COINS = [
    # Major coins
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOT", "MATIC",
    "LINK", "UNI", "ATOM", "LTC", "BCH", "NEAR", "APT", "ARB", "OP",
    "INJ", "SUI", "SEI", "TIA", "JUP", "PYTH", "WEN", "STRK",
    # Memecoins on Bybit
    "DOGE", "SHIB", "PEPE", "FLOKI", "BONK", "WIF", "BOME", "BRETT",
    "MEME", "NEIRO", "POPCAT", "MOG", "TURBO", "BABYDOGE", "SAMO",
    "MYRO", "SLERF", "PONKE", "BOOK", "GIGA", "PNUT", "ACT", "GOAT",
    "MOODENG", "CHILLGUY", "KEKIUS", "FWOG", "ORCA", "TRUMP", "MELANIA",
    # More alts
    "FET", "RENDER", "TAO", "WLD", "RNDR", "GRT", "SAND", "MANA",
    "AXS", "IMX", "GALA", "ENJ", "CHZ", "FLOW", "ROSE", "ONE",
    "ZIL", "VET", "HBAR", "ALGO", "XLM", "EOS", "TRX", "XTZ",
    "AAVE", "CRV", "MKR", "SNX", "COMP", "YFI", "SUSHI", "1INCH",
    "LDO", "RPL", "FXS", "CVX", "BAL", "DYDX", "GMX", "PERP",
    "BLUR", "NFT", "LOOKS", "X2Y2", "MAGIC", "TRB", "BAND",
    "API3", "UMA", "BAT", "ENS", "AUDIO", "MASK", "RAY", "ORCA",
    "MNGO", "STEP", "COPE", "MEDIA", "SRM", "FIDA", "KIN",
    # New trending
    "VIRTUAL", "AI16Z", "ZEREBRO", "AIXBT", "GRIFFAIN", "DEVIN",
    "ARC", "SWARMS", "ELIZA", "GRIFT", "LUNA", "LUNC", "UST",
    "STX", "ORDI", "SATS", "RATS", "PIZZA", "MUBI", "BIKE",
]

COINGECKO_API = "https://api.coingecko.com/api/v3"
BYBIT_API = "https://api.bybit.com/v5/market"

async def fetch(session: aiohttp.ClientSession, url: str, params: dict = None):
    try:
        async with session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        logger.error(f"Fetch error {url}: {e}")
    return None

async def get_bybit_ticker(session: aiohttp.ClientSession, symbol: str) -> Optional[Dict]:
    """Get ticker data from Bybit for a specific symbol"""
    data = await fetch(session, f"{BYBIT_API}/tickers", params={
        "category": "spot",
        "symbol": f"{symbol}USDT"
    })
    if not data:
        return None
    result = data.get("result", {})
    tickers = result.get("list", [])
    if tickers:
        return tickers[0]
    return None

async def get_bybit_klines(session: aiohttp.ClientSession, symbol: str, interval: str = "60", limit: int = 50) -> List:
    """Get candlestick data from Bybit"""
    data = await fetch(session, f"{BYBIT_API}/kline", params={
        "category": "spot",
        "symbol": f"{symbol}USDT",
        "interval": interval,
        "limit": limit
    })
    if not data:
        return []
    return data.get("result", {}).get("list", [])

def calculate_rsi(closes: List[float], period: int = 14) -> float:
    """Calculate real RSI from candlestick closes"""
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_ema(closes: List[float], period: int) -> float:
    """Calculate EMA"""
    if len(closes) < period:
        return closes[-1] if closes else 0
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema
    return round(ema, 8)

def calculate_bb(closes: List[float], period: int = 20) -> Dict:
    """Calculate Bollinger Bands"""
    if len(closes) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "width": 0}
    recent = closes[-period:]
    middle = sum(recent) / period
    variance = sum((x - middle) ** 2 for x in recent) / period
    std = variance ** 0.5
    upper = middle + (2 * std)
    lower = middle - (2 * std)
    width = round(((upper - lower) / middle) * 100, 2) if middle > 0 else 0
    return {"upper": upper, "middle": middle, "lower": lower, "width": width}

def calculate_macd(closes: List[float]) -> Dict:
    """Calculate MACD"""
    if len(closes) < 26:
        return {"macd": 0, "signal": 0, "histogram": 0}
    ema12 = calculate_ema(closes, 12)
    ema26 = calculate_ema(closes, 26)
    macd = ema12 - ema26
    # Simplified signal
    signal = macd * 0.9
    histogram = macd - signal
    return {
        "macd": round(macd, 8),
        "signal": round(signal, 8),
        "histogram": round(histogram, 8)
    }

async def analyze_coin(session: aiohttp.ClientSession, symbol: str) -> Optional[Dict]:
    """Full technical analysis for a Bybit-listed coin"""
    try:
        # Get ticker
        ticker = await get_bybit_ticker(session, symbol)
        if not ticker:
            return None

        price = float(ticker.get("lastPrice", 0))
        if price == 0:
            return None

        price_24h_ago = float(ticker.get("prevPrice24h", price))
        high_24h = float(ticker.get("highPrice24h", price))
        low_24h = float(ticker.get("lowPrice24h", price))
        vol_24h = float(ticker.get("volume24h", 0))
        vol_24h_usd = float(ticker.get("turnover24h", 0))
        bid = float(ticker.get("bid1Price", price))
        ask = float(ticker.get("ask1Price", price))

        ch24h = ((price - price_24h_ago) / price_24h_ago * 100) if price_24h_ago > 0 else 0

        # Get 1h candles for indicators
        klines_1h = await get_bybit_klines(session, symbol, "60", 50)
        await asyncio.sleep(0.1)
        klines_15m = await get_bybit_klines(session, symbol, "15", 50)

        closes_1h = []
        volumes_1h = []
        for k in reversed(klines_1h):
            try:
                closes_1h.append(float(k[4]))
                volumes_1h.append(float(k[5]))
            except:
                continue

        closes_15m = []
        for k in reversed(klines_15m):
            try:
                closes_15m.append(float(k[4]))
            except:
                continue

        if len(closes_1h) < 10:
            return None

        # Calculate real indicators
        rsi_1h = calculate_rsi(closes_1h, 14)
        rsi_15m = calculate_rsi(closes_15m, 14) if len(closes_15m) > 14 else rsi_1h
        bb = calculate_bb(closes_1h, 20)
        macd = calculate_macd(closes_1h)
        ema9 = calculate_ema(closes_1h, 9)
        ema21 = calculate_ema(closes_1h, 21)
        ema50 = calculate_ema(closes_1h, 50) if len(closes_1h) >= 50 else ema21

        # Price changes from candles
        ch1h = ((closes_1h[-1] - closes_1h[-2]) / closes_1h[-2] * 100) if len(closes_1h) >= 2 else 0
        ch4h = ((closes_1h[-1] - closes_1h[-4]) / closes_1h[-4] * 100) if len(closes_1h) >= 4 else 0

        # Volume analysis
        avg_vol = sum(volumes_1h[-20:]) / 20 if len(volumes_1h) >= 20 else 0
        curr_vol = volumes_1h[-1] if volumes_1h else 0
        vol_surge = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 1.0

        # Stochastic RSI
        stoch_k = round(min(max((rsi_1h - 20) / 60 * 100, 0), 100), 1)

        # Trend determination using EMAs
        if ema9 > ema21 > ema50 and price > ema9:
            trend = "STRONG UPTREND"
            trend_icon = "🚀"
        elif ema9 > ema21 and price > ema21:
            trend = "UPTREND"
            trend_icon = "📈"
        elif ema9 < ema21 < ema50 and price < ema9:
            trend = "STRONG DOWNTREND"
            trend_icon = "📉"
        elif ema9 < ema21:
            trend = "DOWNTREND"
            trend_icon = "🔻"
        else:
            trend = "SIDEWAYS"
            trend_icon = "➡️"

        # BB position
        bb_position = "MIDDLE"
        if price >= bb["upper"] * 0.98:
            bb_position = "UPPER"
        elif price <= bb["lower"] * 1.02:
            bb_position = "LOWER"

        # Support and resistance from 24h
        support = low_24h
        resistance = high_24h
        atr = (high_24h - low_24h) * 0.1

        return {
            "symbol": symbol,
            "price": price,
            "ch1h": round(ch1h, 2),
            "ch4h": round(ch4h, 2),
            "ch24h": round(ch24h, 2),
            "high_24h": high_24h,
            "low_24h": low_24h,
            "vol_24h": vol_24h,
            "vol_24h_usd": vol_24h_usd,
            "vol_surge": vol_surge,
            "rsi_1h": rsi_1h,
            "rsi_15m": rsi_15m,
            "stoch_k": stoch_k,
            "bb": bb,
            "bb_position": bb_position,
            "macd": macd,
            "ema9": ema9,
            "ema21": ema21,
            "ema50": ema50,
            "trend": trend,
            "trend_icon": trend_icon,
            "support": support,
            "resistance": resistance,
            "atr": atr,
            "bid": bid,
            "ask": ask,
        }

    except Exception as e:
        logger.error(f"analyze_coin error {symbol}: {e}")
        return None

async def scan_all(mode: str = "signal") -> List[Dict]:
    """Scan all Bybit coins for signals"""
    async with aiohttp.ClientSession() as session:
        # Batch coins to avoid rate limiting
        results = []
        batch_size = 10

        for i in range(0, len(BYBIT_COINS), batch_size):
            batch = BYBIT_COINS[i:i+batch_size]
            tasks = [analyze_coin(session, sym) for sym in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in batch_results:
                if isinstance(r, dict) and r is not None:
                    results.append(r)
            await asyncio.sleep(0.5)

        if mode == "trending":
            results.sort(key=lambda x: abs(x.get("ch24h", 0)), reverse=True)
            return results[:20]

        # Score each coin
        signals = []
        for coin in results:
            score = score_coin(coin)
            if score > 0:
                coin["_score"] = score
                signals.append(coin)

        signals.sort(key=lambda x: x.get("_score", 0), reverse=True)
        return signals[:20]

def score_coin(coin: Dict) -> float:
    """Score a Bybit coin based on real technical indicators"""
    score = 0.0
    rsi = coin.get("rsi_1h", 50)
    stoch = coin.get("stoch_k", 50)
    trend = coin.get("trend", "")
    vol_surge = coin.get("vol_surge", 1)
    bb_pos = coin.get("bb_position", "MIDDLE")
    macd = coin.get("macd", {})
    ch1h = coin.get("ch1h", 0)
    ch24h = coin.get("ch24h", 0)

    # Must have some positive momentum
    if ch1h <= 0 and ch24h <= 0:
        return 0

    # RSI scoring
    if rsi < 30:
        score += 2.5
    elif rsi < 40:
        score += 1.5
    elif 40 <= rsi <= 60:
        score += 1.0
    elif rsi > 70:
        score += 2.0

    # Stoch RSI
    if stoch < 20:
        score += 1.5
    elif stoch > 80:
        score += 1.5

    # Bollinger Bands
    if bb_pos == "UPPER":
        score += 2.0
    elif bb_pos == "LOWER":
        score += 1.5

    # Trend
    if trend == "STRONG UPTREND":
        score += 3.0
    elif trend == "UPTREND":
        score += 2.0

    # MACD
    if macd.get("histogram", 0) > 0 and macd.get("macd", 0) > macd.get("signal", 0):
        score += 2.0

    # Volume surge
    if vol_surge > 3:
        score += 2.5
    elif vol_surge > 2:
        score += 1.5
    elif vol_surge > 1.5:
        score += 1.0

    # Price momentum
    if ch1h > 5:
        score += 2.0
    elif ch1h > 2:
        score += 1.0
    if ch24h > 10:
        score += 1.5

    return round(score, 1)

async def scan_whales() -> List[Dict]:
    """Find coins with unusual volume spikes on Bybit"""
    async with aiohttp.ClientSession() as session:
        results = []
        # Get all tickers at once
        data = await fetch(session, f"{BYBIT_API}/tickers", params={"category": "spot"})
        if not data:
            return []
        tickers = data.get("result", {}).get("list", [])

        # Filter USDT pairs with high volume change
        for t in tickers:
            try:
                symbol = t.get("symbol", "")
                if not symbol.endswith("USDT"):
                    continue
                base = symbol.replace("USDT", "")
                if base not in BYBIT_COINS:
                    continue

                price = float(t.get("lastPrice", 0))
                vol_usd = float(t.get("turnover24h", 0))
                ch24h = float(t.get("price24hPcnt", 0)) * 100

                if vol_usd > 1_000_000 and ch24h > 5:
                    results.append({
                        "symbol": base,
                        "price": price,
                        "ch24h": round(ch24h, 2),
                        "vol_24h_usd": vol_usd,
                        "_whale_label": "High Volume Spike",
                        "_boost": vol_usd
                    })
            except Exception:
                continue

        results.sort(key=lambda x: x.get("vol_24h_usd", 0), reverse=True)
        return results[:10]

async def fetch_by_address(symbol: str) -> Optional[Dict]:
    """Fetch a specific coin by symbol"""
    async with aiohttp.ClientSession() as session:
        return await analyze_coin(session, symbol.upper().replace("USDT", "").replace("$", ""))

async def market_overview() -> str:
    """Get overall Bybit market conditions"""
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, f"{BYBIT_API}/tickers", params={"category": "spot"})
        if not data:
            return "❌ Could not fetch market data."

        tickers = data.get("result", {}).get("list", [])
        usdt_pairs = [t for t in tickers if t.get("symbol", "").endswith("USDT")]

        gainers = []
        losers = []
        total_vol = 0

        for t in usdt_pairs:
            try:
                ch = float(t.get("price24hPcnt", 0)) * 100
                vol = float(t.get("turnover24h", 0))
                total_vol += vol
                if ch > 0:
                    gainers.append(t)
                else:
                    losers.append(t)
            except:
                continue

        bull_pct = len(gainers) / len(usdt_pairs) * 100 if usdt_pairs else 50

        # Get BTC and ETH specifically
        btc = next((t for t in tickers if t.get("symbol") == "BTCUSDT"), None)
        eth = next((t for t in tickers if t.get("symbol") == "ETHUSDT"), None)
        sol = next((t for t in tickers if t.get("symbol") == "SOLUSDT"), None)

        btc_ch = round(float(btc.get("price24hPcnt", 0)) * 100, 2) if btc else 0
        eth_ch = round(float(eth.get("price24hPcnt", 0)) * 100, 2) if eth else 0
        sol_ch = round(float(sol.get("price24hPcnt", 0)) * 100, 2) if sol else 0
        btc_price = float(btc.get("lastPrice", 0)) if btc else 0

        # Top gainers from Bybit coins
        our_coins = [t for t in usdt_pairs if t.get("symbol", "").replace("USDT", "") in BYBIT_COINS]
        top5 = sorted(our_coins, key=lambda x: float(x.get("price24hPcnt", 0)), reverse=True)[:5]

        if bull_pct > 60 and btc_ch > 1:
            sentiment = "🟢 BULLISH"
            advice = "Market is up. Look for breakouts with volume confirmation."
        elif bull_pct > 55:
            sentiment = "🟢 MILDLY BULLISH"
            advice = "Selective buying. Focus on coins already trending."
        elif bull_pct > 45:
            sentiment = "🟡 NEUTRAL"
            advice = "Mixed market. Only trade high conviction setups."
        elif btc_ch < -3:
            sentiment = "🔴 BEARISH"
            advice = "BTC dumping. Avoid entries. Wait for stabilization."
        else:
            sentiment = "🔴 BEARISH"
            advice = "More losers than winners. Protect capital."

        top5_lines = ""
        for t in top5:
            sym = t.get("symbol", "").replace("USDT", "")
            ch = round(float(t.get("price24hPcnt", 0)) * 100, 2)
            price = float(t.get("lastPrice", 0))
            top5_lines += f"  🔥 ${sym}: `{ch:+.2f}%` @ `${price:,.4f}`\n"

        return (
            "🌍 *BYBIT MARKET OVERVIEW*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Sentiment: *{sentiment}*\n"
            f"📈 Gainers: `{len(gainers)}` | 📉 Losers: `{len(losers)}`\n"
            f"💹 Bull Ratio: `{bull_pct:.1f}%`\n"
            f"💰 Total Vol 24H: `${total_vol:,.0f}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📊 *Major Coins:*\n"
            f"  ₿ BTC: `{btc_ch:+.2f}%` @ `${btc_price:,.0f}`\n"
            f"  Ξ ETH: `{eth_ch:+.2f}%`\n"
            f"  ◎ SOL: `{sol_ch:+.2f}%`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *Advice:* {advice}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 *Top Gainers (24H):*\n{top5_lines}"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📢 @DogeOracle | 🧙 Meme Express"
        )
