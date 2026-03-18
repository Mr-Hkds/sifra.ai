"""
Local Telegram Poller for Testing SIFRA:MIND without Vercel/ngrok.
This script polls the Telegram API for updates and forwards them
to your local Flask server as if they were webhooks.
"""

import os
import time
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
FLASK_URL = "http://127.0.0.1:5000/webhook/telegram"

def delete_webhook():
    """Telegram won't allow getUpdates if a webhook is currently active."""
    print("Deleting any existing webhooks on Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook"
    requests.post(url)

def poll_telegram():
    print(f"Starting local Telegram tunnel...\nForwarding messages to {FLASK_URL}\nPress Ctrl+C to stop.")
    offset = None
    
    headers = {}
    if WEBHOOK_SECRET:
        headers["X-Telegram-Bot-Api-Secret-Token"] = WEBHOOK_SECRET

    while True:
        try:
            # 1. Fetch updates
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"timeout": 10, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset
                
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    update_id = update["update_id"]
                    offset = update_id + 1  # mark as read
                    
                    # 2. Forward to local Flask server
                    print(f"\n[➡] Received message from Telegram, forwarding to local Flask...")
                    try:
                        flask_resp = requests.post(FLASK_URL, json=update, headers=headers, timeout=10)
                        if flask_resp.status_code == 200:
                            print(f"[✅] Flask processed successfully (200 OK)")
                        else:
                            print(f"[❌] Flask error: {flask_resp.status_code}")
                    except Exception as e:
                        print(f"[❌] Could not reach local Flask server: {e}")
                        print("    (Make sure 'python app.py' is running in another terminal!)")
            
        except Exception as e:
            print(f"[!] Polling error: {e}")
            time.sleep(2)
            
if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env")
        exit(1)
        
    delete_webhook()
    try:
        poll_telegram()
    except KeyboardInterrupt:
        print("\nStopped.")
