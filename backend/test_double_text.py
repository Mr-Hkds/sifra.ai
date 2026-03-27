import sys
import os
from dotenv import load_dotenv

load_dotenv()
from brain import generate_response
import logging

logging.basicConfig(level=logging.DEBUG)

context = {
    "sentiment": type("obj", (object,), {"emotion": "neutral", "intensity": 5, "energy": 5, "sarcasm": False})(),
    "time_label": "afternoon"
}

# Two user messages perfectly consecutive
history = [
    {"role": "user", "content": "First message"},
    {"role": "user", "content": "Second message"} # This causes history to have User, User, User (with current message)
]

try:
    resp = generate_response(
        user_message="Third user message in a row!",
        context=context,
        conversation_history=history,
        core_rules="act like Sifra"
    )
    print("FINAL RESPONSE:", resp)
except Exception as e:
    import traceback
    traceback.print_exc()
