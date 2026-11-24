import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import time
from biquote import Biquote

# =====================================================================
# [PANEL KONTROL UTAMA]
# =====================================================================
PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF", 
    "EURGBP", "GBPJPY", "EURJPY", "NZDCHF", "NZDJPY", "EURCHF", "GBPCHF", 
    "AUDCAD", "EURCAD", "GBPCAD", "XAUUSD", "BTCUSD"
]

# 1. TURTLE SOUP (TS & TS+)
TS_STATUS = "ON"     
TS_TIMEFRAME = "1d"  

# 2. 80-20 STRATEGY
S8020_STATUS = "ON"     
S8020_TIMEFRAME = "1d"  

# 3. MOMENTUM PINBALL (Watchlist 05:00, Entry 06:00)
PINBALL_STATUS = "ON"     
# (Pinball terkunci di D1 karena butuh siklus harian untuk RSI dan First Hour)

# 4. Parameter Global
SPREAD_MAX_R = 0.15
ENTRY_ATR = 0.15
STOP_ATR = 0.04
ATR_PERIOD = 14
MIN_CANDLE_ATR = 0.8 
WARNING_ATR = 0.02
EXEC_ATR = 0.10      

# =====================================================================
# [BAGIAN 2] UTILITAS & MEMORY
# =====================================================================
def get_wib_time():
    return (datetime.now(timezone.utc) + timedelta(hours=7)).strftime("%d %b %y, %H:%M WIB")

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                content = f.read()
                if not content: return {}
                return json.loads(content)
        except: return {}
    return {}

def save_json(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

# =====================================================================
# [BAGIAN 3] TELEGRAM (ANTI-PUTUS)
# =====================================================================
def kirim_telegram(pesan):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": pesan, "parse_mode": "HTML"}
    headers = {"User-Agent": "Mozilla/5.0"}
    for i in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200: return
        except: time.sleep(5)

# =====================================================================
# [BAGIAN 4] DATA & PERHITUNGAN
# =====================================================================
def hitung_atr(df, period=14):
    hl = df['High'] - df['Low']
    hc = np.abs(df['High'] - df['Close'].shift())
    lc = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def hitung_lbr_rsi(df):
    # Rumus LBR/RSI asli buku Street Smarts:
    # RSI(3) dari Rate of Change (ROC) 1-periode
    roc = df['Close'].diff()       # 1. Hitung ROC
    delta_roc = roc.diff()         # 2. Hitung perubahan ROC
    gain = delta_roc.clip(lower=0)
    loss = -delta_roc.clip(upper=0)
    
    # Wilder's Smoothing (RSI 3-periode)
    avg_gain = gain.ewm(alpha=1/3, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/3, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def get_data_biquote(bq, symbol, timeframe):
    try:
        limit = 500 # Ubah limit menjadi 500 agar data histori banyak
        bars = bq.ohlc(symbol, interval=timeframe, limit=limit)
        if not bars: return None, None
        df = pd.DataFrame(bars)
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
        df.rename(columns={'open':'Open', 'high':'High', 'low':'Low', 'close':'Close'}, inplace=True)
        df_closed = df.iloc[:-1]
        return df_closed, str(df_closed.index[-1])
    except: return None, None

def get_live_tick(bq, symbol):
    try:
        tick = bq.tick(symbol)
        bid, ask = float(tick['bid']), float(tick['ask'])
        return bid, ask, (ask - bid)
    except: return None, None, None

# =====================================================================
# [BAGIAN 5] MODUL STRATEGI
# =====================================================================
def cek_ts(symbol, df, state):
    if df is None or len(df) < 22: return None
    tgl = str(df.index[-1])
    if state.get(f"{symbol}_TS") == tgl: return None
    
    df['ATR'] = hitung_atr(df, ATR_PERIOD)
    curr = df.iloc[-1]
    lookback = df.iloc[-21:-1]
    atr_val = float(curr['ATR'])
    if pd.isna(atr_val) or atr_val <= 0: return None
    
    o, h, l, c = float(curr['Open']), float(curr['High']), float(curr['Low']), float(curr['Close'])
    low20, high20 = float(lookback['Low'].min()), float(lookback['High'].max())
    setup = None
    
    if l < low20:
        age = len(lookback) - lookback['Low'].values.argmin()
        wick = (min(o,c) - l) / (h - l) if (h-l)>0 else 0
        if c > low20 and age >= 4:
            tipe = "KUAT" if wick >= 0.5 else "LEMAH"
            setup = {"type": f"TS {tipe}", "dir": "BUY", "entry": low20 + (ENTRY_ATR*atr_val), "sl": l - (STOP_ATR*atr_val), "tf": TS_TIMEFRAME, "setup_time": tgl, "status": "WAITING", "trailing": True}
        elif c <= low20 and age >= 3:
            setup = {"type": "TS+", "dir": "BUY", "entry": low20, "sl": l - (STOP_ATR*atr_val), "tf": TS_TIMEFRAME, "setup_time": tgl, "status": "WAITING", "trailing": False}
            
    if h > high20:
        age = len(lookback) - lookback['High'].values.argmax()
        wick = (h - max(o,c)) / (h - l) if (h-l)>0 else 0
        if c < high20 and age >= 4:
            tipe = "KUAT" if wick >= 0.5 else "LEMAH"
            setup = {"type": f"TS {tipe}", "dir": "SELL", "entry": high20 - (ENTRY_ATR*atr_val), "sl": h + (STOP_ATR*atr_val), "tf": TS_TIMEFRAME, "setup_time": tgl, "status": "WAITING", "trailing": True}
        elif c >= high20 and age >= 3:
            setup = {"type": "TS+", "dir": "SELL", "entry": high20, "sl": h + (STOP_ATR*atr_val), "tf": TS_TIMEFRAME, "setup_time": tgl, "status": "WAITING", "trailing": False}
            
    state[f"{symbol}_TS"] = tgl
    return setup

def cek_8020(symbol, df, state):
    if df is None or len(df) < ATR_PERIOD + 1: return None
    tgl = str(df.index[-1])
    if state.get(f"{symbol}_8020") == tgl: return None
    
    df['ATR'] = hitung_atr(df, ATR_PERIOD)
    prev = df.iloc[-1]
    atr_val = float(prev['ATR'])
    if pd.isna(atr_val) or atr_val <= 0: return None
    
    o, h, l, c = float(prev['Open']), float(prev['High']), float(prev['Low']), float(prev['Close'])
    rng = h - l
    if rng < (MIN_CANDLE_ATR * atr_val): return None
    
    top, bot = h - (0.2*rng), l + (0.2*rng)
    setup = None
    
    if o >= top and c <= bot: 
        setup = {"type": "80-20 BUY", "dir": "BUY", "level_entry": l, "atr_val": atr_val, "tf": S8020_TIMEFRAME, "setup_time": tgl, "status": "WAITING"}
    elif o <= bot and c >= top: 
        setup = {"type": "80-20 SELL", "dir": "SELL", "level_entry": h, "atr_val": atr_val, "tf": S8020_TIMEFRAME, "setup_time": tgl, "status": "WAITING"}
        
    state[f"{symbol}_8020"] = tgl
    return setup

# =====================================================================
# [BAGIAN 6] PROGRAM UTAMA
# =====================================================================
def jalankan():
    now_utc = datetime.now(timezone.utc)
    now_wib = now_utc + timedelta(hours=7)
    waktu_proses = now_wib.strftime("%d %b %y, %H:%M WIB")
    today_str = now_wib.strftime("%Y-%m-%d")
    
    print(f"[MULAI] {waktu_proses}")
    
    state = load_json("state.json")
    active = load_json("active_setups.json")
    bq = Biquote()
    sinyal_kirim = []

    # =================================================================
    # [FASE 1] CEK WAKTU: MOMENTUM PINBALL (Khusus Jam 05:00 & 06:00)
    # =================================================================
    if PINBALL_STATUS == "ON":
        # 1. JAM 05:00 WIB - Cek RSI untuk Watchlist
        if now_wib.hour == 5 and state.get("pinball_watch_date") != today_str:
            watchlist = []
            for sym in PAIRS:
                df_d1, _ = get_data_biquote(bq, sym, "1d")
                if df_d1 is not None and len(df_d1) > 10:
                    rsi_val = hitung_lbr_rsi(df_d1)
                    if not pd.isna(rsi_val) and (rsi_val < 30 or rsi_val > 70):
                        watchlist.append(f"• {sym} (RSI: {rsi_val:.1f})")
            
            if watchlist:
                msg = (f"🔍 <b>PINBALL WATCHLIST</b> - {waktu_proses}\n"
                       f"Pair dengan RSI Ekstrem:\n" + "\n".join(watchlist) + 
                       f"\n\n👉 <i>Bot mengawasi Jam Pertama (05:00-06:00). Sinyal Entry dikirim jam 06:00.</i>")
                sinyal_kirim.append(msg)
            
            state["pinball_watch_date"] = today_str
            state["pinball_watch_pairs"] = [w.split(' ')[1] for w in watchlist] # Simpan nama pair saja
            
        # 2. JAM 06:00 WIB - Entry (Berdasarkan Watchlist)
        if now_wib.hour == 6 and state.get("pinball_entry_date") != today_str:
            watchlist_pairs = state.get("pinball_watch_pairs", [])
            for sym in watchlist_pairs:
                # Ambil data H1 untuk mencari candle jam 05:00
                df_h1, _ = get_data_biquote(bq, sym, "1h")
                if df_h1 is not None and not df_h1.empty:
                    # Filter candle H1 terakhir yang jam-nya 05:00
                    last_h1 = df_h1.iloc[-1]
                    if last_h1.name.hour == 5: # Memastikan ini candle jam 5
                        high_h1 = float(last_h1['High'])
                        low_h1 = float(last_h1['Low'])
                        
                        # Tentukan arah berdasarkan RSI sebelumnya
                        # (Kita bisa cek RSI lagi, atau simpan arah di state. Untuk simplifikasi, kita cek RSI lagi)
                        df_d1, _ = get_data_biquote(bq, sym, "1d")
                        rsi_val = hitung_lbr_rsi(df_d1) if df_d1 is not None else 50
                        
                        dir_setup = "BUY" if rsi_val < 30 else "SELL" if rsi_val > 70 else None
                        if dir_setup:
                            s_pinball = {
                                "type": f"PINBALL {dir_setup}", "dir": dir_setup, 
                                "entry": high_h1 if dir_setup == "BUY" else low_h1, 
                                "sl": low_h1 if dir_setup == "BUY" else high_h1, 
                                "tf": "1d", "setup_time": today_str, "status": "WAITING"
                            }
                            if sym not in active: active[sym] = {}
                            active[sym]["PINBALL"] = s_pinball
                            
                            msg = (f"🚨 <b>{sym}</b> - {s_pinball['type']} - {waktu_proses}\n"
                                   f"Entry: <code>{s_pinball['entry']:.5f}</code> ({dir_setup} Stop)\n"
                                   f"SL: <code>{s_pinball['sl']:.5f}</code>\n"
                                   f"<i>Segera pasang pending order di MT4.</i>")
                            sinyal_kirim.append(msg)
            
            state["pinball_entry_date"] = today_str
            state["pinball_watch_pairs"] = [] # Bersihkan watchlist setelah dipakai

    # =================================================================
    # [FASE 2] CEK SETUP BARU (TS & 80-20)
    # =================================================================
    for sym in PAIRS:
        bid, ask, spread = get_live_tick(bq, sym)
        if not bid: continue
        
        if TS_STATUS == "ON":
            df_ts, _ = get_data_biquote(bq, sym, TS_TIMEFRAME)
            s_ts = cek_ts(sym, df_ts, state)
            if s_ts:
                if sym not in active: active[sym] = {}
                active[sym]["TS"] = s_ts
                R = abs(s_ts['entry'] - s_ts['sl'])
                one_R = s_ts['entry'] + R if s_ts['dir'] == "BUY" else s_ts['entry'] - R
                msg = (f"🔍 <b>{sym}</b> - {s_ts['type']} - {waktu_proses}\n"
                       f"TF: {s_ts['tf'].upper()}\n"
                       f"Entry: <code>{s_ts['entry']:.5f}</code> ({s_ts['dir']} Stop)\n"
                       f"SL: <code>{s_ts['sl']:.5f}</code>\n"
                       f"1R: <code>{one_R:.5f}</code>")
                sinyal_kirim.append(msg)

        if S8020_STATUS == "ON":
            df_8020, _ = get_data_biquote(bq, sym, S8020_TIMEFRAME)
            s_8020 = cek_8020(sym, df_8020, state)
            if s_8020:
                if sym not in active: active[sym] = {}
                active[sym]["8020"] = s_8020
                target_exec = s_8020['level_entry'] - (EXEC_ATR * s_8020['atr_val']) if s_8020['dir'] == "BUY" else s_8020['level_entry'] + (EXEC_ATR * s_8020['atr_val'])
                target_warn = s_8020['level_entry'] - (WARNING_ATR * s_8020['atr_val']) if s_8020['dir'] == "BUY" else s_8020['level_entry'] + (WARNING_ATR * s_8020['atr_val'])
                jarak_exec = abs(s_8020['level_entry'] - target_exec)
                msg = (f"🔍 <b>{sym}</b> - {s_8020['type']} - {waktu_proses}\n"
                       f"TF: {s_8020['tf'].upper()}\n"
                       f"Entry: <code>{s_8020['level_entry']:.5f}</code> ({s_8020['dir']} Stop)\n"
                       f"Warn: <code>{target_warn:.5f}</code>\n"
                       f"Exec: <code>{target_exec:.5f}</code> (Jarak: {jarak_exec:.5f})")
                sinyal_kirim.append(msg)

    # =================================================================
    # [FASE 3] PANTAU TRIGGER, EXPIRY & TRAILING SL
    # =================================================================
    for sym in list(active.keys()):
        bid, ask, _ = get_live_tick(bq, sym)
        if not bid: continue
        
        for key in list(active[sym].keys()):
            s = active[sym][key]
            
            # --- EXPIRY (KADALUWARSA) ---
            df_check, current_candle_time = get_data_biquote(bq, sym, s['tf'])
            if df_check is not None and s.get('setup_time'):
                # Jika sudah ganti hari/candle dan belum tersentuh
                if current_candle_time != s['setup_time'] and s['status'] in ['WAITING', 'WARNING', 'EXECUTION']:
                    msg = f"⏰ <b>{sym}</b> - {s['type']} DIBATALKAN (Kadaluwarsa)\nHarga tidak menyentuh Entry sesuai batas waktu."
                    sinyal_kirim.append(msg)
                    del active[sym][key]
                    continue

            # --- LOGIKA 80-20 ---
            if key == "8020":
                dist = 0
                if s['dir'] == "BUY" and bid < s['level_entry']: dist = s['level_entry'] - bid
                elif s['dir'] == "SELL" and bid > s['level_entry']: dist = bid - s['level_entry']

                if s['status'] == 'WAITING' and dist >= (WARNING_ATR * s['atr_val']):
                    s['status'] = 'WARNING'
                    target_exec = s['level_entry'] - (EXEC_ATR * s['atr_val']) if s['dir'] == "BUY" else s['level_entry'] + (EXEC_ATR * s['atr_val'])
                    msg = f"⚠️ <b>{sym}</b> - WARN {s['type']} - {waktu_proses}\nTarget Pemicu: <code>{target_exec:.5f}</code>"
                    sinyal_kirim.append(msg)
                
                elif s['status'] == 'WARNING' and dist >= (EXEC_ATR * s['atr_val']):
                    s['status'] = 'EXECUTION'
                    msg = (f"🚨 <b>{sym}</b> - EXEC {s['type']} - {waktu_proses}\n"
                           f"👉 {s['dir'].title()} Stop: <code>{s['level_entry']:.5f}</code>\n"
                           f"🛡 SL: Low terendah hari ini")
                    sinyal_kirim.append(msg)
                
                elif s['status'] == 'EXECUTION':
                    if (s['dir'] == "BUY" and bid >= s['level_entry']) or (s['dir'] == "SELL" and bid <= s['level_entry']):
                        s['status'] = 'TRIGGERED'
                        msg = f"🔔 <b>{sym}</b> - TERSENGGOL - {waktu_proses}\nHarga: <code>{bid:.5f}</code>"
                        sinyal_kirim.append(msg)
                        
                elif s['status'] == 'TRIGGERED':
                    if df_check is not None and len(df_check) >= 3:
                        low3 = float(df_check['Low'].tail(3).min()) if s['dir'] == "BUY" else float(df_check['High'].tail(3).max())
                        if s['dir'] == "BUY" and low3 > s.get('sl_aktif', 0):
                            s['sl_aktif'] = low3
                            msg = f"🔄 <b>{sym}</b> - UPDATE SL - {waktu_proses}\nPindahkan SL ke: <code>{low3:.5f}</code>"
                            sinyal_kirim.append(msg)
                            
                    if now_wib.hour == 4 and now_wib.minute < 30 and not s.get('exit_warned'):
                        s['exit_warned'] = True
                        msg = f"⏰ <b>{sym}</b> - EXIT {s['type']} - {waktu_proses}\n👉 Segera tutup posisi di MT4."
                        sinyal_kirim.append(msg)
            
            # --- LOGIKA TS / TS+ ---
            elif key == "TS":
                if s['status'] == 'WAITING':
                    if (s['dir'] == "BUY" and bid >= s['entry']) or (s['dir'] == "SELL" and bid <= s['entry']):
                        s['status'] = 'TRIGGERED'
                        msg = f"🔔 <b>{sym}</b> - TERSENGGOL - {waktu_proses}\nHarga: <code>{bid:.5f}</code>"
                        sinyal_kirim.append(msg)
                
                elif s['status'] == 'TRIGGERED':
                    if s.get('trailing'):
                        if s['dir'] == "BUY" and bid > s['entry'] + (abs(s['entry']-s['sl'])*0.5):
                            new_sl = s['entry']
                            if new_sl > s['sl']:
                                s['sl'] = new_sl
                                msg = f"🔄 <b>{sym}</b> - UPDATE SL - {waktu_proses}\nPindahkan SL ke: <code>{new_sl:.5f}</code> (BE)."
                                sinyal_kirim.append(msg)

            # --- LOGIKA PINBALL ---
            elif key == "PINBALL":
                if s['status'] == 'WAITING':
                    if (s['dir'] == "BUY" and bid >= s['entry']) or (s['dir'] == "SELL" and bid <= s['entry']):
                        s['status'] = 'TRIGGERED'
                        msg = f"🔔 <b>{sym}</b> - TERSENGGOL - {waktu_proses}\nHarga: <code>{bid:.5f}</code>"
                        sinyal_kirim.append(msg)

    # =================================================================
    # [FASE 4] SIMPAN & KIRIM
    # =================================================================
    save_json("state.json", state)
    save_json("active_setups.json", active)
    
    if sinyal_kirim:
        for msg in sinyal_kirim:
            kirim_telegram(msg)
            time.sleep(1)
    else:
        print("[INFO] Tidak ada sinyal/setup baru.")

if __name__ == "__main__":
    jalankan()
