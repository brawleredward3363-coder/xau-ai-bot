import os
import requests
import yfinance as yf
import pandas as pd

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]

def telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(
        url,
        data={"chat_id": CHAT_ID, "text": message},
        timeout=20
    )
    r.raise_for_status()

# XAU/USD referans verisi
df = yf.download(
    "GC=F",
    period="5d",
    interval="5m",
    progress=False,
    auto_adjust=False
)

if df.empty:
    telegram("⚠️ XAU/USD verisi alınamadı.")
    raise SystemExit

if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

df = df.dropna()

close = df["Close"].astype(float)
high = df["High"].astype(float)
low = df["Low"].astype(float)

# EMA
df["EMA9"] = close.ewm(span=9, adjust=False).mean()
df["EMA21"] = close.ewm(span=21, adjust=False).mean()

# RSI
delta = close.diff()
gain = delta.clip(lower=0).rolling(14).mean()
loss = (-delta.clip(upper=0)).rolling(14).mean()

rs = gain / loss.replace(0, float("nan"))
df["RSI"] = 100 - (100 / (1 + rs))

# ATR
prev_close = close.shift(1)

tr = pd.concat([
    high - low,
    (high - prev_close).abs(),
    (low - prev_close).abs()
], axis=1).max(axis=1)

df["ATR"] = tr.rolling(14).mean()

last = df.iloc[-1]

price = float(last["Close"])
ema9 = float(last["EMA9"])
ema21 = float(last["EMA21"])
rsi = float(last["RSI"])
atr = float(last["ATR"])

if ema9 > ema21:
    trend = "UP"
elif ema9 < ema21:
    trend = "DOWN"
else:
    trend = "NEUTRAL"

# Teknik filtre
bullish = (
    trend == "UP"
    and 52 <= rsi <= 68
)

bearish = (
    trend == "DOWN"
    and 32 <= rsi <= 48
)

if not bullish and not bearish:
    telegram(
        f"⏸️ XAU/USD BEKLE\n\n"
        f"Fiyat: {price:.2f}\n"
        f"Trend: {trend}\n"
        f"RSI: {rsi:.1f}\n"
        f"ATR: {atr:.2f}\n\n"
        f"Teknik setup uygun değil."
    )
    raise SystemExit

# AI
prompt = f"""
Analyze this XAU/USD 5-minute setup conservatively.

Price: {price:.2f}
EMA9: {ema9:.2f}
EMA21: {ema21:.2f}
RSI: {rsi:.2f}
ATR: {atr:.2f}
Trend: {trend}

Account: $10.

Return exactly one word:
BUY
SELL
WAIT

Only choose BUY or SELL if the setup has clear directional evidence.
Otherwise choose WAIT.
Never promise profit.
"""

response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    },
    json={
        "model": "openrouter/free",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 5
    },
    timeout=30
)

if response.status_code != 200:
    telegram(f"⚠️ AI bağlantı hatası: HTTP {response.status_code}")
    raise SystemExit

try:
    signal = response.json()["choices"][0]["message"]["content"].strip().upper()
except Exception:
    signal = "WAIT"

if signal not in ["BUY", "SELL", "WAIT"]:
    signal = "WAIT"

# ATR tabanlı SL / TP
if signal == "BUY":
    sl = price - (atr * 1.0)
    tp = price + (atr * 1.5)
    emoji = "🟢"

elif signal == "SELL":
    sl = price + (atr * 1.0)
    tp = price - (atr * 1.5)
    emoji = "🔴"

else:
    sl = None
    tp = None
    emoji = "⏸️"

if signal == "WAIT":
    telegram(
        f"⏸️ XAU/USD BEKLE\n\n"
        f"Fiyat: {price:.2f}\n"
        f"Trend: {trend}\n"
        f"RSI: {rsi:.1f}\n"
        f"ATR: {atr:.2f}\n\n"
        f"AI işlem onayı vermedi."
    )
else:
    telegram(
        f"{emoji} XAU/USD {signal}\n\n"
        f"📍 Giriş: {price:.2f}\n"
        f"🛑 SL: {sl:.2f}\n"
        f"🎯 TP: {tp:.2f}\n\n"
        f"📊 Trend: {trend}\n"
        f"RSI: {rsi:.1f}\n"
        f"ATR: {atr:.2f}\n\n"
        f"💵 Hesap: $10\n"
        f"⚠️ Manuel işlem — MT5"
    )
