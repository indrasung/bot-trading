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

def hitung_adx_wilder(df, period=14):
    high, low, close = df['High'], df['Low'], df['Close']
    tr1 = pd.DataFrame(high - low)
    tr2 = pd.DataFrame(abs(high - close.shift(1)))
    tr3 = pd.DataFrame(abs(low - close.shift(1)))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean() / atr)
    
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return adx.iloc[-1]

def main():
    print("=== MULAI UJI BUTA: RAKIT H1 MENJADI D1 (VERSI 2) ===")
    bq = Biquote()
    
    for sym in TEST_PAIRS:
        print(f"\n--- Mengambil data {sym} ---")
        # Ambil data
        bars = bq.ohlc(sym, interval="1h", limit=1000)
        if not bars: continue
            
        df = pd.DataFrame(bars)
        
        # 1. Rename kolom agar sesuai standar
        df.rename(columns={'open':'Open', 'high':'High', 'low':'Low', 'close':'Close'}, inplace=True)
        
        # 2. Ubah openTime menjadi format waktu (datetime) dan jadikan index
        df['openTime'] = pd.to_datetime(df['openTime'])
        df.set_index('openTime', inplace=True)
        
        # 3. Buang candle yang sedang berjalan (isOpen == True)
        if 'isOpen' in df.columns:
            df = df[~df['isOpen']]
            
        # 4. Geser waktu dari UTC ke server MT4 (asumsi GMT+2)
        # Kita hilangkan zona waktu (Z) agar bisa dihitung, lalu tambah 2 jam
        df.index = df.index.tz_localize(None) + pd.Timedelta(hours=2)
        
        # 5. Rakit H1 menjadi D1
        df_d1 = df.resample('1D').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
        }).dropna()
        
        # 6. Ambil candle D1 terakhir yang sudah tutup
        candle_terakhir = df_d1.iloc[-1]
        tanggal_candle = df_d1.index[-1].strftime("%d %b %Y")
        
        # 7. Hitung Indikator
        rsi_val = hitung_rsi_momentum(df_d1)
        adx_val = hitung_adx_wilder(df_d1)
        
        print(f"Candle D1 yang diuji (Tanggal): {tanggal_candle}")
        print(f"OHLC: O={candle_terakhir['Open']:.5f} H={candle_terakhir['High']:.5f} L={candle_terakhir['Low']:.5f} C={candle_terakhir['Close']:.5f}")
        print(f"Hasil RSI : {rsi_val:.2f}")
        print(f"Hasil ADX : {adx_val:.2f}")

if __name__ == "__main__":
    main()
