import sys
import os
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from brain import generate_response
import logging

logging.basicConfig(level=logging.DEBUG)

context = {
    "sentiment": type("obj", (object,), {"emotion": "neutral", "intensity": 5, "energy": 5, "sarcasm": False})(),
    "time_label": "afternoon"
}

try:
    resp = generate_response(
        user_message="Mera b'day my not urs",
        context=context,
        conversation_history=[],
        core_rules="act like Sifra"
    )
    print("RESPONSE:", resp)
except Exception as e:
    import traceback
    traceback.print_exc()
