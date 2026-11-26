import pandas as pd
import numpy as np
from biquote import Biquote
import pandas_ta as ta

TEST_PAIRS = ["EURUSD", "GBPUSD", "NZDUSD", "USDCHF"]

def hitung_rsi_momentum(df):
    # Rumus LBR/RSI persis MT4: RSI(3) dari Momentum(1)
    momentum = (df['Close'] / df['Close'].shift(1)) * 100
    delta = momentum.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/3, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/3, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def main():
    print("=== MULAI UJI BUTA: RAKIT H1 MENJADI D1 (VERSI 4) ===")
    bq = Biquote()
    
    for sym in TEST_PAIRS:
        print(f"\n--- Mengambil data {sym} ---")
        # Naikkan limit ke 5000 agar ADX punya data 200+ hari untuk 'pemanasan'
        bars = bq.ohlc(sym, interval="1h", limit=5000)
        if not bars: continue
            
        df = pd.DataFrame(bars)
        df.rename(columns={'open':'Open', 'high':'High', 'low':'Low', 'close':'Close'}, inplace=True)
        df['openTime'] = pd.to_datetime(df['openTime'])
        df.set_index('openTime', inplace=True)
        
        # Buang candle yang sedang berjalan
        if 'isOpen' in df.columns:
            df = df[~df['isOpen']]
            
        # Geser waktu UTC ke GMT+2 (Server MT4)
        df.index = df.index.tz_localize(None) + pd.Timedelta(hours=2)
        
        # Rakit H1 menjadi D1
        df_d1 = df.resample('1D').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
        }).dropna()
        
        # Ambil data sampai kemarin (index -2 adalah kemarin, index -1 adalah hari ini yang belum tutup)
        df_d1_kemarin = df_d1.iloc[:-1]
        candle_kemarin = df_d1_kemarin.iloc[-1]
        tanggal_kemarin = df_d1_kemarin.index[-1].strftime("%d %b %Y")
        
        # Hitung RSI dengan rumus manual kita
        rsi_val = hitung_rsi_momentum(df_d1_kemarin)
        
        # Hitung ADX menggunakan pandas_ta (Standar Industri)
        adx_df = ta.adx(df_d1_kemarin['High'], df_d1_kemarin['Low'], df_d1_kemarin['Close'], length=14)
        # pandas_ta menghasilkan kolom 'ADX_14', kita ambil nilai terakhirnya
        adx_val = adx_df['ADX_14'].iloc[-1] if adx_df is not None else float('nan')
        
        print(f"Candle D1 KEMARIN (Tanggal): {tanggal_kemarin}")
        print(f"OHLC: O={candle_kemarin['Open']:.5f} H={candle_kemarin['High']:.5f} L={candle_kemarin['Low']:.5f} C={candle_kemarin['Close']:.5f}")
        print(f"Hasil RSI : {rsi_val:.2f}")
        print(f"Hasil ADX : {adx_val:.2f}")

if __name__ == "__main__":
    main()
