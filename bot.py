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

# Gold futures — XAU/USD'ye referans veri
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

# Çoklu kolon sorununu düzelt
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

df = df.dropna()

close = df["Close"].astype(float)

# EMA
df["EMA9"] = close.ewm(span=9, adjust=False).mean()
df["EMA21"] = close.ewm(span=21, adjust=False).mean()

# RSI
delta = close.diff()
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)

avg_gain = gain.rolling(14).mean()
avg_loss = loss.rolling(14).mean()

rs = avg_gain / avg_loss.replace(0, float("nan"))
df["RSI"] = 100 - (100 / (1 + rs))

# ATR
high = df["High"].astype(float)
low = df["Low"].astype(float)

prev_close = close.shift(1)

tr = pd.concat([
    high - low,
    (high - prev_close).abs(),
    (low - prev_close).abs()
], axis=1).max(axis=1)

df["ATR"] = tr.rolling(14).mean()

last = df.iloc[-1]
prev = df.iloc[-2]

price = float(last["Close"])
ema9 = float(last["EMA9"])
ema21 = float(last["EMA21"])
rsi = float(last["RSI"])
atr = float(last["ATR"])

# Teknik yön
if ema9 > ema21:
    trend = "UP"
elif ema9 < ema21:
    trend = "DOWN"
else:
    trend = "NEUTRAL"

# AI'ye sadece teknik setup varsa sor
bullish_setup = (
    ema9 > ema21 and
    rsi >= 50 and
    rsi <= 70
)

bearish_setup = (
    ema9 < ema21 and
    rsi <= 50 and
    rsi >= 30
)

if not bullish_setup and not bearish_setup:
    telegram(
        f"⏸️ XAU/USD BEKLE\n\n"
        f"Fiyat: {price:.2f}\n"
        f"Trend: {trend}\n"
        f"RSI: {rsi:.1f}\n\n"
        f"Teknik setup yeterince güçlü değil."
    )
    raise SystemExit

prompt = f"""
You are a conservative XAU/USD intraday trading filter.

Current price: {price:.2f}
EMA9: {ema9:.2f}
EMA21: {ema21:.2f}
RSI14: {rsi:.2f}
ATR14: {atr:.2f}
Trend: {trend}

Account size: $10.

We want very short-term trades, but capital protection is more important
than frequency.

Return ONLY one word:
BUY
SELL
WAIT

Rules:
- Never promise profit.
- If evidence is mixed, return WAIT.
- Do not choose BUY against a clear DOWN trend.
- Do not choose SELL against a clear UP trend.
- Avoid overtrading.
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
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.1,
        "max_tokens": 10
    },
    timeout=30
)

if response.status_code != 200:
    telegram(
        f"⚠️ AI bağlantı hatası\n"
        f"HTTP: {response.status_code}"
    )
    raise SystemExit

data = response.json()

try:
    signal = data["choices"][0]["message"]["content"].strip().upper()
except Exception:
    signal = "WAIT"

if signal not in ["BUY", "SELL", "WAIT"]:
    signal = "WAIT"

if signal == "BUY":
    emoji = "🟢"
elif signal == "SELL":
    emoji = "🔴"
else:
    emoji = "⏸️"

telegram(
    f"{emoji} XAU/USD AI SİNYAL\n\n"
    f"Sinyal: {signal}\n"
    f"Fiyat: {price:.2f}\n"
    f"Trend: {trend}\n"
    f"EMA9: {ema9:.2f}\n"
    f"EMA21: {ema21:.2f}\n"
    f"RSI: {rsi:.1f}\n"
    f"ATR: {atr:.2f}\n\n"
    f"💵 Hesap: $10\n"
    f"⚠️ Manuel işlem — MT5"
)
