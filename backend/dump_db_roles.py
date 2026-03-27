import logging
import json
from dotenv import load_dotenv

load_dotenv()
from supabase_client import get_client

logging.basicConfig(level=logging.ERROR)

def check_db():
    client = get_client()
    res = client.table("conversations").select("*").order("timestamp", desc=True).limit(20).execute()
    
    for row in reversed(res.data):
        print(f"[{row['timestamp']}] Role: {row['role']} | Msg: {row['content']}")

if __name__ == "__main__":
    check_db()
