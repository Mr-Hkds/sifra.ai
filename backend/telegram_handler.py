"""
Telegram webhook handler — processes incoming messages,
orchestrates the full pipeline: context → memory → response → save.
"""

import os
import json
import logging
import threading
import requests

from peek_context import build_context
from mesh_memory import recall_memories, process_memory_extraction
from sifra_brain import generate_response, detect_mood
from supabase_client import save_conversation, get_conversations, update_sifra_state

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
USER_TELEGRAM_ID = os.environ.get("USER_TELEGRAM_ID", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_telegram_message(chat_id: int | str, text: str) -> bool:
    """Send a message via Telegram Bot API."""
    try:
        url = f"{TELEGRAM_API}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"send_telegram_message failed: {e}")
        return False


def _run_memory_extraction_async(user_message: str, recent_context: str) -> None:
    """Run memory extraction in a background thread so it doesn't block the response."""
    try:
        count = process_memory_extraction(user_message, recent_context)
        if count > 0:
            logger.info(f"Extracted {count} memories from message")
    except Exception as e:
        logger.error(f"Async memory extraction failed: {e}")


def process_telegram_update(update: dict) -> dict:
    """
    Process an incoming Telegram webhook update.

    Returns a dict with:
      - success: bool
      - reply: str (the response sent, if any)
      - error: str (error message, if any)
    """
    try:
        # Extract message details
        message = update.get("message")
        if not message:
            return {"success": False, "error": "No message in update"}

        text = message.get("text", "").strip()
        if not text:
            return {"success": False, "error": "Empty message text"}

        chat_id = message["chat"]["id"]
        user_id = str(message["from"]["id"])

        # Security: only respond to the configured user
        if USER_TELEGRAM_ID and user_id != USER_TELEGRAM_ID:
            logger.warning(f"Unauthorized user attempted access: {user_id}")
            return {"success": False, "error": "Unauthorized user"}

        # Handle /start command
        if text == "/start":
            welcome = "hey! sifra here. bata, kya chal raha hai? 👋"
            send_telegram_message(chat_id, welcome)
            save_conversation("sifra", welcome, platform="telegram")
            return {"success": True, "reply": welcome}

        # Get last message timestamp for gap detection
        recent = get_conversations(limit=1)
        last_ts = recent[0].get("timestamp") if recent else None

        # Step 1: Build context (Peek system)
        context = build_context(text, last_message_timestamp=last_ts)
        logger.info(f"Context built: mode={context['personality_mode']}, mood={context['mood_signal']}")

        # Step 2: Save user message
        mood = detect_mood(text, _get_recent_context_str())
        save_conversation("user", text, mood_detected=mood, platform="telegram")

        # Step 3: Generate Sifra's response
        reply = generate_response(text, context)

        # Step 4: Save Sifra's response
        save_conversation("sifra", reply, mood_detected=context.get("mood_signal", "neutral"), platform="telegram")

        # Step 5: Send reply via Telegram
        send_telegram_message(chat_id, reply)

        # Step 6: Run memory extraction async (don't block response)
        recent_context_str = _get_recent_context_str()
        thread = threading.Thread(
            target=_run_memory_extraction_async,
            args=(text, recent_context_str),
            daemon=True,
        )
        thread.start()

        # Step 7: Update sifra_state
        update_sifra_state({
            "current_mood": context.get("mood_signal", "neutral"),
            "personality_mode": context.get("personality_mode", "normal"),
        })

        return {"success": True, "reply": reply}

    except Exception as e:
        logger.error(f"process_telegram_update failed: {e}")
        return {"success": False, "error": str(e)}


def _get_recent_context_str() -> str:
    """Get last 5 messages as a formatted context string."""
    try:
        recent = get_conversations(limit=5)
        if not recent:
            return ""
        lines = []
        for msg in recent:
            role = "User" if msg.get("role") == "user" else "Sifra"
            lines.append(f"{role}: {msg.get('content', '')}")
        return "\n".join(lines)
    except Exception:
        return ""


def verify_webhook_secret(secret_token: str) -> bool:
    """Verify the incoming webhook request has the correct secret."""
    if not WEBHOOK_SECRET:
        return True  # No secret configured = skip verification
    return secret_token == WEBHOOK_SECRET
