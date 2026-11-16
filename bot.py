
# === ISI FILE: bot.py ===

import requests
import yfinance as yf

TELEGRAM_TOKEN = "9221976474:AAGK4Lz8h6GzLu1wuvoQvLoGoWxA9RdSiRs"
TELEGRAM_CHAT_ID = "6917045544"

def send_telegram(message):
    domain = "api.telegram.org"
    url = f"https://{domain}/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error kirim Telegram: {e}")

def check_80_20(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="1d", progress=False)
        if len(df) < 2:
            return
        prev = df.iloc[-2]
        o = float(prev['Open'])
        h = float(prev['High'])
        l = float(prev['Low'])
        c = float(prev['Close'])
        rng = h - l
        if rng <= 0:
            return
        
        top_20 = h - (0.20 * rng)
        bot_20 = l + (0.20 * rng)
        
        if o >= top_20 and c <= bot_20:
            msg = f"[80-20's BUY SETUP]\nPair: {symbol}\nLow Kemarin: {l:.5f}\nSiapkan BUY STOP di bawah Low kemarin."
            send_telegram(msg)
            
        elif o <= bot_20 and c >= top_20:
            msg = f"[80-20's SELL SETUP]\nPair: {symbol}\nHigh Kemarin: {h:.5f}\nSiapkan SELL STOP di atas High kemarin."
            send_telegram(msg)
    except Exception as e:
        print(f"Error {symbol}: {e}")

pairs = ["BTC-USD", "EURUSD=X"]
for p in pairs:
    check_80_20(p)


