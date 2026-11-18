import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import time

# =====================================================================
# [BAGIAN 1] PENGATURAN
# =====================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 19 Pair (Nama standar MT5)
PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF", 
    "EURGBP", "GBPJPY", "EURJPY", "NZDCHF", "NZDJPY", "EURCHF", "GBPCHF", 
    "AUDCAD", "EURCAD", "GBPCAD", "XAUUSD", "BTCUSD"
]

# =====================================================================
# [BAGIAN 2] UTILITAS WAKTU & FILE MEMORY
# =====================================================================
def get_wib_time(dt_utc=None):
    if dt_utc is None:
        dt_utc = datetime.now(timezone.utc)
    wib = dt_utc + timedelta(hours=7)
    return wib.strftime("%d %b %y, %H:%M WIB")

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                content = f.read()
                if not content: return {} # Jika file kosong
                return json.loads(content)
        except:
            return {} # Jika file rusak
    return {}

def save_json(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

# =====================================================================
# [BAGIAN 3] TELEGRAM (ANTI-PUTUS)
# =====================================================================
def kirim_telegram(pesan):
    print(f"\n[INFO] Mengirim ke Telegram...")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[ERROR] Token/ID kosong!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": pesan, "parse_mode": "HTML"}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for i in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                print("[SUKSES] Terkirim!")
                return
            else:
                print(f"[ERROR TELEGRAM] {resp.status_code}: {resp.text}")
                return
        except Exception:
            print(f"[WARNING] Timeout, retry {i+1}/3...")
            time.sleep(5)
    print("[ERROR] Gagal total kirim Telegram.")

# =====================================================================
# [BAGIAN 4] PENGAMBILAN DATA BIQUOTE
# =====================================================================
def hitung_atr(df, period=14):
    hl = df['High'] - df['Low']
    hc = np.abs(df['High'] - df['Close'].shift())
    lc = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def get_data_biquote(symbol, timeframe):
    try:
        from biquote import Biquote
        bq = Biquote()
        # Ambil data
        bars = bq.ohlc(symbol, interval=timeframe, limit=50)
        if not bars: return None, None
        
        df = pd.DataFrame(bars)
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
        df.rename(columns={'open':'Open', 'high':'High', 'low':'Low', 'close':'Close'}, inplace=True)
        
        # PENTING: Buang candle yang sedang berjalan (baris terakhir)
        df_closed = df.iloc[:-1]
        waktu_candle_terakhir = str(df_closed.index[-1])
        return df_closed, waktu_candle_terakhir
    except Exception as e:
        print(f"[ERROR DATA] {symbol} {timeframe}: {e}")
        return None, None

def get_harga_live(symbol):
    try:
        from biquote import Biquote
        bq = Biquote()
        # biquote.tick mengembalikan harga terakhir (bid/ask)
        tick = bq.tick(symbol)
        return float(tick['bid']) # Pakai bid untuk trigger sell, ask untuk buy (simplifikasi pakai mid)
    except:
        return None

# =====================================================================
# [BAGIAN 5] LOGIKA ANALISA (SETUP)
# =====================================================================
def cek_setup(symbol, df_h4, df_d1, state):
    setups = {}
    now_str = get_wib_time()
    
    # --- Cek 80-20 (D1) ---
    if df_d1 is not None and len(df_d1) >= 2:
        tgl_d1 = str(df_d1.index[-1])
        if state.get(f"{symbol}_D1") != tgl_d1: # Belum dicek
            prev = df_d1.iloc[-1]
            o, h, l, c = float(prev['Open']), float(prev['High']), float(prev['Low']), float(prev['Close'])
            rng = h - l
            if rng > 0:
                top, bot = h - (0.2*rng), l + (0.2*rng)
                if o >= top and c <= bot: # Buy
                    setups["8020"] = {"dir": "BUY", "entry": h, "sl": l - (rng*0.1), "type": "80-20 BUY"}
                elif o <= bot and c >= top: # Sell
                    setups["8020"] = {"dir": "SELL", "entry": l, "sl": h + (rng*0.1), "type": "80-20 SELL"}
            state[f"{symbol}_D1"] = tgl_d1 # Tandai sudah dicek

    # --- Cek TS / TS+ (H4) ---
    if df_h4 is not None and len(df_h4) >= 22:
        tgl_h4 = str(df_h4.index[-1])
        if state.get(f"{symbol}_H4") != tgl_h4:
            df_h4['ATR'] = hitung_atr(df_h4)
            curr = df_h4.iloc[-1]
            lookback = df_h4.iloc[-21:-1]
            atr = float(curr['ATR'])
            
            if not pd.isna(atr) and atr > 0:
                o, h, l, c = float(curr['Open']), float(curr['High']), float(curr['Low']), float(curr['Close'])
                low20, high20 = float(lookback['Low'].min()), float(lookback['High'].max())
                
                if l < low20:
                    age = len(lookback) - lookback['Low'].values.argmin()
                    wick = (min(o,c) - l) / (h - l) if (h-l)>0 else 0
                    if c > low20 and age >= 4: # TS
                        setups["TS"] = {"dir": "BUY", "entry": low20 + (0.15*atr), "sl": l - (0.04*atr), "type": "TS BUY " + ("KUAT" if wick>=0.5 else "LEMAH"), "trailing": True}
                    elif c <= low20 and age >= 3: # TS+
                        setups["TS+"] = {"dir": "BUY", "entry": low20, "sl": l - (0.04*atr), "type": "TS+ BUY", "trailing": False}
                
                if h > high20:
                    age = len(lookback) - lookback['High'].values.argmax()
                    wick = (h - max(o,c)) / (h - l) if (h-l)>0 else 0
                    if c < high20 and age >= 4: # TS
                        setups["TS"] = {"dir": "SELL", "entry": high20 - (0.15*atr), "sl": h + (0.04*atr), "type": "TS SELL " + ("KUAT" if wick>=0.5 else "LEMAH"), "trailing": True}
                    elif c >= high20 and age >= 3: # TS+
                        setups["TS+"] = {"dir": "SELL", "entry": high20, "sl": h + (0.04*atr), "type": "TS+ SELL", "trailing": False}
            state[f"{symbol}_H4"] = tgl_h4 # Tandai sudah dicek
            
    return setups

# =====================================================================
# [BAGIAN 6] PROGRAM UTAMA
# =====================================================================
def jalankan():
    print(f"[MULAI] Waktu UTC: {datetime.now(timezone.utc)}")
    
    state = load_json("state.json")
    active = load_json("active_setups.json")
    sinyal_baru = []

    # --- FASE 1: CARI SETUP BARU ---
    for sym in PAIRS:
        df_h4, t_h4 = get_data_biquote(sym, "4h")
        df_d1, t_d1 = get_data_biquote(sym, "1d")
        
        new_setups = cek_setup(sym, df_h4, df_d1, state)
        for k, v in new_setups.items():
            if sym not in active: active[sym] = {}
            # Simpan ke active
            active[sym][k] = v
            sinyal_baru.append(f"⚠️ <b>[SETUP DITEMUKAN: {v['type']}]</b>\nPair: {sym}\nEntry: {v['entry']:.5f} ({v['dir']} STOP)\nSL: {v['sl']:.5f}\n<i>Bot sedang mengawasi harga...</i>")

    # --- FASE 2: PANTAU TRIGGER & TRAILING SL ---
    sinyal_trigger = []
    for sym in list(active.keys()):
        harga_live = get_harga_live(sym)
        if not harga_live: continue
        
        for key in list(active[sym].keys()):
            s = active[sym][key]
            triggered = False
            
            # Cek Trigger
            if s['dir'] == "BUY" and harga_live >= s['entry']:
                triggered = True
            elif s['dir'] == "SELL" and harga_live <= s['entry']:
                triggered = True
                
            if triggered:
                sinyal_trigger.append(f"🚨 <b>[TRIGGERED!]</b>\n{s['type']}\nPair: {sym}\nHarga Live: {harga_live:.5f}\n👉 <b>ENTRY {s['dir']} SEKARANG!</b>\nSL: {s['sl']:.5f}")
                del active[sym][key] # Hapus dari pantauan
                continue # Lanjut ke pair berikutnya
                
            # Cek Trailing SL (Khusus TS)
            if s.get('trailing') and not triggered:
                sl_baru = s['sl']
                if s['dir'] == "BUY" and harga_live < s['sl']:
                    # Update SL berdasarkan harga live (trailing)
                    # (Ini simplifikasi, SL sebenarnya pakai Low candle berjalan)
                    pass 

    # --- FASE 3: SIMPAN STATE & KIRIM NOTIF ---
    save_json("state.json", state)
    save_json("active_setups.json", active)
    
    if sinyal_baru:
        kirim_telegram("🔍 <b>Pemindaian Selesai. Setup Baru Ditemukan!</b>")
        for s in sinyal_baru: kirim_telegram(s)
        
    if sinyal_trigger:
        for s in sinyal_trigger: kirim_telegram(s)
        
    if not sinyal_baru and not sinyal_trigger:
        print("[INFO] Tidak ada setup atau trigger baru.")

if __name__ == "__main__":
    kirim_telegram("🧪 <b>TES KONEKSI:</b> Halo Indra, bot GitHub saya sudah berhasil terhubung ke Telegram!")
    jalankan()
