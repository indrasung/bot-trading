import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

# Token dan Chat ID Telegram Anda
TELEGRAM_TOKEN = "9221976474:AAGK4Lz8h6GzLu1wuvoQvLoGoWxA9RdSiRs"
TELEGRAM_CHAT_ID = "6917045544"

def send_telegram(message):
    domain = "api.telegram.org"
    url = f"https://{domain}/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error kirim Telegram: {e}")

# 1. STRATEGI 80-20's (Timeframe Daily)
def check_80_20(df, symbol):
    if len(df) < 2:
        return None
    prev = df.iloc[-2]  # Candle kemarin
    o, h, l, c = float(prev['Open']), float(prev['High']), float(prev['Low']), float(prev['Close'])
    rng = h - l
    if rng <= 0:
        return None
    
    top_20 = h - (0.20 * rng)
    bot_20 = l + (0.20 * rng)
    
    # Buy Setup: Open di top 20%, Close di bottom 20%
    if o >= top_20 and c <= bot_20:
        return f"🚨 *[80-20's BUY SETUP]*\nPair: `{symbol}` (Daily)\nLow Kemarin: `{l:.5f}`\n👉 *Entry*: Siapkan BUY STOP di `{l:.5f}` saat penetrasi Low."
    
    # Sell Setup: Open di bottom 20%, Close di top 20%
    elif o <= bot_20 and c >= top_20:
        return f"🚨 *[80-20's SELL SETUP]*\nPair: `{symbol}` (Daily)\nHigh Kemarin: `{h:.5f}`\n👉 *Entry*: Siapkan SELL STOP di `{h:.5f}` saat penetrasi High."
    
    return None

# 2. STRATEGI TURTLE SOUP & TS+ (Timeframe H4 - Lookback 20 Period)
def check_turtle_soup(df, symbol):
    if len(df) < 22:
        return None
    
    curr = df.iloc[-1]
    lookback = df.iloc[-21:-1] # 20 candle H4 sebelumnya
    
    lowest_20 = float(lookback['Low'].min())
    highest_20 = float(lookback['High'].max())
    
    curr_low = float(curr['Low'])
    curr_high = float(curr['High'])
    curr_close = float(curr['Close'])
    
    # TS Buy: Low menembus di bawah 20-period Low, tapi Close membal balik di atasnya
    if curr_low < lowest_20 and curr_close > lowest_20:
        return f"🚨 *[TURTLE SOUP BUY]*\nPair: `{symbol}` (H4)\nLow 20-Bar: `{lowest_20:.5f}`\nLow Baru: `{curr_low:.5f}`\n👉 *Entry*: BUY di level `{lowest_20:.5f}`\n🛡 *Stop Loss*: `{curr_low:.5f}`"
        
    # TS Sell: High menembus di atas 20-period High, tapi Close membal balik di bawahnya
    if curr_high > highest_20 and curr_close < highest_20:
        return f"🚨 *[TURTLE SOUP SELL]*\nPair: `{symbol}` (H4)\nHigh 20-Bar: `{highest_20:.5f}`\nHigh Baru: `{curr_high:.5f}`\n👉 *Entry*: SELL di level `{highest_20:.5f}`\n🛡 *Stop Loss*: `{curr_high:.5f}`"

    return None

def main():
    pairs = ["BTC-USD", "EURUSD=X", "GBPUSD=X"]
    signals = []
    
    for symbol in pairs:
        try:
            # Ambii data Daily untuk 80-20's
            df_d1 = yf.download(symbol, period="30d", interval="1d", progress=False)
            if isinstance(df_d1.columns, pd.MultiIndex):
                df_d1.columns = df_d1.columns.get_level_values(0)
            
            sig_8020 = check_80_20(df_d1, symbol)
            if sig_8020:
                signals.append(sig_8020)
                
            # Ambil data H1 & resample ke H4 untuk Turtle Soup
            df_h1 = yf.download(symbol, period="30d", interval="1h", progress=False)
            if isinstance(df_h1.columns, pd.MultiIndex):
                df_h1.columns = df_h1.columns.get_level_values(0)
            
            df_h4 = df_h1.resample('4h').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last'
            }).dropna()
            
            sig_ts = check_turtle_soup(df_h4, symbol)
            if sig_ts:
                signals.append(sig_ts)
                
        except Exception as e:
            print(f"Error pada {symbol}: {e}")

    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    # NOTIFIKASI STATUS (Terbukti selalu terkirim ke Telegram)
    status_msg = f"🤖 *[BOT PEMINDAI AKTIF]*\n⏰ Waktu: `{now_str}`\n📊 Pasar: {', '.join(pairs)}\n"
    if signals:
        status_msg += f"✅ *Ditemukan {len(signals)} Sinyal Valid!*"
        send_telegram(status_msg)
        for sig in signals:
            send_telegram(sig)
    else:
        status_msg += "ℹ️ *Status*: Pemindaian selesai. Tidak ada setup 80-20's / Turtle Soup yang aktif."
        send_telegram(status_msg)

if __name__ == "__main__":
    main()
