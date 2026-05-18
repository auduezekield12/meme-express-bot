import requests
import time
import schedule
import threading
import statistics
from datetime import datetime

BOT_TOKEN = "8013194385:AAHRFcTr2T5kObSxBPQ-tdNw6AzNOGsMes0"
CHAT_ID = CHAT_IDS = "6553775216", "-1003998806451"
BIRDEYE_KEY = "86e20bdc71ea4be996bbf94ffa7e5a90"

MIN_SCORE = 6
RR_MIN = 1.5
COOLDOWN = 3600
SCAN_DELAY = 5

COINS = {
    "bitcoin":            {"name": "Bitcoin",   "sym": "BTC",   "type": "major", "max_lev": 10},
    "ethereum":           {"name": "Ethereum",  "sym": "ETH",   "type": "major", "max_lev": 10},
    "solana":             {"name": "Solana",    "sym": "SOL",   "type": "major", "max_lev": 10},
    "ripple":             {"name": "XRP",       "sym": "XRP",   "type": "major", "max_lev": 10},
    "dogecoin":           {"name": "Dogecoin",  "sym": "DOGE",  "type": "major", "max_lev": 5},
    "pepe":               {"name": "Pepe",      "sym": "PEPE",  "type": "meme",  "max_lev": 5},
    "bonk":               {"name": "Bonk",      "sym": "BONK",  "type": "meme",  "max_lev": 3},
    "dogwifcoin":         {"name": "WIF",       "sym": "WIF",   "type": "meme",  "max_lev": 3},
    "floki":              {"name": "Floki",     "sym": "FLOKI", "type": "meme",  "max_lev": 3},
    "trump-2024":         {"name": "TRUMP",     "sym": "TRUMP", "type": "meme",  "max_lev": 3},
    "avalanche-2":        {"name": "Avalanche", "sym": "AVAX",  "type": "alt",   "max_lev": 5},
    "chainlink":          {"name": "Chainlink", "sym": "LINK",  "type": "alt",   "max_lev": 5},
    "sui":                {"name": "Sui",       "sym": "SUI",   "type": "alt",   "max_lev": 5},
    "injective-protocol": {"name": "Injective", "sym": "INJ",   "type": "alt",   "max_lev": 5},
    "aptos":              {"name": "Aptos",     "sym": "APT",   "type": "alt",   "max_lev": 5},
    "the-open-network":   {"name": "TON",       "sym": "TON",   "type": "alt",   "max_lev": 5},
    "render-token":       {"name": "Render",    "sym": "RNDR",  "type": "alt",   "max_lev": 5},
    "jupiter-exchange-solana": {"name": "Jupiter", "sym": "JUP", "type": "alt",  "max_lev": 3},
}

alerted = {}

def send(msg):
    for cid in CHAT_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": cid, "text": msg, "parse_mode": "HTML"},
                timeout=10
            )
        except Exception as e:
            print(f"Telegram error: {e}")
    
    

def fetch_ohlc(coin, days=14):
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin}/ohlc",
            params={"vs_currency": "usd", "days": str(days)},
            timeout=15
        )
        if r.status_code == 200:
            d = r.json()
            if len(d) >= 20:
                return {
                    "opens":  [x[1] for x in d],
                    "highs":  [x[2] for x in d],
                    "lows":   [x[3] for x in d],
                    "closes": [x[4] for x in d],
                }
        elif r.status_code == 429:
            print("Rate limited, waiting 60s...")
            time.sleep(60)
    except Exception as e:
        print(f"OHLC error: {e}")
    return None

def fetch_market(coin):
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency": "usd", "ids": coin, "price_change_percentage": "1h,24h,7d"},
            timeout=10
        )
        if r.status_code == 200 and r.json():
            c = r.json()[0]
            return {
                "price":    float(c.get("current_price") or 0),
                "chg_1h":   float(c.get("price_change_percentage_1h_in_currency") or 0),
                "chg_24h":  float(c.get("price_change_percentage_24h") or 0),
                "chg_7d":   float(c.get("price_change_percentage_7d_in_currency") or 0),
                "vol_24h":  float(c.get("total_volume") or 0),
                "high_24h": float(c.get("high_24h") or 0),
                "low_24h":  float(c.get("low_24h") or 0),
                "mktcap":   float(c.get("market_cap") or 0),
            }
        elif r.status_code == 429:
            print("Rate limited, waiting 60s...")
            time.sleep(60)
    except Exception as e:
        print(f"Market error: {e}")
    return None

def fetch_global_sentiment():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        if r.status_code == 200:
            d = r.json()["data"][0]
            return int(d["value"]), d["value_classification"]
    except:
        pass
    return 50, "Neutral"

def fetch_btc_dominance():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        if r.status_code == 200:
            d = r.json()["data"]
            return round(d["market_cap_percentage"]["btc"], 1)
    except:
        pass
    return 0.0

def ema(data, period):
    if len(data) < period:
        return data[-1]
    k = 2 / (period + 1)
    e = sum(data[:period]) / period
    for v in data[period:]:
        e = v * k + e * (1 - k)
    return e

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [max(x, 0) for x in deltas]
    losses = [max(-x, 0) for x in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return round(100.0 - (100.0 / (1 + avg_gain / avg_loss)), 1)

def macd_calc(closes):
    if len(closes) < 35:
        return 0, 0, 0, False, False
    macd_history = []
    for i in range(26, len(closes)):
        macd_history.append(ema(closes[:i+1], 12) - ema(closes[:i+1], 26))
    if len(macd_history) < 9:
        return 0, 0, 0, False, False
    macd_line   = macd_history[-1]
    signal_line = ema(macd_history, 9)
    histogram   = macd_line - signal_line
    prev_hist   = macd_history[-2] - ema(macd_history[:-1], 9) if len(macd_history) > 9 else 0
    return macd_line, signal_line, histogram, histogram > 0 and prev_hist <= 0, histogram < 0 and prev_hist >= 0

def bollinger_bands(closes, period=20):
    if len(closes) < period:
        return closes[-1], closes[-1], closes[-1], 0
    recent = closes[-period:]
    mid    = sum(recent) / period
    std    = statistics.stdev(recent)
    return mid + 2*std, mid, mid - 2*std, round((4*std/mid)*100, 2)

def stoch_rsi(closes, period=14):
    if len(closes) < period * 2:
        return 50.0, 50.0
    rsi_values = [rsi(closes[:i+1], period) for i in range(period, len(closes))]
    if len(rsi_values) < period:
        return 50.0, 50.0
    recent = rsi_values[-period:]
    mn, mx = min(recent), max(recent)
    if mx == mn:
        return 50.0, 50.0
    k = ((rsi_values[-1] - mn) / (mx - mn)) * 100
    d = sum(((rsi_values[-i] - mn) / (mx - mn)) * 100 for i in range(1, 4)) / 3
    return round(k, 1), round(d, 1)

def atr_calc(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return 0
    tr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, len(closes))]
    return sum(tr[-period:]) / period

def key_levels(highs, lows, closes):
    p = closes[-1]
    sup = min(lows[-20:])
    res = max(highs[-20:])
    return {
        "sup": sup, "res": res,
        "d_sup": ((p - sup) / p) * 100,
        "d_res": ((res - p) / p) * 100,
    }

def candlestick_patterns(opens, highs, lows, closes):
    bullish, bearish = [], []
    if len(closes) < 3:
        return bullish, bearish
    o, h, l, c = opens[-3:], highs[-3:], lows[-3:], closes[-3:]
    body  = [abs(c[i]-o[i]) for i in range(3)]
    uw    = [h[i]-max(c[i],o[i]) for i in range(3)]
    lw    = [min(c[i],o[i])-l[i] for i in range(3)]
    green = [c[i]>o[i] for i in range(3)]
    red   = [c[i]<o[i] for i in range(3)]
    if lw[2] > body[2]*2 and uw[2] < body[2]*0.3: bullish.append("Hammer")
    if red[1] and green[2] and o[2]<=c[1] and c[2]>=o[1] and body[2]>body[1]: bullish.append("Bullish Engulfing")
    if red[0] and body[1]<body[0]*0.4 and green[2] and c[2]>(o[0]+c[0])/2: bullish.append("Morning Star")
    if all(green) and c[2]>c[1]>c[0]: bullish.append("Three White Soldiers")
    if uw[2] > body[2]*2 and lw[2] < body[2]*0.3: bearish.append("Shooting Star")
    if green[1] and red[2] and o[2]>=c[1] and c[2]<=o[1] and body[2]>body[1]: bearish.append("Bearish Engulfing")
    if green[0] and body[1]<body[0]*0.4 and red[2] and c[2]<(o[0]+c[0])/2: bearish.append("Evening Star")
    if all(red) and c[2]<c[1]<c[0]: bearish.append("Three Black Crows")
    return bullish, bearish

def trend_info(closes, highs, lows):
    if len(closes) < 50:
        return "NEUTRAL", closes[-1], closes[-1]
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    p   = closes[-1]
    hh  = highs[-1] > max(highs[-10:-1])
    hl  = lows[-1]  > min(lows[-10:-1])
    lh  = highs[-1] < max(highs[-10:-1])
    ll  = lows[-1]  < min(lows[-10:-1])
    if e20 > e50 and p > e20:
        return ("STRONG UPTREND" if hh and hl else "UPTREND"), e20, e50
    if e20 < e50 and p < e20:
        return ("STRONG DOWNTREND" if lh and ll else "DOWNTREND"), e20, e50
    return "NEUTRAL", e20, e50

def score_coin(coin, ohlc, market):
    o, h, l, c = ohlc["opens"], ohlc["highs"], ohlc["lows"], ohlc["closes"]
    p = market["price"]
    if len(c) < 30:
        return None, 0, [], {}

    rv       = rsi(c)
    sk, sd   = stoch_rsi(c)
    ml, sl2, hist, bx, sx = macd_calc(c)
    bbu, bbm, bbl, bbw    = bollinger_bands(c)
    lv       = key_levels(h, l, c)
    trend, e20, e50       = trend_info(c, h, l)
    bp, sp   = candlestick_patterns(o, h, l, c)
    av       = atr_calc(h, l, c)
    c1h      = market["chg_1h"]
    c24      = market["chg_24h"]
    vol_ratio = round((market["vol_24h"] / market["mktcap"]) * 100, 2) if market["mktcap"] > 0 else 0

    ls, ss   = 0.0, 0.0
    lr, sr   = [], []

    if rv < 20:   ls += 2.5; lr.append(f"RSI severely oversold ({rv})")
    elif rv < 30: ls += 2.0; lr.append(f"RSI oversold ({rv})")
    elif rv < 40: ls += 1.0; lr.append(f"RSI below 40 ({rv})")
    if rv > 80:   ss += 2.5; sr.append(f"RSI severely overbought ({rv})")
    elif rv > 70: ss += 2.0; sr.append(f"RSI overbought ({rv})")
    elif rv > 60: ss += 1.0; sr.append(f"RSI above 60 ({rv})")

    if sk < 10 and sd < 20: ls += 2.0; lr.append(f"Stoch RSI deeply oversold (K:{sk})")
    elif sk < 20:            ls += 1.2; lr.append(f"Stoch RSI oversold (K:{sk})")
    if sk > 90 and sd > 80:  ss += 2.0; sr.append(f"Stoch RSI deeply overbought (K:{sk})")
    elif sk > 80:             ss += 1.2; sr.append(f"Stoch RSI overbought (K:{sk})")

    if bx:       ls += 2.5; lr.append("MACD bullish crossover confirmed")
    elif hist>0: ls += 1.0; lr.append("MACD bullish momentum")
    if sx:       ss += 2.5; sr.append("MACD bearish crossover confirmed")
    elif hist<0: ss += 1.0; sr.append("MACD bearish momentum")

    if p < bbl:        ls += 2.0; lr.append("Price below lower Bollinger Band")
    elif p < bbl*1.01: ls += 1.2; lr.append("Price touching lower Bollinger Band")
    if p > bbu:        ss += 2.0; sr.append("Price above upper Bollinger Band")
    elif p > bbu*0.99: ss += 1.2; sr.append("Price touching upper Bollinger Band")
    if bbw < 3:
        if ls > ss: ls += 0.8; lr.append("Bollinger squeeze — breakout likely")
        else:       ss += 0.8; sr.append("Bollinger squeeze — breakdown likely")

    if trend == "STRONG UPTREND":   ls += 2.5; lr.append("Strong uptrend confirmed (HH+HL)")
    elif trend == "UPTREND":        ls += 1.5; lr.append("Uptrend (EMA20 above EMA50)")
    if trend == "STRONG DOWNTREND": ss += 2.5; sr.append("Strong downtrend confirmed (LH+LL)")
    elif trend == "DOWNTREND":      ss += 1.5; sr.append("Downtrend (EMA20 below EMA50)")

    if lv["d_sup"] <= 1.0:   ls += 2.0; lr.append(f"Price AT key support (${lv['sup']:.4f})")
    elif lv["d_sup"] <= 3.0: ls += 1.2; lr.append(f"Near key support (${lv['sup']:.4f})")
    elif lv["d_sup"] <= 6.0: ls += 0.5; lr.append("Support zone nearby")
    if lv["d_res"] <= 1.0:   ss += 2.0; sr.append(f"Price AT key resistance (${lv['res']:.4f})")
    elif lv["d_res"] <= 3.0: ss += 1.2; sr.append(f"Near key resistance (${lv['res']:.4f})")
    elif lv["d_res"] <= 6.0: ss += 0.5; sr.append("Resistance zone nearby")

    if bp: ls += min(len(bp)*1.0, 2.0); lr.append(f"Pattern: {', '.join(bp)}")
    if sp: ss += min(len(sp)*1.0, 2.0); sr.append(f"Pattern: {', '.join(sp)}")

    if vol_ratio > 20:
        if ls > ss: ls += 1.0; lr.append(f"High volume activity ({vol_ratio}%)")
        else:       ss += 1.0; sr.append(f"High volume activity ({vol_ratio}%)")

    if c24 < -8 and rv < 35:   ls += 1.2; lr.append(f"Oversold bounce setup ({c24:.1f}% drop)")
    elif c1h > 0.5 and rv < 50: ls += 0.5; lr.append(f"Positive 1H momentum (+{c1h:.1f}%)")
    if c24 > 10 and rv > 65:    ss += 1.2; sr.append(f"Overbought reversal setup (+{c24:.1f}% pump)")
    elif c1h < -0.5 and rv > 50: ss += 0.5; sr.append(f"Negative 1H momentum ({c1h:.1f}%)")

    ls = round(min(ls, 15), 1)
    ss = round(min(ss, 15), 1)

    def calc_levels(direction):
        am = 1.5
        if direction == "LONG":
            tp1 = round(lv["res"]*0.99, 6) if lv["res"] > p else round(p+av*am*2, 6)
            tp2 = round(p+av*am*4, 6)
            sl  = round(lv["sup"]*0.995, 6) if lv["sup"] < p else round(p-av*am, 6)
            if tp1 <= p: tp1 = round(p*1.06, 6)
            if sl  >= p: sl  = round(p*0.94, 6)
            reward = ((tp1-p)/p)*100
            risk   = ((p-sl)/p)*100
        else:
            tp1 = round(lv["sup"]*1.01, 6) if lv["sup"] < p else round(p-av*am*2, 6)
            tp2 = round(p-av*am*4, 6)
            sl  = round(lv["res"]*1.005, 6) if lv["res"] > p else round(p+av*am, 6)
            if tp1 >= p: tp1 = round(p*0.94, 6)
            if sl  <= p: sl  = round(p*1.06, 6)
            reward = ((p-tp1)/p)*100
            risk   = ((sl-p)/p)*100
        rr = round(reward/risk, 2) if risk > 0 else 0
        return {
            "entry": p, "tp1": tp1, "tp2": tp2, "sl": sl,
            "risk": round(risk,2), "reward": round(reward,2), "rr": rr,
            "atr": round(av,6), "rsi": rv, "trend": trend,
            "support": lv["sup"], "resistance": lv["res"],
            "stoch_k": sk, "bbw": bbw,
        }

    if ls >= MIN_SCORE and ls > ss: return "LONG",  ls, lr, calc_levels("LONG")
    if ss >= MIN_SCORE and ss > ls: return "SHORT", ss, sr, calc_levels("SHORT")
    return None, max(ls, ss), [], {}

def format_and_send(coin, direction, score, reasons, lvl, market, info):
    key = f"{coin}_{direction}"
    if time.time() - alerted.get(key, 0) < COOLDOWN:
        return
    if lvl.get("rr", 0) < RR_MIN:
        print(f"  Skipped low R:R ({lvl.get('rr',0)})")
        return
    alerted[key] = time.time()

    if score >= 11:   confidence, stars = "VERY HIGH", "🔥🔥🔥"
    elif score >= 8:  confidence, stars = "HIGH",      "⭐⭐"
    else:             confidence, stars = "MODERATE",  "⭐"

    arrow     = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
    chg_sign  = "+" if market["chg_24h"] >= 0 else ""
    reasons_text = "\n".join([f"  • {r}" for r in reasons])

    msg = (
        f"{arrow} {stars} {confidence} CONFIDENCE\n\n"
        f"{info['name']} (#{info['sym']}) — {info['type'].upper()}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Price:  ${market['price']:,.6f}\n"
        f"📊 1H:     {market['chg_1h']:+.2f}%\n"
        f"📊 24H:    {chg_sign}{market['chg_24h']:.2f}%\n"
        f"📊 7D:     {market['chg_7d']:+.2f}%\n"
        f"📈 Trend:  {lvl['trend']}\n\n"
        f"WHY THIS SETUP ({score}/15):\n"
        f"{reasons_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"TRADE PLAN:\n"
        f"🎯 Entry:     ${lvl['entry']:,.6f}\n"
        f"✅ TP1:       ${lvl['tp1']:,.6f} (+{lvl['reward']:.1f}%)\n"
        f"✅ TP2:       ${lvl['tp2']:,.6f}\n"
        f"🛑 Stop Loss: ${lvl['sl']:,.6f} (-{lvl['risk']:.1f}%)\n"
        f"⚖️ R:R Ratio: 1:{lvl['rr']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"KEY LEVELS:\n"
        f"Support:    ${lvl['support']:,.6f}\n"
        f"Resistance: ${lvl['resistance']:,.6f}\n"
        f"ATR:        ${lvl['atr']:,.6f}\n\n"
        f"INDICATORS:\n"
        f"RSI: {lvl['rsi']} | Stoch K: {lvl['stoch_k']} | BB Width: {lvl['bbw']}%\n\n"
        f"BYBIT SETUP:\n"
        f"Margin: Isolated | Max Lev: {info['max_lev']}x\n"
        f"Risk: Max 2% of account per trade\n\n"
        f"⚠️ Verify on chart before entering\n"
        f"⚠️ Never trade without Stop Loss\n\n"
        f"{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Meme_Express Signals v3.0"
    )
    send(msg)
    print(f"  SIGNAL: {direction} {info['name']} | Score:{score}/15 | R:R:1:{lvl['rr']}")

def scan(scheduled=False):
    now = datetime.now().strftime('%H:%M')
    print(f"\n[{now}] Scanning {len(COINS)} coins...")
    fg_val, fg_label = fetch_global_sentiment()
    btc_dom = fetch_btc_dominance()
    print(f"  Fear&Greed={fg_val} ({fg_label}) | BTC Dom={btc_dom}%")
    found, errors = 0, 0
    for coin, info in COINS.items():
        print(f"  {info['name']}...", end=" ", flush=True)
        try:
            ohlc = fetch_ohlc(coin, 14)
            if not ohlc: print("no data"); errors+=1; time.sleep(SCAN_DELAY); continue
            market = fetch_market(coin)
            if not market: print("no market"); errors+=1; time.sleep(SCAN_DELAY); continue
            direction, score, reasons, lvl = score_coin(coin, ohlc, market)
            if direction and lvl:
                format_and_send(coin, direction, score, reasons, lvl, market, info)
                found += 1
            else:
                print(f"no setup ({score:.1f}/15)")
        except Exception as e:
            print(f"error: {e}"); errors += 1
        time.sleep(SCAN_DELAY)
    print(f"Done. {found} signals | {errors} errors")
    if scheduled:
        if found > 0:
            send(f"Scan done — {now}\n{found} signal(s) sent!\n\nFear&Greed: {fg_val} ({fg_label})\nBTC Dom: {btc_dom}%\n\nMeme_Express v3.0")
        else:
            send(f"Scan done — {now}\nNo strong setups. Market consolidating.\n\nFear&Greed: {fg_val} ({fg_label})\nBTC Dom: {btc_dom}%\n\nMeme_Express v3.0")

def run_scheduler():
    for t in ["00:00","04:00","08:00","12:00","16:00","20:00"]:
        schedule.every().day.at(t).do(lambda: scan(True))
    while True:
        schedule.run_pending()
        time.sleep(30)

def main():
    send(
        f"Meme_Express Signal Bot v3.0 LIVE!\n\n"
        f"Monitoring {len(COINS)} coins\n"
        f"9 indicators: RSI, Stoch RSI, MACD,\n"
        f"Bollinger Bands, EMA Trend, Support/Resistance,\n"
        f"Candlestick Patterns, Volume, Momentum\n\n"
        f"Min Score: {MIN_SCORE}/15 | Min R:R: 1:{RR_MIN}\n"
        f"Scans: Every 4hrs + Every 15mins\n\n"
        f"Always use Stop Loss.\n"
        f"Meme_Express v3.0"
    )
    threading.Thread(target=run_scheduler, daemon=True).start()
    scan(True)
    while True:
        time.sleep(900)
        scan(False)

if __name__ == "__main__":
    main()
