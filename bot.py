import requests,time,schedule,threading,math,statistics
from datetime import datetime
BOT_TOKEN="8013194385:AAHRFcTr2T5kObSxBPQ-tdNw6AzNOGsMes0"
CHAT_ID="6553775216"
MIN_SCORE=6
RR_MIN=1.5
COOLDOWN=3600
SCAN_DELAY=4
COINS={
"bitcoin":{"name":"Bitcoin","sym":"BTC","emoji":"BTC","type":"major","max_lev":10},
"ethereum":{"name":"Ethereum","sym":"ETH","emoji":"ETH","type":"major","max_lev":10},
"solana":{"name":"Solana","sym":"SOL","emoji":"SOL","type":"major","max_lev":10},
"ripple":{"name":"XRP","sym":"XRP","emoji":"XRP","type":"major","max_lev":10},
"dogecoin":{"name":"Dogecoin","sym":"DOGE","emoji":"DOGE","type":"major","max_lev":5},
"pepe":{"name":"Pepe","sym":"PEPE","emoji":"PEPE","type":"meme","max_lev":5},
"bonk":{"name":"Bonk","sym":"BONK","emoji":"BONK","type":"meme","max_lev":3},
"dogwifcoin":{"name":"WIF","sym":"WIF","emoji":"WIF","type":"meme","max_lev":3},
"floki":{"name":"Floki","sym":"FLOKI","emoji":"FLOKI","type":"meme","max_lev":3},
"trump-2024":{"name":"TRUMP","sym":"TRUMP","emoji":"TRUMP","type":"meme","max_lev":3},
"avalanche-2":{"name":"Avalanche","sym":"AVAX","emoji":"AVAX","type":"alt","max_lev":5},
"chainlink":{"name":"Chainlink","sym":"LINK","emoji":"LINK","type":"alt","max_lev":5},
"sui":{"name":"Sui","sym":"SUI","emoji":"SUI","type":"alt","max_lev":5},
"injective-protocol":{"name":"Injective","sym":"INJ","emoji":"INJ","type":"alt","max_lev":5},
"aptos":{"name":"Aptos","sym":"APT","emoji":"APT","type":"alt","max_lev":5},
}
alerted={}
def send(msg):
 try:requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json={"chat_id":CHAT_ID,"text":msg,"parse_mode":"HTML"},timeout=10)
 except Exception as e:print(f"TG:{e}")
def fetch_ohlc(coin,days=14):
 try:
  r=requests.get(f"https://api.coingecko.com/api/v3/coins/{coin}/ohlc",params={"vs_currency":"usd","days":str(days)},timeout=15)
  if r.status_code==200:
   d=r.json()
   if len(d)>=20:return{"opens":[x[1]for x in d],"highs":[x[2]for x in d],"lows":[x[3]for x in d],"closes":[x[4]for x in d]}
 except:pass
 return None
def fetch_market(coin):
 try:
  r=requests.get("https://api.coingecko.com/api/v3/coins/markets",params={"vs_currency":"usd","ids":coin,"price_change_percentage":"1h,24h,7d"},timeout=10)
  if r.status_code==200 and r.json():
   c=r.json()[0]
   return{"price":float(c.get("current_price")or 0),"chg_1h":float(c.get("price_change_percentage_1h_in_currency")or 0),"chg_24h":float(c.get("price_change_percentage_24h")or 0),"chg_7d":float(c.get("price_change_percentage_7d_in_currency")or 0),"vol_24h":float(c.get("total_volume")or 0),"high_24h":float(c.get("high_24h")or 0),"low_24h":float(c.get("low_24h")or 0)}
 except:pass
 return None
def ema(data,p):
 if len(data)<p:return data[-1]
 k=2/(p+1);e=sum(data[:p])/p
 for v in data[p:]:e=v*k+e*(1-k)
 return e
def rsi(c,p=14):
 if len(c)<p+1:return 50.0
 d=[c[i]-c[i-1]for i in range(1,len(c))]
 g=[max(x,0)for x in d];l=[max(-x,0)for x in d]
 ag=sum(g[-p:])/p;al=sum(l[-p:])/p
 return 100.0-(100.0/(1+(ag/al)))if al>0 else 100.0
def macd_calc(c):
 if len(c)<35:return 0,0,0,False,False
 e12=ema(c,12);e26=ema(c,26);ml=e12-e26
 mh=[]
 for i in range(26,len(c)):mh.append(ema(c[:i+1],12)-ema(c[:i+1],26))
 if len(mh)<9:return ml,0,ml,False,False
 sl=ema(mh,9);hist=ml-sl
 ph=mh[-2]-ema(mh[:-1],9)if len(mh)>9 else 0
 return ml,sl,hist,hist>0 and ph<=0,hist<0 and ph>=0
def bb(c,p=20):
 if len(c)<p:return c[-1],c[-1],c[-1],0
 r=c[-p:];m=sum(r)/p;std=statistics.stdev(r)
 return m+2*std,m,m-2*std,(4*std/m)*100
def stoch_rsi(c,p=14):
 if len(c)<p*2:return 50.0,50.0
 rv=[rsi(c[:i+1],p)for i in range(p,len(c))]
 if len(rv)<p:return 50.0,50.0
 rc=rv[-p:];mn=min(rc);mx=max(rc)
 if mx==mn:return 50.0,50.0
 k=((rv[-1]-mn)/(mx-mn))*100
 d=sum(((rv[-i]-mn)/(mx-mn))*100 for i in range(1,4))/3
 return round(k,1),round(d,1)
def atr_calc(h,l,c,p=14):
 if len(c)<p+1:return 0
 tr=[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1]))for i in range(1,len(c))]
 return sum(tr[-p:])/p
def key_levels(h,l,c):
 p=c[-1];s=min(l[-20:]);r=max(h[-20:])
 return{"sup":s,"res":r,"d_sup":((p-s)/p)*100,"d_res":((r-p)/p)*100,"pos":((p-s)/(r-s)*100)if r!=s else 50}
def patterns(o,h,l,c):
 bu=[];be=[]
 if len(c)<3:return bu,be
 o3=o[-3:];h3=h[-3:];l3=l[-3:];c3=c[-3:]
 bd=[abs(c3[i]-o3[i])for i in range(3)];rg=[max(h3[i]-l3[i],0.00001)for i in range(3)]
 uw=[h3[i]-max(c3[i],o3[i])for i in range(3)];lw=[min(c3[i],o3[i])-l3[i]for i in range(3)]
 gn=[c3[i]>o3[i]for i in range(3)];rd=[c3[i]<o3[i]for i in range(3)]
 if lw[2]>bd[2]*2 and uw[2]<bd[2]*0.3:bu.append("Hammer")
 if rd[1]and gn[2]and o3[2]<=c3[1]and c3[2]>=o3[1]and bd[2]>bd[1]:bu.append("Bullish Engulfing")
 if rd[0]and bd[1]<bd[0]*0.4 and gn[2]and c3[2]>(o3[0]+c3[0])/2:bu.append("Morning Star")
 if all(gn)and c3[2]>c3[1]>c3[0]:bu.append("Three White Soldiers")
 if uw[2]>bd[2]*2 and lw[2]<bd[2]*0.3:be.append("Shooting Star")
 if gn[1]and rd[2]and o3[2]>=c3[1]and c3[2]<=o3[1]and bd[2]>bd[1]:be.append("Bearish Engulfing")
 if gn[0]and bd[1]<bd[0]*0.4 and rd[2]and c3[2]<(o3[0]+c3[0])/2:be.append("Evening Star")
 if all(rd)and c3[2]<c3[1]<c3[0]:be.append("Three Black Crows")
 return bu,be
def trend_info(c,h,l):
 if len(c)<50:return"NEUTRAL",0,c[-1],c[-1]
 e20=ema(c,20);e50=ema(c,50);p=c[-1]
 hh=h[-1]>max(h[-10:-1]);hl=l[-1]>min(l[-10:-1])
 lh=h[-1]<max(h[-10:-1]);ll=l[-1]<min(l[-10:-1])
 sep=abs(e20-e50)/e50*100
 if e20>e50 and p>e20:
  t="STRONG_UP"if hh and hl else"UPTREND"
  return t,min(sep*20,5),e20,e50
 if e20<e50 and p<e20:
  t="STRONG_DOWN"if lh and ll else"DOWNTREND"
  return t,min(sep*20,5),e20,e50
 return"NEUTRAL",0,e20,e50
def score_coin(coin,ohlc,market):
 o=ohlc["opens"];h=ohlc["highs"];l=ohlc["lows"];c=ohlc["closes"];p=market["price"]
 if len(c)<30:return None,0,[],{}
 rv=rsi(c);sk,sd=stoch_rsi(c);ml,sl2,hist,bx,sx=macd_calc(c)
 bbu,bbm,bbl,bbw=bb(c);lv=key_levels(h,l,c)
 t,ts,e20,e50=trend_info(c,h,l);bp,sp=patterns(o,h,l,c);av=atr_calc(h,l,c)
 c1h=market["chg_1h"];c24=market["chg_24h"]
 ls=0.0;ss=0.0;lr=[];sr=[]
 # RSI
 if rv<20:ls+=2.0;lr.append(f"RSI severely oversold ({rv:.1f})")
 elif rv<30:ls+=1.5;lr.append(f"RSI oversold ({rv:.1f})")
 elif rv<40:ls+=0.8;lr.append(f"RSI below 40 ({rv:.1f})")
 if rv>80:ss+=2.0;sr.append(f"RSI severely overbought ({rv:.1f})")
 elif rv>70:ss+=1.5;sr.append(f"RSI overbought ({rv:.1f})")
 elif rv>60:ss+=0.8;sr.append(f"RSI above 60 ({rv:.1f})")
 # Stoch RSI
 if sk<10 and sd<20:ls+=1.5;lr.append(f"Stoch RSI deeply oversold (K:{sk})")
 elif sk<20:ls+=1.0;lr.append(f"Stoch RSI oversold (K:{sk})")
 if sk>90 and sd>80:ss+=1.5;sr.append(f"Stoch RSI deeply overbought (K:{sk})")
 elif sk>80:ss+=1.0;sr.append(f"Stoch RSI overbought (K:{sk})")
 # MACD
 if bx:ls+=2.0;lr.append("MACD bullish crossover")
 elif hist>0:ls+=1.0;lr.append("MACD bullish")
 if sx:ss+=2.0;sr.append("MACD bearish crossover")
 elif hist<0:ss+=1.0;sr.append("MACD bearish")
 # Bollinger Bands
 if p<bbl:ls+=1.5;lr.append("Price below lower Bollinger Band")
 elif p<bbl*1.01:ls+=1.0;lr.append("Price at lower Bollinger Band")
 if p>bbu:ss+=1.5;sr.append("Price above upper Bollinger Band")
 elif p>bbu*0.99:ss+=1.0;sr.append("Price at upper Bollinger Band")
 if bbw<3:
  if ls>ss:ls+=0.5;lr.append("Bollinger squeeze - breakout imminent")
  else:ss+=0.5;sr.append("Bollinger squeeze - breakdown imminent")
 # Trend
 if t=="STRONG_UP":ls+=2.0;lr.append("STRONG uptrend (HH+HL)")
 elif t=="UPTREND":ls+=1.0;lr.append("Uptrend (EMA20>EMA50)")
 if t=="STRONG_DOWN":ss+=2.0;sr.append("STRONG downtrend (LH+LL)")
 elif t=="DOWNTREND":ss+=1.0;sr.append("Downtrend (EMA20<EMA50)")
 # Support/Resistance
 ds=lv["d_sup"];dr=lv["d_res"]
 if ds<=1.0:ls+=1.5;lr.append(f"Price AT support (${lv['sup']:.4f})")
 elif ds<=3.0:ls+=1.0;lr.append(f"Near support (${lv['sup']:.4f}, -{ds:.1f}%)")
 elif ds<=6.0:ls+=0.5;lr.append(f"Support nearby (${lv['sup']:.4f})")
 if dr<=1.0:ss+=1.5;sr.append(f"Price AT resistance (${lv['res']:.4f})")
 elif dr<=3.0:ss+=1.0;sr.append(f"Near resistance (${lv['res']:.4f}, +{dr:.1f}%)")
 elif dr<=6.0:ss+=0.5;sr.append(f"Resistance nearby (${lv['res']:.4f})")
 # Candle Patterns
 if bp:ls+=min(len(bp)*0.75,1.5);lr.append(f"Pattern: {', '.join(bp)}")
 if sp:ss+=min(len(sp)*0.75,1.5);sr.append(f"Pattern: {', '.join(sp)}")
 # Momentum
 if c24<-8 and rv<35:ls+=1.0;lr.append(f"Oversold bounce setup ({c24:.1f}% drop)")
 elif c1h>0.5 and rv<50:ls+=0.5;lr.append(f"Positive 1H momentum (+{c1h:.1f}%)")
 if c24>10 and rv>65:ss+=1.0;sr.append(f"Overbought reversal setup (+{c24:.1f}% pump)")
 elif c1h<-0.5 and rv>50:ss+=0.5;sr.append(f"Negative 1H momentum ({c1h:.1f}%)")
 ls=round(min(ls,12),1);ss=round(min(ss,12),1)
 def calc_levels(direction):
  am=1.5
  if direction=="LONG":
   tp1=round(lv["res"]*0.99,6)if lv["res"]>p else round(p+av*am*2,6)
   tp2=round(p+av*am*4,6);sl=round(lv["sup"]*0.995,6)if lv["sup"]<p else round(p-av*am,6)
   if tp1<=p:tp1=round(p*1.05,6)
   if sl>=p:sl=round(p*0.95,6)
   rw=((tp1-p)/p)*100;rk=((p-sl)/p)*100
  else:
   tp1=round(lv["sup"]*1.01,6)if lv["sup"]<p else round(p-av*am*2,6)
   tp2=round(p-av*am*4,6);sl=round(lv["res"]*1.005,6)if lv["res"]>p else round(p+av*am,6)
   if tp1>=p:tp1=round(p*0.95,6)
   if sl<=p:sl=round(p*1.05,6)
   rw=((p-tp1)/p)*100;rk=((sl-p)/p)*100
  rr=round(rw/rk,2)if rk>0 else 0
  return{"entry":p,"tp1":tp1,"tp2":tp2,"sl":sl,"risk":round(rk,2),"reward":round(rw,2),"rr":rr,"atr":round(av,6),"rsi":round(rv,1),"trend":t,"support":lv["sup"],"resistance":lv["res"],"stoch_k":sk,"bbw":round(bbw,2)}
 if ls>=MIN_SCORE and ls>ss:return"LONG",ls,lr,calc_levels("LONG")
 if ss>=MIN_SCORE and ss>ls:return"SHORT",ss,sr,calc_levels("SHORT")
 return None,max(ls,ss),[],{}
def format_send(coin,direction,score,reasons,lvl,market):
 key=f"{coin}_{direction}"
 if time.time()-alerted.get(key,0)<COOLDOWN:return
 if lvl.get("rr",0)<RR_MIN:print(f"  Skip RR:{lvl.get('rr',0)}");return
 alerted[key]=time.time()
 info=COINS[coin];de="LONG" if direction=="LONG" else "SHORT"
 ce="+" if market["chg_24h"]>=0 else""
 conf="VERY HIGH" if score>=9 else("HIGH" if score>=7 else"MODERATE")
 stars="***" if score>=9 else("**" if score>=7 else"*")
 rt="\n".join([f"  - {r}"for r in reasons])
 msg=f"""{de} SIGNAL {stars} {conf} CONFIDENCE
{info['name']} #{info['sym']} ({info['type'].upper()})
Price: ${market['price']:,.6f}
1H: {market['chg_1h']:+.2f}% | 24H: {ce}{market['chg_24h']:.2f}% | 7D: {market['chg_7d']:+.2f}%
Trend: {lvl['trend']}

REASONS ({score}/12):
{rt}

TRADE PLAN:
Entry:     ${lvl['entry']:,.6f}
TP1:       ${lvl['tp1']:,.6f} (+{lvl['reward']:.1f}%)
TP2:       ${lvl['tp2']:,.6f}
Stop Loss: ${lvl['sl']:,.6f} (-{lvl['risk']:.1f}%)
R:R Ratio: 1:{lvl['rr']}

KEY LEVELS:
Support:    ${lvl['support']:,.6f}
Resistance: ${lvl['resistance']:,.6f}
ATR:        ${lvl['atr']:,.6f}

INDICATORS:
RSI: {lvl['rsi']} | Stoch: {lvl['stoch_k']} | BB Width: {lvl['bbw']}%

BYBIT SETUP:
Margin: Isolated | Max Leverage: {info['max_lev']}x
Risk: Max 2% of account per trade

Always verify on chart before entering
Never trade without Stop Loss
{datetime.now().strftime('%Y-%m-%d %H:%M')}
Meme_Express Signals v2.0"""
 send(msg);print(f"  ALERT: {direction} {info['name']} Score:{score}/12 RR:1:{lvl['rr']}")
def scan(scheduled=False):
 now=datetime.now().strftime('%H:%M');found=0;errors=0
 print(f"\n[{now}] Scanning {len(COINS)} coins...")
 for coin,info in COINS.items():
  print(f"  {info['name']}...",end=" ",flush=True)
  try:
   ohlc=fetch_ohlc(coin,14)
   if not ohlc:print("no data");errors+=1;time.sleep(SCAN_DELAY);continue
   market=fetch_market(coin)
   if not market:print("no market");errors+=1;time.sleep(SCAN_DELAY);continue
   direction,score,reasons,lvl=score_coin(coin,ohlc,market)
   if direction and lvl:format_send(coin,direction,score,reasons,lvl,market);found+=1
   else:print(f"quiet ({score:.1f}/12)")
  except Exception as e:print(f"error:{e}");errors+=1
  time.sleep(SCAN_DELAY)
 print(f"Done. {found} signals. {errors} errors.")
 if scheduled:
  if found>0:send(f"Scan done — {now}\n{found} high-confidence signal(s) sent!")
  else:send(f"Scan done — {now}\nNo strong setups found. Market consolidating.")
def run_scheduler():
 for t in["00:00","04:00","08:00","12:00","16:00","20:00"]:
  schedule.every().day.at(t).do(lambda:scan(True))
 while True:schedule.run_pending();time.sleep(30)
def main():
 send(f"Meme_Express Signal Bot v2.0 LIVE!\n\nMonitoring {len(COINS)} coins with 8 indicators:\nRSI + Stoch RSI + MACD + Bollinger Bands\nEMA Trend + Support/Resistance\nCandlestick Patterns + Momentum\n\nMin Score: {MIN_SCORE}/12\nMin R:R: 1:{RR_MIN}\nScan: Every 15 mins\n\nHigh confidence signals only.\nAlways use Stop Loss.\nMeme_Express v2.0")
 threading.Thread(target=run_scheduler,daemon=True).start()
 scan(True)
 while True:time.sleep(900);scan(False)
if __name__=="__main__":main()
