import asyncio
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 33754919
API_HASH = "cd3ec4b240056a9a1d5655d9971fa07f"
PHONE = "+916283370364"

async def main():
    action = sys.argv[1]
    
    # We use a file-backed session so it remembers the code request hash
    client = TelegramClient('bot_training_auth', API_ID, API_HASH)
    await client.connect()

    if action == "request":
        res = await client.send_code_request(PHONE)
        print("CODE_REQUESTED")
    elif action == "login":
        code = sys.argv[2]
        password = sys.argv[3] if len(sys.argv) > 3 else None
        
        try:
            await client.sign_in(phone=PHONE, code=code, password=password)
            session_str = client.session.save()
            print("LOGIN_SUCCESS")
            # Convert file session to string session to give to user
            sc = TelegramClient(StringSession(), API_ID, API_HASH)
            sc.session.server_address = client.session.server_address
            sc.session.port = client.session.port
            sc.session.auth_key = client.session.auth_key
            print(sc.session.save())
        except Exception as e:
            print(f"LOGIN_ERROR: {e}")
            
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
