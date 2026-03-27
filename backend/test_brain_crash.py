import sys
import os
from dotenv import load_dotenv

load_dotenv()
from brain import generate_response
import logging

logging.basicConfig(level=logging.DEBUG)

context = {
    "sentiment": type("obj", (object,), {"emotion": "frustrated", "intensity": 8, "energy": 8, "sarcasm": False})(),
    "time_label": "morning"
}

history = [
    {"role": "user", "content": "Okay okay apka birthday kab hai"},
    {"role": "sifra", "content": "4th july 🌻 tum kyun pooch rahe ho?"},
    {"role": "user", "content": "Mera bday yaad hai apko ??"},
    {"role": "sifra", "content": "haan! 4 july 2001 ko aayi thi main 🌟 bas, yeh yaad hai? arre 25 saal ho gaye hain, kya ho raha hai? 😂"}
]

try:
    resp = generate_response(
        user_message="Mera b'day my not urs",
        context=context,
        conversation_history=history,
        core_rules="act like Sifra"
    )
    print("RESPONSE:", resp)
except Exception as e:
    import traceback
    traceback.print_exc()
