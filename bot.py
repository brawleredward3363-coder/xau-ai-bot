import os
import requests
import yfinance as yf
import pandas as pd

TELEGRAM_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
OPENROUTER_KEY = os.environ["OPENROUTER_API_KEY"]

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": message
    })

# XAU/USD futures verisi
data = yf.download(
    "GC=F",
    period="2d",
    interval="5m",
    progress=False,
    auto_adjust=False
)

if data.empty:
    send_telegram("⚠️ XAU/USD verisi alınamadı.")
    raise SystemExit

close = data["Close"].squeeze()

ema9 = close.ewm(span=9).mean()
ema21 = close.ewm(span=21).mean()

delta = close.diff()
gain = delta.clip(lower=0).rolling(14).mean()
loss = (-delta.clip(upper=0)).rolling(14).mean()

rsi = 100 - (100 / (1 + gain / loss))

price = float(close.iloc[-1])
ema9_now = float(ema9.iloc[-1])
ema21_now = float(ema21.iloc[-1])
rsi_now = float(rsi.iloc[-1])

if ema9_now > ema21_now:
    trend = "UP"
elif ema9_now < ema21_now:
    trend = "DOWN"
else:
    trend = "NEUTRAL"

prompt = f"""
You are a cautious XAU/USD intraday trading analyst.

Current gold price: {price:.2f}
EMA9: {ema9_now:.2f}
EMA21: {ema21_now:.2f}
RSI14: {rsi_now:.2f}
Trend: {trend}

Account size is only $10.

Return ONLY one of:
BUY
SELL
WAIT

Choose BUY or SELL only when the setup is reasonably strong.
Otherwise choose WAIT.
Do not promise profit.
"""

response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    },
    json={
        "model": "openrouter/free",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    },
    timeout=30
)

result = response.json()

try:
    signal = result["choices"][0]["message"]["content"].strip().upper()
except Exception:
    signal = "WAIT"

if "BUY" in signal:
    emoji = "🟢"
    signal = "BUY"
elif "SELL" in signal:
    emoji = "🔴"
    signal = "SELL"
else:
    emoji = "⏸️"
    signal = "WAIT"

message = f"""
{emoji} XAU/USD AI SİNYAL

Sinyal: {signal}

Fiyat: {price:.2f}
EMA9: {ema9_now:.2f}
EMA21: {ema21_now:.2f}
RSI: {rsi_now:.1f}

⚠️ Hesap: $10
⚠️ Manuel işlem — MT5
"""

send_telegram(message)
