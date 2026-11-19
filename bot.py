import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import time
from biquote import Biquote

# =====================================================================
# [BAGIAN 1] PENGATURAN
# =====================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF", 
    "EURGBP", "GBPJPY", "EURJPY", "NZDCHF", "NZDJPY", "EURCHF", "GBPCHF", 
    "AUDCAD", "EURCAD", "GBPCAD", "XAUUSD", "BTCUSD"
]

SPREAD_MAX_R = 0.15
ENTRY_ATR = 0.15
STOP_ATR = 0.04

# Pengaturan 80-20
ATR_PERIOD_8020 = 14
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
# [BAGIAN 3] TELEGRAM
# =====================================================================
def kirim_telegram(pesan):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": pesan, "parse_mode": "HTML"}
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

def get_data_biquote(bq, symbol, timeframe):
    try:
        bars = bq.ohlc(symbol, interval=timeframe, limit=50)
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
# [BAGIAN 5] ANALISA SETUP
# =====================================================================
def cek_8020(symbol, df, state):
    if df is None or len(df) < ATR_PERIOD_8020 + 1: return None
    tgl = str(df.index[-1])
    if state.get(f"{symbol}_D1") == tgl: return None
    
    df['ATR'] = hitung_atr(df, ATR_PERIOD_8020)
    prev = df.iloc[-1]
    atr_d1 = float(prev['ATR'])
    
    if pd.isna(atr_d1) or atr_d1 <= 0: return None
    
    o, h, l, c = float(prev['Open']), float(prev['High']), float(prev['Low']), float(prev['Close'])
    rng = h - l
    
    if rng < (MIN_CANDLE_ATR * atr_d1): return None
    
    top, bot = h - (0.2*rng), l + (0.2*rng)
    setup = None
    
    if o >= top and c <= bot: 
        setup = {"dir": "BUY", "level_entry": l, "atr_d1": atr_d1, "type": "80-20 BUY", "status": "WAITING", "desc": "Candle turun tajam (Bearish)."}
    elif o <= bot and c >= top: 
        setup = {"dir": "SELL", "level_entry": h, "atr_d1": atr_d1, "type": "80-20 SELL", "status": "WAITING", "desc": "Candle naik tajam (Bullish)."}
        
    state[f"{symbol}_D1"] = tgl
    return setup

def cek_ts(symbol, df, state, tf_name, min_ts, min_tsp):
    if df is None or len(df) < 22: return None
    tgl = str(df.index[-1])
    if state.get(f"{symbol}_{tf_name}") == tgl: return None
    
    df['ATR'] = hitung_atr(df)
    curr = df.iloc[-1]
    lookback = df.iloc[-21:-1]
    atr = float(curr['ATR'])
    if pd.isna(atr) or atr <= 0: return None
    
    o, h, l, c = float(curr['Open']), float(curr['High']), float(curr['Low']), float(curr['Close'])
    low20, high20 = float(lookback['Low'].min()), float(lookback['High'].max())
    setup = None
    
    if l < low20:
        age = len(lookback) - lookback['Low'].values.argmin()
        wick = (min(o,c) - l) / (h - l) if (h-l)>0 else 0
        if c > low20 and age >= min_ts:
            tipe = "KUAT" if wick >= 0.5 else "LEMAH"
            setup = {"dir": "BUY", "entry": low20 + (ENTRY_ATR*atr), "sl": l - (STOP_ATR*atr), "type": f"TS {tipe}", "desc": f"Low lama candle -{age} ({low20:.2f}). Ekor {wick*100:.0f}%.", "status": "WAITING", "atr_h4": atr}
        elif c <= low20 and age >= min_tsp:
            setup = {"dir": "BUY", "entry": low20, "sl": l - (STOP_ATR*atr), "type": "TS+", "desc": f"Low lama candle -{age} ({low20:.2f}). Breakout.", "status": "WAITING", "atr_h4": atr}
            
    if h > high20:
        age = len(lookback) - lookback['High'].values.argmax()
        wick = (h - max(o,c)) / (h - l) if (h-l)>0 else 0
        if c < high20 and age >= min_ts:
            tipe = "KUAT" if wick >= 0.5 else "LEMAH"
            setup = {"dir": "SELL", "entry": high20 - (ENTRY_ATR*atr), "sl": h + (STOP_ATR*atr), "type": f"TS {tipe}", "desc": f"High lama candle -{age} ({high20:.2f}). Ekor {wick*100:.0f}%.", "status": "WAITING", "atr_h4": atr}
        elif c >= high20 and age >= min_tsp:
            setup = {"dir": "SELL", "entry": high20, "sl": h + (STOP_ATR*atr), "type": "TS+", "desc": f"High lama candle -{age} ({high20:.2f}). Breakout.", "status": "WAITING", "atr_h4": atr}
            
    state[f"{symbol}_{tf_name}"] = tgl
    return setup

# =====================================================================
# [BAGIAN 6] PROGRAM UTAMA
# =====================================================================
def jalankan():
    print(f"[MULAI] {get_wib_time()}")
    state = load_json("state.json")
    active = load_json("active_setups.json")
    bq = Biquote()
    sinyal_kirim = []

    # --- FASE 1: CARI SETUP BARU ---
    for sym in PAIRS:
        bid, ask, spread = get_live_tick(bq, sym)
        if not bid: continue
        
        df_h4, _ = get_data_biquote(bq, sym, "4h")
        df_d1, _ = get_data_biquote(bq, sym, "1d")
        
        setups = {}
        s_8020 = cek_8020(sym, df_d1, state)
        if s_8020: setups["8020"] = s_8020
        
        s_ts = cek_ts(sym, df_h4, state, "H4", 4, 3)
        if s_ts: setups["TS"] = s_ts
        
        for k, v in setups.items():
            if sym not in active: active[sym] = {}
            active[sym][k] = v
            
            if k == "8020":
                # [TAMBAHAN BARU] Notifikasi Setup Awal 80-20
                target_exec = v['level_entry'] - (EXEC_ATR * v['atr_d1']) if v['dir'] == "BUY" else v['level_entry'] + (EXEC_ATR * v['atr_d1'])
                target_warn = v['level_entry'] - (WARNING_ATR * v['atr_d1']) if v['dir'] == "BUY" else v['level_entry'] + (WARNING_ATR * v['atr_d1'])
                
                msg = (f"🔍 <b>[SETUP AWAL: {v['type']}]</b>\n"
                       f"Pair: <b>{sym}</b> (D1)\n"
                       f"👉 <b>Level Entry:</b> <code>{v['level_entry']:.5f}</code> ({v['dir']} STOP)\n"
                       f"⚠️ <b>Batas Warning:</b> <code>{target_warn:.5f}</code>\n"
                       f"🚨 <b>Batas Eksekusi:</b> <code>{target_exec:.5f}</code>\n"
                       f"ℹ️ <i>{v['desc']}</i>\n"
                       f"<i>Bot akan mengawasi. Anda hanya akan dihubungi lagi saat harga menyentuh Warning atau Eksekusi.</i>")
                sinyal_kirim.append(msg)
            else:
                # Notif Setup TS / TS+
                R = abs(v['entry'] - v['sl'])
                one_R = v['entry'] + R if v['dir'] == "BUY" else v['entry'] - R
                msg = (f"⚠️ <b>[SETUP DITEMUKAN: {v['type']}]</b>\n"
                       f"Pair: <b>{sym}</b> (H4)\n"
                       f"👉 <b>Entry:</b> <code>{v['entry']:.5f}</code> ({v['dir']} STOP)\n"
                       f"🛡 <b>SL:</b> <code>{v['sl']:.5f}</code>\n"
                       f"🎯 <b>Target 1R:</b> <code>{one_R:.5f}</code>\n"
                       f"ℹ️ <i>{v['desc']}</i>\n"
                       f"<i>Segera pasang pending order.</i>")
                sinyal_kirim.append(msg)

    # --- FASE 2: PANTAU TRIGGER & PENGINGAT ---
    for sym in list(active.keys()):
        bid, ask, _ = get_live_tick(bq, sym)
        if not bid: continue
        
        for key in list(active[sym].keys()):
            s = active[sym][key]
            
            # ==========================================
            # LOGIKA KHUSUS 80-20 (Sistem 3 Tahap)
            # ==========================================
            if key == "8020":
                # PERBAIKAN FATAL: Hitung jarak HANYA JIKA searah dengan setup
                dist = 0
                if s['dir'] == "BUY" and bid < s['level_entry']:
                    dist = s['level_entry'] - bid
                elif s['dir'] == "SELL" and bid > s['level_entry']:
                    dist = bid - s['level_entry']

                # Tahap 1: Warning
                if s['status'] == 'WAITING' and dist >= (WARNING_ATR * s['atr_d1']):
                    s['status'] = 'WARNING'
                    target_exec = s['level_entry'] - (EXEC_ATR * s['atr_d1']) if s['dir'] == "BUY" else s['level_entry'] + (EXEC_ATR * s['atr_d1'])
                    msg = (f"⚠️ <b>[WARNING: {s['type']} - {sym}]</b>\n"
                           f"Harga mulai menjebol level kemarin.\n"
                           f"🎯 <b>Target Eksekusi (0.1 ATR):</b> <code>{target_exec:.5f}</code>\n"
                           f"<i>Bersiaplah di MT4.</i>")
                    sinyal_kirim.append(msg)
                
                # Tahap 2: Eksekusi
                elif s['status'] == 'WARNING' and dist >= (EXEC_ATR * s['atr_d1']):
                    s['status'] = 'EXECUTION'
                    sl_temp = bid 
                    msg = (f"🚨 <b>[EKSEKUSI: {s['type']} - {sym}]</b>\n"
                           f"Fakeout Terkonfirmasi!\n"
                           f"👉 <b>SEGERA PASANG {s['dir']} STOP DI:</b> <code>{s['level_entry']:.5f}</code>\n"
                           f"🛡 <b>SL Sementara:</b> <code>{sl_temp:.5f}</code>\n"
                           f"⚠️ <i>Geser SL jika harga bergerak lebih jauh sebelum order tersentuh.</i>")
                    sinyal_kirim.append(msg)
                
                # Tahap 3: Tersenggol & Trailing
                elif s['status'] == 'EXECUTION':
                    is_triggered = (s['dir'] == "BUY" and bid >= s['level_entry']) or (s['dir'] == "SELL" and bid <= s['level_entry'])
                    if is_triggered:
                        s['status'] = 'TRIGGERED'
                        msg = f"🔔 <b>[TERSENGGOL: {s['type']} - {sym}]</b>\nHarga menyentuh Entry. Posisi Anda harusnya sudah terbuka."
                        sinyal_kirim.append(msg)
                        
                elif s['status'] == 'TRIGGERED':
                    df_d1, _ = get_data_biquote(bq, sym, "1d")
                    if df_d1 is not None and len(df_d1) >= 3:
                        low3 = float(df_d1['Low'].tail(3).min()) if s['dir'] == "BUY" else float(df_d1['High'].tail(3).max())
                        if s['dir'] == "BUY" and low3 > s.get('sl_aktif', 0):
                            s['sl_aktif'] = low3
                            msg = f"🔄 <b>[UPDATE SL: {sym}]</b>\nPindahkan SL Anda ke: <code>{low3:.5f}</code> (Mengikuti Low 3 Candle)."
                            sinyal_kirim.append(msg)
            
            # ==========================================
            # LOGIKA KHUSUS TS / TS+
            # ==========================================
            else:
                if s['status'] == 'WAITING':
                    if (s['dir'] == "BUY" and bid >= s['entry']) or (s['dir'] == "SELL" and bid <= s['entry']):
                        s['status'] = 'TRIGGERED'
                        msg = (f"🔔 <b>LAPORAN: HARGA TERSENGGOL</b>\nPair: <b>{sym}</b> (H4 - {s['type']})\nHarga Live: <code>{bid:.5f}</code>\n👉 <i>Cek MT4 Anda.</i>")
                        sinyal_kirim.append(msg)
                
                elif s['status'] == 'TRIGGERED':
                    if s.get('trailing'):
                        if s['dir'] == "BUY" and bid > s['entry'] + (abs(s['entry']-s['sl'])*0.5):
                            new_sl = s['entry']
                            if new_sl > s['sl']:
                                s['sl'] = new_sl
                                msg = f"🔄 <b>UPDATE SL (Trailing)</b>\nPair: <b>{sym}</b>\nPindahkan SL ke <code>{new_sl:.5f}</code> (Break Even)."
                                sinyal_kirim.append(msg)

    # --- FASE 3: SIMPAN & KIRIM ---
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
