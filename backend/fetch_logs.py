import os
import sys
from dotenv import load_dotenv

load_dotenv()
from supabase_client import get_client

print("Fetching directly from supabase...")
try:
    result = get_client().table('conversations').select('*').order('timestamp', desc=True).limit(20).execute()
    data = result.data or []
    print(f"Found {len(data)} conversations directly.")
    data.reverse()
    for c in data:
        print(f"[{c.get('timestamp')}] {c.get('role', '').upper()}: {c.get('content')}")
except Exception as e:
    print(f"Error fetching conversations: {e}")
