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
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error kirim Telegram: {e}")

def test_tahap_2():
    pairs = ["BTC-USD", "EURUSD=X", "GBPUSD=X"]
    summary_lines = []
    
    for symbol in pairs:
        try:
            # 1. Tes Ambil Data Daily (D1)
            df_d1 = yf.download(symbol, period="7d", interval="1d", progress=False)
            if isinstance(df_d1.columns, pd.MultiIndex):
                df_d1.columns = df_d1.columns.get_level_values(0)
            
            # 2. Tes Ambil Data H1 & Resample ke H4
            df_h1 = yf.download(symbol, period="7d", interval="1h", progress=False)
            if isinstance(df_h1.columns, pd.MultiIndex):
                df_h1.columns = df_h1.columns.get_level_values(0)
                
            df_h4 = df_h1.resample('4h').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
            }).dropna()
            
            last_close = float(df_d1['Close'].iloc[-1])
            summary_lines.append(f"• `{symbol}`: Harga Terakhir `{last_close:.4f}` | Data D1: {len(df_d1)} baris, H4: {len(df_h4)} baris")
            
        except Exception as e:
            summary_lines.append(f"• `{symbol}`: ❌ Error ({e})")
            
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    msg = f"📊 *[TES TAHAP 2 BERHASIL!]*\n⏰ Waktu: `{now_str}`\n\nPenarikan data pasar via `yfinance` & `pandas` berjalan lancar:\n\n" + "\n".join(summary_lines)
    send_telegram(msg)

if __name__ == "__main__":
    test_tahap_2()
