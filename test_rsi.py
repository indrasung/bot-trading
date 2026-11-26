import pandas as pd
import numpy as np
from biquote import Biquote

TEST_PAIRS = ["EURUSD", "GBPUSD", "NZDUSD", "USDCHF"]

def hitung_rsi_momentum(df):
    momentum = (df['Close'] / df['Close'].shift(1)) * 100
    delta = momentum.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/3, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/3, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

# --- INI BAGIAN YANG DIPERBAIKI ---
def hitung_adx_wilder(df, period=14):
    high, low, close = df['High'], df['Low'], df['Close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    # Menggunakan .where() Pandas agar index waktu tidak hilang
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return adx.iloc[-1]
# ----------------------------------

def main():
    print("=== MULAI UJI BUTA: RAKIT H1 MENJADI D1 (VERSI 3) ===")
    bq = Biquote()
    
    for sym in TEST_PAIRS:
        print(f"\n--- Mengambil data {sym} ---")
        bars = bq.ohlc(sym, interval="1h", limit=1000)
        if not bars: continue
            
        df = pd.DataFrame(bars)
        df.rename(columns={'open':'Open', 'high':'High', 'low':'Low', 'close':'Close'}, inplace=True)
        df['openTime'] = pd.to_datetime(df['openTime'])
        df.set_index('openTime', inplace=True)
        
        if 'isOpen' in df.columns:
            df = df[~df['isOpen']]
            
        df.index = df.index.tz_localize(None) + pd.Timedelta(hours=2)
        
        df_d1 = df.resample('1D').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
        }).dropna()
        
        # Kita cetak dua tanggal: Hari ini (Live) dan Kemarin (Closed)
        candle_kemarin = df_d1.iloc[-2] # Index -2 adalah kemarin (25 Nov)
        tanggal_kemarin = df_d1.index[-2].strftime("%d %b %Y")
        
        rsi_kemarin = hitung_rsi_momentum(df_d1.iloc[:-1]) # Hitung s/d kemarin
        adx_kemarin = hitung_adx_wilder(df_d1.iloc[:-1])
        
        print(f"Candle D1 KEMARIN (Tanggal): {tanggal_kemarin}")
        print(f"OHLC: O={candle_kemarin['Open']:.5f} H={candle_kemarin['High']:.5f} L={candle_kemarin['Low']:.5f} C={candle_kemarin['Close']:.5f}")
        print(f"Hasil RSI : {rsi_kemarin:.2f}")
        print(f"Hasil ADX : {adx_kemarin:.2f}")

if __name__ == "__main__":
    main()
