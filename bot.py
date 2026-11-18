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
                return
        except Exception:
            time.sleep(5)
    print("[ERROR] Gagal kirim Telegram setelah 3x percobaan.")

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
        df_closed = df.iloc[:-1] # Buang candle berjalan
        return df_closed, str(df_closed.index[-1])
    except Exception:
        return None, None

def get_live_tick(bq, symbol):
    try:
        tick = bq.tick(symbol)
        bid, ask = float(tick['bid']), float(tick['ask'])
        return bid, ask, (ask - bid)
    except:
        return None, None, None

# =====================================================================
# [BAGIAN 5] ANALISA SETUP
# =====================================================================
def cek_8020(symbol, df, state):
    if df is None or len(df) < 2: return None
    tgl = str(df.index[-1])
    if state.get(f"{symbol}_D1") == tgl: return None
    
    prev = df.iloc[-1]
    o, h, l, c = float(prev['Open']), float(prev['High']), float(prev['Low']), float(prev['Close'])
    rng = h - l
    if rng <= 0: return None
    
    top, bot = h - (0.2*rng), l + (0.2*rng)
    setup = None
    if o >= top and c <= bot:
        setup = {"dir": "BUY", "entry": h, "sl": l - (rng*0.1), "type": "80-20 BUY", "desc": "Pembalikan dari penurunan tajam."}
    elif o <= bot and c >= top:
        setup = {"dir": "SELL", "entry": l, "sl": h + (rng*0.1), "type": "80-20 SELL", "desc": "Pembalikan dari kenaikan tajam."}
        
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
            setup = {"dir": "BUY", "entry": low20 + (ENTRY_ATR*atr), "sl": l - (STOP_ATR*atr), "type": f"TS {tipe}", "desc": f"Fakeout. Ekor {wick*100:.0f}%.", "trailing": True}
        elif c <= low20 and age >= min_tsp:
            setup = {"dir": "BUY", "entry": low20, "sl": l - (STOP_ATR*atr), "type": "TS+", "desc": "Breakout. Close di bawah Low.", "trailing": False}
            
    if h > high20:
        age = len(lookback) - lookback['High'].values.argmax()
        wick = (h - max(o,c)) / (h - l) if (h-l)>0 else 0
        if c < high20 and age >= min_ts:
            tipe = "KUAT" if wick >= 0.5 else "LEMAH"
            setup = {"dir": "SELL", "entry": high20 - (ENTRY_ATR*atr), "sl": h + (STOP_ATR*atr), "type": f"TS {tipe}", "desc": f"Fakeout. Ekor {wick*100:.0f}%.", "trailing": True}
        elif c >= high20 and age >= min_tsp:
            setup = {"dir": "SELL", "entry": high20, "sl": h + (STOP_ATR*atr), "type": "TS+", "desc": "Breakout. Close di atas High.", "trailing": False}
            
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
            R = abs(v['entry'] - v['sl'])
            one_R = v['entry'] + R if v['dir'] == "BUY" else v['entry'] - R
            spread_R = spread / R if R > 0 else 0
            
            filter_msg = ""
            if spread_R > SPREAD_MAX_R:
                filter_msg = f"\n❌ <b>FILTER SPREAD: LEWATI SINYAL INI</b>\nSpread/R terlalu besar ({spread_R:.2f}). Risiko tidak sebanding."
            
            tf_label = "H4" if "TS" in v['type'] else "D1"
            msg = (f"⚠️ <b>[SETUP DITEMUKAN: {v['type']}]</b>\n"
                   f"Pair: <b>{sym}</b> ({tf_label})\n"
                   f"Waktu: {get_wib_time()}\n"
                   f"👉 <b>Entry:</b> <code>{v['entry']:.5f}</code> ({v['dir']} STOP)\n"
                   f"🛡 <b>SL:</b> <code>{v['sl']:.5f}</code>\n"
                   f"🎯 <b>Target 1R:</b> <code>{one_R:.5f}</code>\n"
                   f"ℹ️ <i>{v['desc']}</i>{filter_msg}\n"
                   f"<i>Bot mengawasi harga. Segera pasang pending order jika belum.</i>")
            
            sinyal_kirim.append(msg)
            if sym not in active: active[sym] = {}
            v['status'] = 'WAITING'
            v['time_setup'] = get_wib_time()
            v['tgl_setup'] = str(df_h4.index[-1]) if df_h4 is not None else ""
            active[sym][k] = v

    for sym in list(active.keys()):
        bid, ask, _ = get_live_tick(bq, sym)
        if not bid: continue
        
        for key in list(active[sym].keys()):
            s = active[sym][key]
            
            if s['status'] == 'WAITING':
                if (s['dir'] == "BUY" and bid >= s['entry']) or (s['dir'] == "SELL" and bid <= s['entry']):
                    s['status'] = 'TRIGGERED'
                    tf_label = "H4" if "TS" in s['type'] else "D1"
                    msg = (f"🔔 <b>LAPORAN: HARGA TERSENGGOL</b>\n"
                           f"Pair: <b>{sym}</b> ({tf_label} - {s['type']})\n"
                           f"Harga Live: <code>{bid:.5f}</code>\n\n"
                           f"👉 <i>Jika Anda sudah pasang {s['dir']} Stop, posisi Anda kini sudah TERBUKA. Cek MT4 Anda!</i>")
                    sinyal_kirim.append(msg)
            
            elif s['status'] == 'TRIGGERED':
                if s.get('trailing'):
                    if s['dir'] == "BUY" and bid > s['entry'] + (abs(s['entry']-s['sl'])*0.5):
                        new_sl = s['entry']
                        if new_sl > s['sl']:
                            s['sl'] = new_sl
                            msg = (f"🔄 <b>UPDATE SL (Trailing)</b>\n"
                                   f"Pair: <b>{sym}</b>\n"
                                   f"Harga Live: <code>{bid:.5f}</code>\n"
                                   f"👉 <i>Pindahkan SL Anda ke <code>{new_sl:.5f}</code> (Break Even).</i>")
                            sinyal_kirim.append(msg)
            
            if s['status'] == 'WAITING' and s.get('tgl_setup'):
                if df_h4 is not None and s['tgl_setup'] != str(df_h4.index[-1]):
                    tf_label = "H4" if "TS" in s['type'] else "D1"
                    msg = (f"⚠️ <b>SETUP EXPIRED / BATAL</b>\n"
                           f"Pair: <b>{sym}</b> ({tf_label} - {s['type']})\n"
                           f"Candle baru sudah terbentuk dan harga tidak menyentuh Entry.\n"
                           f"👉 <i>Segera BATALKAN pending order Anda di MT4.</i>")
                    sinyal_kirim.append(msg)
                    del active[sym][key]

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
