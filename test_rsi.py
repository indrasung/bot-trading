import pandas as pd
from biquote import Biquote

def main():
    print("=== MULAI UJI BUTA: DEBUG DATA BIQUOTE ===")
    bq = Biquote()
    
    # Kita hanya ambil 5 data untuk melihat bentuk mentahnya
    sym = "EURUSD"
    print(f"\n--- Mengambil 5 data H1 {sym} ---")
    bars = bq.ohlc(sym, interval="1h", limit=5)
    
    if not bars:
        print("Gagal ambil data.")
        return
        
    df = pd.DataFrame(bars)
    
    print("\n[1] BENTUK DATA MENTAH:")
    print(df)
    
    print("\n[2] TIPE DATA SETIAP KOLOM:")
    print(df.dtypes)
    
    print("\n[3] NAMA INDEX (BARIS):")
    print(df.index)

if __name__ == "__main__":
    main()
