import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

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
        r = requests.post(url, json=payload, timeout=10)
        print(f"Status HTTP: {r.status_code}")
    except Exception as e:
        print(f"Error Telegram: {e}")

def check_80_20(df_d1):
    """Memeriksa Setup 80-20's pada candle harian (H-1)"""
    if len(df_d1) < 2:
        return None
    prev = df_d1.iloc[-2] # Candle kemarin yang sudah selesai
    o, h, l, c = prev['Open'], prev['High'], prev['Low'], prev['Close']
    total_range = h - l
    if total_range <= 0:
        return None
    
    lower_20 = l + 0.20 * total_range
    upper_20 = h - 0.20 * total_range
    
    # Buy Setup: Open <= 20% bawah & Close >= 20% atas
    if o <= lower_20 and c >= upper_20:
        return f"🟢 *80-20's BUY SETUP (D1)*\n   - High H-1: `{h:.4f}` | Low H-1: `{l:.4f}`\n   - *Rencana:* Pasang Buy Stop di atas High H-1"
    
    # Sell Setup: Open >= 20% atas & Close <= 20% bawah
    if o >= upper_20 and c <= lower_20:
        return f"🔴 *80-20's SELL SETUP (D1)*\n   - High H-1: `{h:.4f}` | Low H-1: `{l:.4f}`\n   - *Rencana:* Pasang Sell Stop di bawah Low H-1"
    
    return None

def check_turtle_soup(df_h4, lookback=20):
    """Memeriksa Turtle Soup (False Breakout 20 bar H4)"""
    if len(df_h4) < lookback + 1:
        return None
    
    recent = df_h4.iloc[-lookback-1:-1] # 20 bar H4 sebelumnya
    curr = df_h4.iloc[-1] # Bar H4 berjalan/terbaru
    
    max_high = recent['High'].max()
    min_low = recent['Low'].min()
    
    # Turtle Soup Buy: Menembus Low 20 bar tapi memantul kembali di atasnya
    if curr['Low'] < min_low and curr['Close'] > min_low:
        return f"🐢 *TURTLE SOUP BUY (H4)*\n   - Memantul dari Low 20-bar (`{min_low:.4f}`)\n   - Harga Saat Ini: `{curr['Close']:.4f}`"
        
    # Turtle Soup Sell: Menembus High 20 bar tapi memantul kembali di bawahnya
    if curr['High'] > max_high and curr['Close'] < max_high:
        return f"🐢 *TURTLE SOUP SELL (H4)*\n   - Memantul dari High 20-bar (`{max_high:.4f}`)\n   - Harga Saat Ini: `{curr['Close']:.4f}`"
        
    return None

def scan_markets():
    # Daftar aset: BTC-USD, EURUSD=X, GBPUSD=X, GC=F (Emas)
    pairs = ["BTC-USD", "EURUSD=X", "GBPUSD=X", "GC=F"]
    signals = []
    status_summary = []
    
    for symbol in pairs:
        try:
            # 1. Ambil data D1 (30 hari)
            df_d1 = yf.download(symbol, period="30d", interval="1d", progress=False)
            if isinstance(df_d1.columns, pd.MultiIndex):
                df_d1.columns = df_d1.columns.get_level_values(0)
            
            # 2. Ambil data H1 & resample ke H4 (14 hari)
            df_h1 = yf.download(symbol, period="14d", interval="1h", progress=False)
            if isinstance(df_h1.columns, pd.MultiIndex):
                df_h1.columns = df_h1.columns.get_level_values(0)
                
            df_h4 = df_h1.resample('4h').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
            }).dropna()
            
            last_price = float(df_d1['Close'].iloc[-1])
            status_summary.append(f"• `{symbol}`: `{last_price:.4f}`")
            
            # Analisis 80-20's
            sig_8020 = check_80_20(df_d1)
            if sig_8020:
                signals.append(f"📌 *{symbol}*\n{sig_8020}")
                
            # Analisis Turtle Soup H4
            sig_ts = check_turtle_soup(df_h4, lookback=20)
            if sig_ts:
                signals.append(f"📌 *{symbol}*\n{sig_ts}")
                
        except Exception as e:
            print(f"Error scanning {symbol}: {e}")
            
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    if signals:
        msg = f"🚨 *[SINYAL TRADING TERDETEKSI!]*\n⏰ Waktu: `{now_str}`\n\n" + "\n\n".join(signals)
    else:
        msg = f"✅ *[PEMINDAIAN UTUH SELESAI]*\n⏰ Waktu: `{now_str}`\n\nBelum ada setup **80-20's** atau **Turtle Soup H4** terdeteksi saat ini.\n\nHarga Terakhir:\n" + "\n".join(status_summary)
        
    send_telegram(msg)

if __name__ == "__main__":
    scan_markets()
