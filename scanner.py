import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)
DEXSCREENER = "https://api.dexscreener.com"

async def fetch(session: aiohttp.ClientSession, url: str):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        logger.error(f"Fetch error {url}: {e}")
    return None

async def scan_trending_tokens(mode: str = "signal") -> List[Dict]:
    async with aiohttp.ClientSession() as session:
        all_pairs = []

        # Cast a wide net — memecoins, altcoins, all categories
        queries = [
            "solana meme", "solana pump", "solana dog", "solana cat",
            "solana pepe", "solana inu", "solana ai", "solana baby",
            "solana moon", "solana elon", "solana based", "solana chad",
            "solana wojak", "solana frog", "solana coin",
            # Altcoins
            "ethereum meme", "ethereum alt", "base meme", "base pump",
            "bsc meme", "bsc pump", "bsc dog", "bsc moon",
            "arbitrum meme", "avalanche meme",
            # General pump keywords
            "pump fun", "new token", "trending",
        ]

        # Fetch all queries concurrently for speed
        async def fetch_query(q):
            data = await fetch(session, f"{DEXSCREENER}/latest/dex/search?q={q}")
            return (data or {}).get("pairs", [])

        tasks = [fetch_query(q) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_pairs.extend(r)

        # Pull boosted tokens across all chains
        boost_data = await fetch(session, f"{DEXSCREENER}/token-boosts/top/v1")
        if isinstance(boost_data, list):
            boost_tasks = []
            for token in boost_data[:30]:
                addr = token.get("tokenAddress", "")
                if addr:
                    boost_tasks.append(fetch(session, f"{DEXSCREENER}/latest/dex/tokens/{addr}"))
            boost_results = await asyncio.gather(*boost_tasks, return_exceptions=True)
            for br in boost_results:
                if isinstance(br, dict):
                    all_pairs.extend(br.get("pairs", []))

        # Pull latest new token profiles
        new_data = await fetch(session, f"{DEXSCREENER}/token-profiles/latest/v1")
        if isinstance(new_data, list):
            new_tasks = []
            for token in new_data[:20]:
                addr = token.get("tokenAddress", "")
                if addr:
                    new_tasks.append(fetch(session, f"{DEXSCREENER}/latest/dex/tokens/{addr}"))
            new_results = await asyncio.gather(*new_tasks, return_exceptions=True)
            for nr in new_results:
                if isinstance(nr, dict):
                    all_pairs.extend(nr.get("pairs", []))

        # Supported chains — Solana + major EVM chains
        supported_chains = {
            "solana", "ethereum", "bsc", "base",
            "arbitrum", "avalanche", "polygon", "optimism"
        }

        # Deduplicate
        seen = set()
        unique = []
        for p in all_pairs:
            pid = p.get("pairAddress", "")
            chain = p.get("chainId", "")
            if pid and pid not in seen and chain in supported_chains:
                seen.add(pid)
                unique.append(p)

        if mode == "trending":
            unique.sort(key=lambda x: x.get("volume", {}).get("h24", 0) or 0, reverse=True)
            return unique[:30]

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

                # Minimum quality bar
                if liq < 3000:
                    continue
                if vol1 < 1000:
                    continue

                # Must have some positive momentum somewhere
                if ch1 <= 0 and ch5m <= 0 and ch6 <= 0 and ch24 <= 0:
                    continue

                # Filter obvious rugs
                if ch1 < -60 or ch24 < -90:
                    continue

                # Score
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
                    score += 3  # strong 5m momentum bonus
                if ch1 > 20:
                    score += 4  # strong 1h bonus
                if ch6 > 30:
                    score += 3  # 6h trend confirmation

                avg_hourly = vol24 / 24 if vol24 > 0 else 0
                if avg_hourly > 0:
                    surge = vol1 / avg_hourly
                    score += min(surge * 2, 8)

                p["_score"] = round(score, 2)
                p["_chain"] = p.get("chainId", "solana")
                signals.append(p)

            except Exception:
                continue

        signals.sort(key=lambda x: x.get("_score", 0), reverse=True)
        return signals[:25]  # top 25 candidates for analysis

async def scan_whale_activity() -> List[Dict]:
    async with aiohttp.ClientSession() as session:
        results = []

        boost_data = await fetch(session, f"{DEXSCREENER}/token-boosts/top/v1")
        boosted = boost_data if isinstance(boost_data, list) else []

        new_data = await fetch(session, f"{DEXSCREENER}/token-profiles/latest/v1")
        newest = new_data if isinstance(new_data, list) else []

        all_tokens = boosted[:15] + newest[:15]

        supported = {"solana", "ethereum", "bsc", "base", "arbitrum", "avalanche"}

        fetch_tasks = []
        valid_tokens = []
        for token in all_tokens:
            addr = token.get("tokenAddress", "")
            chain = token.get("chainId", "")
            if addr and chain in supported:
                fetch_tasks.append(fetch(session, f"{DEXSCREENER}/latest/dex/tokens/{addr}"))
                valid_tokens.append(token)

        pair_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        for i, pr in enumerate(pair_results):
            try:
                if not isinstance(pr, dict):
                    continue
                pairs = pr.get("pairs", [])
                if not pairs:
                    continue
                top = pairs[0]
                vol1 = top.get("volume", {}).get("h1", 0) or 0
                liq = top.get("liquidity", {}).get("usd", 0) or 0
                ch1 = top.get("priceChange", {}).get("h1", 0) or 0
                if vol1 > 3000 and liq > 2000:
                    top["_whale_label"] = "Smart Money / Boosted"
                    top["_boost"] = valid_tokens[i].get("amount", 0)
                    results.append(top)
            except Exception:
                continue

        results.sort(key=lambda x: x.get("volume", {}).get("h1", 0) or 0, reverse=True)
        return results[:10]

async def fetch_pair_by_address(address: str) -> Optional[Dict]:
    async with aiohttp.ClientSession() as session:
        data = await fetch(session, f"{DEXSCREENER}/latest/dex/tokens/{address}")
        pairs = (data or {}).get("pairs", [])
        if not pairs:
            return None
        pairs.sort(key=lambda x: x.get("volume", {}).get("h24", 0) or 0, reverse=True)
        return pairs[0]

async def get_market_overview() -> str:
    async with aiohttp.ClientSession() as session:
        all_pairs = []
        for q in ["solana meme", "solana pump", "ethereum meme", "bsc meme", "base meme"]:
            data = await fetch(session, f"{DEXSCREENER}/latest/dex/search?q={q}")
            pairs = (data or {}).get("pairs", [])
            all_pairs.extend(pairs)

        supported = {"solana", "ethereum", "bsc", "base", "arbitrum"}
        seen = set()
        all_p = []
        for p in all_pairs:
            pid = p.get("pairAddress", "")
            if pid and pid not in seen and p.get("chainId") in supported:
                seen.add(pid)
                all_p.append(p)

        if not all_p:
            return "Could not fetch market data right now."

        gainers = [p for p in all_p if (p.get("priceChange", {}).get("h1", 0) or 0) > 0]
        losers = [p for p in all_p if (p.get("priceChange", {}).get("h1", 0) or 0) < 0]
        hot_5m = [p for p in all_p if (p.get("priceChange", {}).get("m5", 0) or 0) > 5]
        total_vol_1h = sum(p.get("volume", {}).get("h1", 0) or 0 for p in all_p[:100])
        total_vol_24h = sum(p.get("volume", {}).get("h24", 0) or 0 for p in all_p[:100])

        bull_pct = len(gainers) / len(all_p) * 100 if all_p else 0
        avg_1h = sum(p.get("priceChange", {}).get("h1", 0) or 0 for p in all_p[:50]) / min(50, len(all_p))
        avg_5m = sum(p.get("priceChange", {}).get("m5", 0) or 0 for p in all_p[:50]) / min(50, len(all_p))

        if bull_pct > 60 and avg_1h > 3:
            sentiment = "🟢 BULLISH"
            advice = "Market pumping. Enter strong setups with volume confirmation."
        elif bull_pct > 55:
            sentiment = "🟢 MILDLY BULLISH"
            advice = "Selective buying. Focus on coins already breaking out."
        elif bull_pct > 45:
            sentiment = "🟡 NEUTRAL"
            advice = "Mixed. Only trade setups with clear TP and SL."
        elif avg_5m > 2:
            sentiment = "🟡 RECOVERING"
            advice = "Short term bounce forming. Watch closely for confirmation."
        else:
            sentiment = "🔴 BEARISH"
            advice = "Market bleeding. Avoid entries. Protect capital."

        # Top movers per chain
        sol_top = sorted(
            [p for p in all_p if p.get("chainId") == "solana"],
            key=lambda x: x.get("priceChange", {}).get("h1", 0) or 0, reverse=True
        )[:3]
        eth_top = sorted(
            [p for p in all_p if p.get("chainId") in ("ethereum", "base", "arbitrum")],
            key=lambda x: x.get("priceChange", {}).get("h1", 0) or 0, reverse=True
        )[:3]
        bsc_top = sorted(
            [p for p in all_p if p.get("chainId") == "bsc"],
            key=lambda x: x.get("priceChange", {}).get("h1", 0) or 0, reverse=True
        )[:3]

        def chain_lines(pairs, label):
            if not pairs:
                return ""
            lines = f"\n*{label}:*\n"
            for p in pairs:
                sym = p.get("baseToken", {}).get("symbol", "???")
                ch = p.get("priceChange", {}).get("h1", 0) or 0
                lines += f"  🔥 ${sym}: `{ch:+.1f}%`\n"
            return lines

        return (
            "🌍 *MULTI-CHAIN MARKET OVERVIEW*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Sentiment: *{sentiment}*\n"
            f"📈 Gainers: `{len(gainers)}` | 📉 Losers: `{len(losers)}`\n"
            f"⚡ Hot 5M: `{len(hot_5m)}` tokens +5% in 5min\n"
            f"💹 Bull Ratio: `{bull_pct:.1f}%`\n"
            f"📊 Avg 1H: `{avg_1h:+.2f}%` | 5M: `{avg_5m:+.2f}%`\n"
            f"💰 Vol 1H: `${total_vol_1h:,.0f}`\n"
            f"💰 Vol 24H: `${total_vol_24h:,.0f}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *Advice:* {advice}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🚀 *Top Movers:*"
            f"{chain_lines(sol_top, '⚡ Solana')}"
            f"{chain_lines(eth_top, '🔷 ETH/Base/Arb')}"
            f"{chain_lines(bsc_top, '🟡 BSC')}"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📢 @DogeOracle | 🧙 Meme Express"
        )
