"""
SIFRA:MIND — Session Generator.
Run this ONCE on your local machine to log into your Telegram account.
It will produce a session string you set as TELEGRAM_SESSION env var.

Usage:
    python generate_session.py
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 33754919
API_HASH = "cd3ec4b240056a9a1d5655d9971fa07f"


async def main():
    print("=" * 50)
    print("  SIFRA:MIND — Telegram Session Generator")
    print("=" * 50)
    print()
    print("This will log into your Telegram account ONCE.")
    print("After login, you'll get a session string.")
    print("Set it as TELEGRAM_SESSION in your Vercel env vars.")
    print()

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start()

    session_string = client.session.save()

    print()
    print("=" * 50)
    print("  ✅ LOGIN SUCCESSFUL!")
    print("=" * 50)
    print()
    print("Your session string (copy the ENTIRE string below):")
    print()
    print(session_string)
    print()
    print("=" * 50)
    print("NOW DO THIS:")
    print("1. Copy the session string above")
    print("2. Go to Vercel → Settings → Environment Variables")
    print("3. Add: TELEGRAM_SESSION = <paste the string>")
    print("4. Redeploy your backend")
    print("=" * 50)
    print()
    input("Press Enter to exit...")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
