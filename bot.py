import requests

# Token dan Chat ID Anda
TELEGRAM_TOKEN = "9221976474:AAGK4Lz8h6GzLu1wuvoQvLoGoWxA9RdSiRs"
TELEGRAM_CHAT_ID = "6917045544"

def send_test():
    domain = "api.telegram.org"
    url = f"https://{domain}/bot{TELEGRAM_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": "🎉 *TES TAHAP 1 BERHASIL!*\nKoneksi antara GitHub Actions dan Telegram HP Anda sudah 100% terhubung lancar.",
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Status HTTP: {response.status_code}")
        print(f"Respon Telegram: {response.text}")
    except Exception as e:
        print(f"Error Koneksi: {e}")

if __name__ == "__main__":
    send_test()
