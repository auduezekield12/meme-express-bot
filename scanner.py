import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)
DEX = "https://api.dexscreener.com"

CHAINS = {"solana", "ethereum", "bsc", "base", "arbitrum", "avalanche", "polygon"}

QUERIES = [
    # Solana memecoins
    "solana meme", "solana pump", "solana dog", "solana cat",
    "solana pepe", "solana inu", "solana ai", "solana moon",
    "solana based", "solana chad", "solana frog", "solana coin",
    # ETH/Base memecoins
    "ethereum meme", "base meme", "base pump", "ethereum pepe",
    "ethereum dog", "arbitrum meme",
    # BSC memecoins
    "bsc meme", "bsc pump", "bsc dog", "bsc moon", "bsc inu",
    # BTC ecosystem
    "bitcoin meme", "btc ordinals",
    # General
    "pump fun", "trending meme", "new token pump",
]

async def fetch(session: aiohttp.ClientSession, url: str):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        logger.error(f"Fetch error: {e}")
    return None

async def scan_all(mode: str = "signal") -> List[Dict]:
    async with aiohttp.ClientSession() as session:
        all_pairs = []

        # Fetch all search queries concurrently
        tasks = [fetch(session, f"{DEX}/latest/dex/search?q={q}") for q in QUERIES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, dict):
                all_pairs.extend(r.get("pairs", []))

        # Fetch boosted tokens
        boost = await fetch(session, f"{DEX}/token-boosts/top/v1")
        if isinstance(boost, list):
            btasks = [
                fetch(session, f"{DEX}/latest/dex/tokens/{t.get('tokenAddress', '')}")
                for t in boost[:25] if t.get("tokenAddress")
            ]
            bresults = await asyncio.gather(*btasks, return_exceptions=True)
            for br in bresults:
                if isinstance(br, dict):
                    all_pairs.extend(br.get("pairs", []))

        # Fetch newest token profiles
        new = await fetch(session, f"{DEX}/token-profiles/latest/v1")
        if isinstance(new, list):
            ntasks = [
                fetch(session, f"{DEX}/latest/dex/tokens/{t.get('tokenAddress', '')}")
                for t in new[:20] if t.get("tokenAddress")
            ]
            nresults = await asyncio.gather(*ntasks, return_exceptions=True)
            for nr in nresults:
                if isinstance(nr, dict):
                    all_pairs.extend(nr.get("pairs", []))

        # Deduplicate
        seen = set()
        unique = []
        for p in all_pairs:
            pid = p.get("pairAddress", "")
            chain = p.get("chainId", "")
            if pid and pid not in seen and chain in CHAINS:
                seen.add(pid)
                unique.append(p)

        if mode == "trending":
            unique.sort(key=lambda x: x.get("volume", {}).get("h24", 0) or 0, reverse=True)
            return unique[:30]

        # Score and filter
        signals = []
        for p in unique:
            try:
                ch5m = p.get("priceChange", {}).get("m5", 0) or 0
                ch1 = p.get("priceChange", {}).get("h1", 0) or 0
                ch6 = p.get("priceChange", {}).get("h6", 0) or 0
                ch24 = p.get("priceChange", {}).get("h24", 0) or 0
                vol1 = p.get("volume", {}).get("h1", 0) or 0
                vol24 = p.get("volume", {}).get("h24", 0) or 0
                liq = p.get("liquidity", {}).get("usd", 0) or 0
                buys = p.get("txns", {}).get("h1", {}).get("buys", 0)
                sells = p.get("txns", {}).get("h1", {}).get("sells", 0)
                buys5m = p.get("txns", {}).get("m5", {}).get("buys", 0)
                sells5m = p.get("txns", {}).get("m5", {}).get("sells", 0)

                if liq < 3000 or vol1 < 1000:
                    continue
                if ch1 <= 0 and ch5m <= 0 and ch6 <= 0:
                    continue
                if ch1 < -60 or ch24 < -90:
                    continue

                score = 0
                score += min(ch1 / 4, 12)
                score += min(ch5m / 2, 6)
                score += min(ch6 / 8, 5)
                score += min(vol1 / 3000, 10)
                score += min(liq / 8000, 6)
                if buys > sells:
                    score += 5
                if buys5m > sells5m:
                    score += 4
                if ch5m > 5:
                    score += 3
                if ch1 > 20:
                    score += 4
                if ch6 > 30:
                    score += 3
                avg_h = vol24 / 24 if vol24 > 0 else 0
                if avg_h > 0:
                    surge = vol1 / avg_h
                    score += min(surge * 2, 8)

                p["_score"] = round(score, 2)
                signals.append(p)
            except Exception:
                continue

        signals.sort(key=lambda x: x.get("_score", 0), reverse=True)
        return signals[:25]

async def scan_whales() -> List[Dict]:
    async with aiohttp.ClientSession() as session:
        results = []
        boost = await fetch(session, f"{DEX}/token-boosts/top/v1")
        new = await fetch(session, f"{DEX}/token-profiles/latest/v1")
        tokens = (boost if isinstance(boost, list) else [])[:15]
        tokens += (new if isinstance(new, list) else [])[:15]

        valid = [t for t in tokens if t.get("tokenAddress") and t.get("chainId") in CHAINS]
        tasks = [fetch(session, f"{DEX}/latest/dex/tokens/{t['tokenAddress']}") for t in valid]
        res = await asyncio.gather(*tasks, return_exceptions=True)

        for i, r in enumerate(res):
            try:
                if not isinstance(r, dict):
                    continue
                pairs = r.get("pairs", [])
                if not pairs:
                    continue
                top = pairs[0]
                vol1 = top.get("volume", {}).get("h1", 0) or 0
                liq = top.get("liquidity", {}).get("usd", 0) or 0
                if vol1 > 3000 and liq > 2000:
                    top["_whale_label"] = "Smart Money / Boosted"
                    top["_boost"] = valid[i].get("amount", 0)
                    results.append(top)
            except Exception:
                continue

        results.sort(key=lambda x: x.get("volume", {}).get("h1", 0) or 0, reverse=True)
        return results[:10]

async def fetch_by_address(address: str) -> Optional[Dict]:
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, f"{DEX}/latest/dex/tokens/{address}")
        pairs = (data or {}).get("pairs", [])
        if not pairs:
            return None
        pairs.sort(key=lambda x: x.get("volume", {}).get("h24", 0) or 0, reverse=True)
        return pairs[0]

async def market_overview() -> str:
    async with aiohttp.ClientSession() as session:
        all_pairs = []
        qs = ["solana meme", "ethereum meme", "bsc meme", "base meme", "solana pump"]
        tasks = [fetch(session, f"{DEX}/latest/dex/search?q={q}") for q in qs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, dict):
                all_pairs.extend(r.get("pairs", []))

        seen = set()
        pairs = []
        for p in all_pairs:
            pid = p.get("pairAddress", "")
            if pid and pid not in seen and p.get("chainId") in CHAINS:
                seen.add(pid)
                pairs.append(p)

        if not pairs:
            return "❌ Could not fetch market data."

        gainers = [p for p in pairs if (p.get("priceChange", {}).get("h1", 0) or 0) > 0]
        losers = [p for p in pairs if (p.get("priceChange", {}).get("h1", 0) or 0) < 0]
        hot5m = [p for p in pairs if (p.get("priceChange", {}).get("m5", 0) or 0) > 5]
        vol1h = sum(p.get("volume", {}).get("h1", 0) or 0 for p in pairs[:100])
        vol24h = sum(p.get("volume", {}).get("h24", 0) or 0 for p in pairs[:100])
        bull = len(gainers) / len(pairs) * 100 if pairs else 0
        avg1h = sum(p.get("priceChange", {}).get("h1", 0) or 0 for p in pairs[:50]) / min(50, len(pairs))
        avg5m = sum(p.get("priceChange", {}).get("m5", 0) or 0 for p in pairs[:50]) / min(50, len(pairs))

        if bull > 60 and avg1h > 3:
            sent = "🟢 BULLISH"
            advice = "Market pumping. Enter strong setups with volume confirmation."
        elif bull > 55:
            sent = "🟢 MILDLY BULLISH"
            advice = "Selective buying. Focus on tokens already breaking out."
        elif bull > 45:
            sent = "🟡 NEUTRAL"
            advice = "Mixed. Only trade setups with clear TP and SL."
        elif avg5m > 2:
            sent = "🟡 RECOVERING"
            advice = "Short term bounce forming. Wait for confirmation."
        else:
            sent = "🔴 BEARISH"
            advice = "Market bleeding. Avoid entries. Protect capital."

        def top_movers(chain_filter, label):
            filtered = [p for p in pairs if p.get("chainId") in chain_filter]
            top = sorted(filtered, key=lambda x: x.get("priceChange", {}).get("h1", 0) or 0, reverse=True)[:3]
            if not top:
                return ""
            out = f"\n*{label}:*\n"
            for p in top:
                sym = p.get("baseToken", {}).get("symbol", "???")
                ch = p.get("priceChange", {}).get("h1", 0) or 0
                out += f"  🔥 ${sym}: `{ch:+.1f}%`\n"
            return out

        return (
            "🌍 *MULTI-CHAIN MARKET OVERVIEW*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Sentiment: *{sent}*\n"
            f"📈 Gainers: `{len(gainers)}` | 📉 Losers: `{len(losers)}`\n"
            f"⚡ Hot 5M: `{len(hot5m)}` tokens\n"
            f"💹 Bull Ratio: `{bull:.1f}%`\n"
            f"📊 Avg 1H: `{avg1h:+.2f}%` | 5M: `{avg5m:+.2f}%`\n"
            f"💰 Vol 1H: `${vol1h:,.0f}`\n"
            f"💰 Vol 24H: `${vol24h:,.0f}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *Advice:* {advice}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🚀 *Top Movers:*"
            f"{top_movers(['solana'], '⚡ Solana')}"
            f"{top_movers(['ethereum', 'base', 'arbitrum'], '🔷 ETH/Base/ARB')}"
            f"{top_movers(['bsc'], '🟡 BSC')}"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📢 @DogeOracle | 🧙 Meme Express"
        )
