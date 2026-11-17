import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time

# =====================================================================
# [BAGIAN 1] PENGATURAN
# =====================================================================
# Token & ID diambil dari GitHub Secrets (Jangan ditulis langsung di sini)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Daftar Pair (Format MT4 : Format Yahoo Finance)
PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "NZDUSD": "NZDUSD=X",
    "USDCHF": "USDCHF=X",
    "EURGBP": "EURGBP=X",
    "XAUUSD": "GC=F",
    "BTCUSD": "BTC-USD",
    "GBPJPY": "GBPJPY=X",
    "EURJPY": "EURJPY=X"
}

# =====================================================================
# [BAGIAN 2] UTILITAS WAKTU (WIB & FORMAT TANGGAL)
# =====================================================================
def dapatkan_waktu_wib():
    # Waktu server (UTC) + 7 jam = WIB
    wib_time = datetime.utcnow() + timedelta(hours=7)
    # Format: 11 Nov 26, 15:05 WIB
    return wib_time.strftime("%d %b %y, %H:%M WIB")

# =====================================================================
# [BAGIAN 3] MODUL KIRIM TELEGRAM (VERSI PERBAIKAN JARINGAN)
# =====================================================================
def kirim_telegram(pesan):
    print(f"\n[INFO] Mengirim pesan ke Telegram...")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[ERROR] Token atau Chat ID belum diset di GitHub Secrets!")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": pesan, "parse_mode": "HTML"}
    
    # Header agar Telegram tidak mengira ini serangan bot
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    # Coba kirim hingga 3 kali jika jaringan putus
    for percobaan in range(3):
        try:
            respon = requests.post(url, json=payload, headers=headers, timeout=15)
            if respon.status_code == 200:
                print("[SUKSES] Pesan terkirim ke Telegram!")
                return # Keluar dari fungsi jika berhasil
            else:
                print(f"[ERROR TELEGRAM] Kode: {respon.status_code}, Pesan: {respon.text}")
                return
        except requests.exceptions.RequestException as e:
            print(f"[WARNING] Percobaan {percobaan + 1} gagal (Jaringan sibuk). Mencoba lagi...")
            time.sleep(5) # Jeda 5 detik sebelum coba lagi (membutuhkan import time)
            
    print("[ERROR KONEKSI] Gagal total menghubungi Telegram setelah 3x percobaan.")

# =====================================================================
# [BAGIAN 4] MODUL AMBIL DATA & HITUNG ATR
# =====================================================================
def ambil_data(yahoo_symbol, interval, period="30d"):
    try:
        df = yf.download(yahoo_symbol, period=period, interval=interval, progress=False, threads=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None

def hitung_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(window=period).mean()

def cek_harga_live(yahoo_symbol):
    try:
        ticker = yf.Ticker(yahoo_symbol)
        harga = ticker.fast_info['last_price']
        return float(harga)
    except Exception:
        return None

# =====================================================================
# [BAGIAN 5] MODUL ANALISA 80-20 (Timeframe D1)
# =====================================================================
def cek_80_20(simbol_mt4, yahoo_symbol):
    df = ambil_data(yahoo_symbol, "1d")
    if df is None or len(df) < 2: return None
    
    prev = df.iloc[-2]
    o, h, l, c = float(prev['Open']), float(prev['High']), float(prev['Low']), float(prev['Close'])
    rng = h - l
    if rng <= 0: return None
        
    top_20 = h - (0.20 * rng)
    bot_20 = l + (0.20 * rng)
    waktu_sekarang = dapatkan_waktu_wib()
    
    # 80-20 BUY: Kemarin turun tajam (Open atas, Close bawah) -> Harap pembalikan naik
    if o >= top_20 and c <= bot_20:
        harga_live = cek_harga_live(yahoo_symbol)
        if harga_live and harga_live > h:
            return f"⚠️ <b>[80-20's BUY - TERLAMBAT]</b>\nPair: {simbol_mt4} (D1)\nWaktu: {waktu_sekarang}\nHarga sudah tembus High ({h:.5f}). Harga kini: {harga_live:.5f}. Abaikan."
        return f"🚨 <b>[80-20's BUY SETUP]</b>\nPair: {simbol_mt4} (D1)\nWaktu: {waktu_sekarang}\nHigh Kemarin: <code>{h:.5f}</code>\n👉 <b>Entry:</b> BUY STOP di <code>{h:.5f}</code>"
    
    # 80-20 SELL: Kemarin naik tajam (Open bawah, Close atas) -> Harap pembalikan turun
    elif o <= bot_20 and c >= top_20:
        harga_live = cek_harga_live(yahoo_symbol)
        if harga_live and harga_live < l:
            return f"⚠️ <b>[80-20's SELL - TERLAMBAT]</b>\nPair: {simbol_mt4} (D1)\nWaktu: {waktu_sekarang}\nHarga sudah tembus Low ({l:.5f}). Harga kini: {harga_live:.5f}. Abaikan."
        return f"🚨 <b>[80-20's SELL SETUP]</b>\nPair: {simbol_mt4} (D1)\nWaktu: {waktu_sekarang}\nLow Kemarin: <code>{l:.5f}</code>\n👉 <b>Entry:</b> SELL STOP di <code>{l:.5f}</code>"
        
    return None

# =====================================================================
# [BAGIAN 6] MODUL ANALISA TS / TS+ (Timeframe H4)
# =====================================================================
def cek_ts(simbol_mt4, yahoo_symbol):
    df_h1 = ambil_data(yahoo_symbol, "1h")
    if df_h1 is None: return None
    
    # Konversi H1 ke H4
    df = df_h1.resample('4h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'}).dropna()
    if len(df) < 22: return None
    
    df['ATR'] = hitung_atr(df)
    
    curr = df.iloc[-1]
    lookback = df.iloc[-21:-1]
    atr = float(curr['ATR'])
    
    if pd.isna(atr) or atr <= 0: return None
    
    o, h, l, c = float(curr['Open']), float(curr['High']), float(curr['Low']), float(curr['Close'])
    lowest_20 = float(lookback['Low'].min())
    highest_20 = float(lookback['High'].max())
    waktu_sekarang = dapatkan_waktu_wib()
    
    # TS BUY / TS+ BUY
    if l < lowest_20:
        idx_low = lookback['Low'].idxmin()
        age = len(lookback) - lookback.index.get_loc(idx_low)
        wick = (min(o, c) - l) / (h - l) if (h - l) > 0 else 0
        
        if c > lowest_20 and age >= 4: # TS Buy
            harga_live = cek_harga_live(yahoo_symbol)
            entry = lowest_20 + (0.15 * atr)
            if harga_live and harga_live > entry:
                return f"⚠️ <b>[TS BUY - TERLAMBAT]</b>\nPair: {simbol_mt4} (H4)\nWaktu: {waktu_sekarang}\nHarga sudah naik ke {harga_live:.5f} (Entry: {entry:.5f}). Abaikan."
            
            tipe = "TS KUAT" if wick >= 0.5 else "TS LEMAH"
            return f"🚨 <b>[{tipe} BUY]</b>\nPair: {simbol_mt4} (H4)\nWaktu: {waktu_sekarang}\nEntry: <code>{entry:.5f}</code> (BUY STOP)\nSL: <code>{l:.5f}</code>"
            
        elif c <= lowest_20 and age >= 3: # TS+ Buy
            entry = lowest_20
            harga_live = cek_harga_live(yahoo_symbol)
            if harga_live and harga_live > entry:
                return f"⚠️ <b>[TS+ BUY - TERLAMBAT]</b>\nPair: {simbol_mt4} (H4)\nWaktu: {waktu_sekarang}\nHarga sudah naik ke {harga_live:.5f}. Abaikan."
            return f"🚨 <b>[TS+ BUY]</b>\nPair: {simbol_mt4} (H4)\nWaktu: {waktu_sekarang}\nEntry: <code>{entry:.5f}</code> (BUY STOP)\nSL: <code>{l - (0.04 * atr):.5f}</code>"

    # TS SELL / TS+ SELL
    if h > highest_20:
        idx_high = lookback['High'].idxmax()
        age = len(lookback) - lookback.index.get_loc(idx_high)
        wick = (h - max(o, c)) / (h - l) if (h - l) > 0 else 0
        
        if c < highest_20 and age >= 4: # TS Sell
            harga_live = cek_harga_live(yahoo_symbol)
            entry = highest_20 - (0.15 * atr)
            if harga_live and harga_live < entry:
                return f"⚠️ <b>[TS SELL - TERLAMBAT]</b>\nPair: {simbol_mt4} (H4)\nWaktu: {waktu_sekarang}\nHarga sudah turun ke {harga_live:.5f} (Entry: {entry:.5f}). Abaikan."
            
            tipe = "TS KUAT" if wick >= 0.5 else "TS LEMAH"
            return f"🚨 <b>[{tipe} SELL]</b>\nPair: {simbol_mt4} (H4)\nWaktu: {waktu_sekarang}\nEntry: <code>{entry:.5f}</code> (SELL STOP)\nSL: <code>{h:.5f}</code>"
            
        elif c >= highest_20 and age >= 3: # TS+ Sell
            entry = highest_20
            harga_live = cek_harga_live(yahoo_symbol)
            if harga_live and harga_live < entry:
                return f"⚠️ <b>[TS+ SELL - TERLAMBAT]</b>\nPair: {simbol_mt4} (H4)\nWaktu: {waktu_sekarang}\nHarga sudah turun ke {harga_live:.5f}. Abaikan."
            return f"🚨 <b>[TS+ SELL]</b>\nPair: {simbol_mt4} (H4)\nWaktu: {waktu_sekarang}\nEntry: <code>{entry:.5f}</code> (SELL STOP)\nSL: <code>{h + (0.04 * atr):.5f}</code>"

    return None

# =====================================================================
# [BAGIAN 7] PROGRAM UTAMA
# =====================================================================
def jalankan():
    print(f"==========================================")
    print(f"[MULAI] Waktu UTC: {datetime.utcnow()}")
    
    semua_sinyal = []
    
    for simbol_mt4, yahoo_symbol in PAIRS.items():
        # Cek 80-20 (D1)
        sinyal_80 = cek_80_20(simbol_mt4, yahoo_symbol)
        if sinyal_80: 
            semua_sinyal.append(sinyal_80)
            print(f"[SUKSES] Sinyal 80-20 ditemukan: {simbol_mt4}")
        
        # Cek TS/TS+ (H4)
        sinyal_ts = cek_ts(simbol_mt4, yahoo_symbol)
        if sinyal_ts: 
            semua_sinyal.append(sinyal_ts)
            print(f"[SUKSES] Sinyal TS ditemukan: {simbol_mt4}")

    # Laporan Akhir
    if semua_sinyal:
        kirim_telegram(f"🔔 <b>Ditemukan {len(semua_sinyal)} Sinyal Valid!</b>")
        for s in semua_sinyal:
            kirim_telegram(s)
    else:
        print("[INFO] Tidak ada sinyal. Tidak mengirim pesan agar HP tidak berisik.")

if __name__ == "__main__":
    jalankan()
