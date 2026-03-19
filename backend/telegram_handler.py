"""
SIFRA:MIND — Telegram Handler.
Clean orchestration pipeline: message → sentiment → context → brain → quality → send.
No more scattered logic or wrong-mood GIFs.
"""

import os
import re
import logging
import threading

import requests

import sentiment as sentiment_engine
import context_engine
import brain
import memory_engine
import web_search
from supabase_client import (
    save_conversation, get_conversations, get_sifra_state, update_sifra_state,
)
from config import TELEGRAM_BOT_TOKEN, USER_TELEGRAM_ID, WEBHOOK_SECRET

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
CORE_RULES_PATTERN = re.compile(
    r"sifra,?\s*update\s+core\s+rules?:\s*(.+)", re.IGNORECASE | re.DOTALL
)


# ---------------------------------------------------------------------------
# Telegram API Helpers
# ---------------------------------------------------------------------------

def send_message(chat_id: int | str, text: str) -> bool:
    """Send a text message via Telegram."""
    try:
        resp = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"send_message failed: {e}")
        return False


def verify_webhook_secret(secret_token: str) -> bool:
    """Verify the webhook request has the correct secret."""
    if not WEBHOOK_SECRET:
        return True
    return secret_token == WEBHOOK_SECRET


# ---------------------------------------------------------------------------
# Core Rules Update Handler
# ---------------------------------------------------------------------------

def _handle_core_rules(text: str, chat_id: int | str) -> bool:
    """Check if message is a core rules update. Returns True if handled."""
    match = CORE_RULES_PATTERN.match(text)
    if not match:
        return False

    new_rules = match.group(1).strip()
    try:
        update_sifra_state({"core_rules": new_rules})
        confirm = f"✅ Core rules updated:\n\n\"{new_rules}\""
        send_message(chat_id, confirm)
        save_conversation("user", text, platform="telegram")
        save_conversation("sifra", confirm, platform="telegram")
        logger.info(f"Core rules updated: {new_rules[:80]}...")
    except Exception as e:
        logger.error(f"Core rules update failed: {e}")
        send_message(chat_id, "rules update nahi ho payi yr, try again?")
    return True


# ---------------------------------------------------------------------------
# Background Memory Extraction
# ---------------------------------------------------------------------------

def _extract_memories_async(user_message: str, context_str: str) -> None:
    """Run memory extraction in background thread."""
    try:
        count = memory_engine.process_extraction(user_message, context_str)
        if count > 0:
            logger.info(f"Extracted {count} memories")
    except Exception as e:
        logger.error(f"Async memory extraction failed: {e}")


# ---------------------------------------------------------------------------
# The Pipeline — This Is It
# ---------------------------------------------------------------------------

def process_update(update: dict) -> dict:
    """
    Process an incoming Telegram webhook update.

    Pipeline:
    1. Extract + validate message
    2. Analyze sentiment (AI — not keywords)
    3. Build context (time + sentiment + energy → personality mode)
    4. Check for web search need
    5. Generate response (brain → quality gate → retry if needed)
    6. Save everything
    7. Send reply
    8. Extract memories (async background)

    Returns dict with success, reply, error.
    """
    try:
        # --- Validate ---
        message = update.get("message")
        if not message:
            return {"success": False, "error": "No message in update"}

        text = message.get("text", "").strip()
        if not text:
            return {"success": False, "error": "Empty message text"}

        chat_id = message["chat"]["id"]
        user_id = str(message["from"]["id"])

        if USER_TELEGRAM_ID and user_id != USER_TELEGRAM_ID:
            logger.warning(f"Unauthorized user: {user_id}")
            return {"success": False, "error": "Unauthorized"}

        # --- /start ---
        if text == "/start":
            welcome = "hey! sifra here. bata, kya chal raha hai? 👋"
            send_message(chat_id, welcome)
            save_conversation("sifra", welcome, platform="telegram")
            return {"success": True, "reply": welcome}

        # --- Core Rules ---
        if _handle_core_rules(text, chat_id):
            return {"success": True, "reply": "Core rules updated"}

        # --- Step 1: Get conversation history ---
        conversation_history = get_conversations(limit=20)
        last_ts = conversation_history[-1].get("timestamp") if conversation_history else None

        # Build recent context string for sentiment analysis
        recent_str = _format_recent(conversation_history[-5:])

        # --- Step 2: Analyze sentiment (AI-powered) ---
        user_sentiment = sentiment_engine.analyze(text, recent_str)
        logger.info(
            f"Sentiment: {user_sentiment.emotion} "
            f"(intensity={user_sentiment.intensity}, energy={user_sentiment.energy}, "
            f"sarcasm={user_sentiment.sarcasm})"
        )

        # --- Step 3: Build context ---
        context = context_engine.build_context(text, user_sentiment, last_ts)
        logger.info(f"Context: mode={context['personality_mode']}")

        # --- Step 4: Save user message ---
        save_conversation("user", text, mood_detected=user_sentiment.emotion, platform="telegram")

        # --- Step 5: Web search if needed ---
        search_results = None
        if web_search.should_search(text):
            search_results = web_search.search(text)

        # --- Step 6: Generate response ---
        state = get_sifra_state()
        core_rules = state.get("core_rules", "")

        reply = brain.generate_response(
            user_message=text,
            context=context,
            conversation_history=conversation_history,
            core_rules=core_rules,
            web_search_results=search_results,
        )

        # --- Step 7: Save Sifra's response ---
        save_conversation(
            "sifra", reply,
            mood_detected=context["sentiment"].emotion,
            platform="telegram",
        )

        # --- Step 8: Send reply ---
        send_message(chat_id, reply)

        # --- Step 9: Update state ---
        update_sifra_state({
            "current_mood": context["sentiment"].emotion,
            "personality_mode": context["personality_mode"],
            "energy_level": brain._derive_sifra_energy(context["sentiment"], context["time_label"]),
        })

        # --- Step 10: Memory extraction (async) ---
        thread = threading.Thread(
            target=_extract_memories_async,
            args=(text, recent_str),
            daemon=True,
        )
        thread.start()

        return {"success": True, "reply": reply}

    except Exception as e:
        logger.error(f"process_update failed: {e}")
        return {"success": False, "error": str(e)}


def _format_recent(messages: list[dict]) -> str:
    """Format recent messages for context strings."""
    if not messages:
        return ""
    lines = []
    for msg in messages:
        role = "Harkamal" if msg.get("role") == "user" else "Sifra"
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(lines)
