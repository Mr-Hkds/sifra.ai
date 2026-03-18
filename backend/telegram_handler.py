"""
Telegram webhook handler — processes incoming messages,
orchestrates the full pipeline: context → memory → response → save.
Includes sticker/GIF support for more human-like interactions.
"""

import os
import json
import re
import random
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

# Core Rules trigger pattern (case-insensitive)
CORE_RULES_PATTERN = re.compile(r"sifra,?\s*update\s+core\s+rules?:\s*(.+)", re.IGNORECASE | re.DOTALL)

# GIPHY free API key (public beta key — rate limited but works)
GIPHY_API_KEY = os.environ.get("GIPHY_API_KEY", "GlVGYHkr3WSBnllca54iNt0yFbjz7L65")

# GIF search keywords based on mood/context
MOOD_GIF_KEYWORDS = {
    "happy": ["happy dance", "celebration", "excited", "yaay", "party"],
    "excited": ["omg excited", "celebration dance", "cant wait", "woohoo"],
    "sad": ["sad hug", "comfort hug", "there there", "sad rain"],
    "stressed": ["stressed out", "deep breath", "calm down", "its okay"],
    "bored": ["bored af", "so bored", "yawn", "nothing to do"],
    "playful": ["lol funny", "haha", "rofl", "cheeky", "teasing"],
    "neutral": ["hi wave", "thinking", "hmm", "curious"],
    "angry": ["angry", "frustrated", "ugh", "annoyed"],
    "tired": ["sleepy", "yawn tired", "exhausted", "need sleep"],
    "venting": ["hug comfort", "listening", "im here", "support"],
    "hyped": ["lets go", "hyped", "fire", "excited dance", "wooo"],
}


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


def send_telegram_gif(chat_id: int | str, gif_url: str) -> bool:
    """Send a GIF via Telegram Bot API."""
    try:
        url = f"{TELEGRAM_API}/sendAnimation"
        payload = {"chat_id": chat_id, "animation": gif_url}
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"send_telegram_gif failed: {e}")
        return False


def send_telegram_sticker(chat_id: int | str, sticker_id: str) -> bool:
    """Send a sticker via Telegram Bot API."""
    try:
        url = f"{TELEGRAM_API}/sendSticker"
        payload = {"chat_id": chat_id, "sticker": sticker_id}
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"send_telegram_sticker failed: {e}")
        return False


def _search_giphy(query: str) -> str | None:
    """Search GIPHY for a relevant GIF. Returns GIF URL or None."""
    try:
        resp = requests.get(
            "https://api.giphy.com/v1/gifs/search",
            params={
                "api_key": GIPHY_API_KEY,
                "q": query,
                "limit": 10,
                "rating": "pg-13",
                "lang": "en",
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        gifs = resp.json().get("data", [])
        if not gifs:
            return None
        gif = random.choice(gifs)
        return gif.get("images", {}).get("fixed_height", {}).get("url")
    except Exception as e:
        logger.error(f"GIPHY search failed: {e}")
        return None


def _maybe_send_gif(chat_id: int | str, mood: str, personality_mode: str) -> None:
    """
    Randomly send a relevant GIF/sticker after Sifra's text reply.
    30% chance on playful/hyped moods, 15% on others.
    Never sends during vent/quiet modes (respect the vibe).
    """
    # Don't send GIFs during serious moments
    if personality_mode in ("vent", "quiet", "late_night"):
        return

    # Higher chance for fun moods
    chance = 0.30 if personality_mode in ("playful", "hyped") else 0.15
    if random.random() > chance:
        return

    # Pick a search keyword based on mood
    keywords = MOOD_GIF_KEYWORDS.get(mood, MOOD_GIF_KEYWORDS["neutral"])
    query = random.choice(keywords)

    gif_url = _search_giphy(query)
    if gif_url:
        send_telegram_gif(chat_id, gif_url)
        logger.info(f"Sent GIF for mood={mood}, query={query}")


def _run_memory_extraction_async(user_message: str, sifra_context: str) -> None:
    """
    Run memory extraction in a background thread.
    IMPORTANT: Only extracts from user_message. sifra_context is read-only
    reference so the extractor understands the conversation flow.
    """
    try:
        count = process_memory_extraction(user_message, sifra_context)
        if count > 0:
            logger.info(f"Extracted {count} memories from user message")
    except Exception as e:
        logger.error(f"Async memory extraction failed: {e}")


def _handle_core_rules_update(text: str, chat_id: int | str) -> bool:
    """
    Check if the message is a Core Rules update command.
    If yes, save the rules and confirm. Returns True if handled.
    """
    match = CORE_RULES_PATTERN.match(text)
    if not match:
        return False

    new_rules = match.group(1).strip()
    try:
        update_sifra_state({"core_rules": new_rules})
        confirm = f"✅ Core rules updated. I'll follow these from now on:\n\n\"{new_rules}\""
        send_telegram_message(chat_id, confirm)
        save_conversation("user", text, platform="telegram")
        save_conversation("sifra", confirm, platform="telegram")
        logger.info(f"Core rules updated: {new_rules[:80]}...")
    except Exception as e:
        logger.error(f"Core rules update failed: {e}")
        send_telegram_message(chat_id, "rules update nahi ho payi yr, try again?")
    return True


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

        # Handle Core Rules update (secret element)
        if _handle_core_rules_update(text, chat_id):
            return {"success": True, "reply": "Core rules updated"}

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

        # Step 6: Maybe send a fun GIF/sticker (contextual, random chance)
        _maybe_send_gif(chat_id, mood, context.get("personality_mode", "normal"))

        # Step 7: Run memory extraction async — ONLY from user message
        sifra_context = _get_recent_context_str()
        thread = threading.Thread(
            target=_run_memory_extraction_async,
            args=(text, sifra_context),
            daemon=True,
        )
        thread.start()

        # Step 8: Update sifra_state
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
