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
# Secret Admin Commands — diagnostic & control via Telegram
# ---------------------------------------------------------------------------

ADMIN_COMMANDS = {
    "/sifra_diag": "System diagnostics",
    "/sifra_reset": "Full factory reset",
    "/sifra_clear_mem": "Clear all memories",
    "/sifra_clear_conv": "Clear all conversations",
    "/sifra_help": "Show admin commands",
}


def _handle_admin_command(text: str, chat_id: int | str) -> dict | None:
    """
    Handle secret admin commands. Returns a result dict if handled, None otherwise.
    These commands are invisible to Sifra — they don't go through the AI pipeline.
    """
    cmd = text.strip().lower().split()[0]

    if cmd == "/sifra_help":
        lines = ["🔧 <b>SIFRA:MIND Admin Commands</b>\n"]
        for c, desc in ADMIN_COMMANDS.items():
            lines.append(f"<code>{c}</code> — {desc}")
        send_message(chat_id, "\n".join(lines))
        return {"success": True, "reply": "admin help"}

    if cmd == "/sifra_diag":
        return _send_diagnostics(chat_id)

    if cmd == "/sifra_reset":
        from supabase_client import full_reset
        result = full_reset()
        msg = (
            f"♻️ <b>Factory Reset Complete</b>\n\n"
            f"• Memories cleared: <b>{result['memories_cleared']}</b>\n"
            f"• Conversations cleared: <b>{result['conversations_cleared']}</b>\n"
            f"• State: reset to defaults\n\n"
            f"<i>Sifra is now a blank slate.</i>"
        )
        send_message(chat_id, msg)
        return {"success": True, "reply": "factory reset done"}

    if cmd == "/sifra_clear_mem":
        from supabase_client import clear_all_memories
        count = clear_all_memories()
        send_message(chat_id, f"🧹 Cleared <b>{count}</b> memories.")
        return {"success": True, "reply": f"cleared {count} memories"}

    if cmd == "/sifra_clear_conv":
        from supabase_client import clear_all_conversations
        count = clear_all_conversations()
        send_message(chat_id, f"🧹 Cleared <b>{count}</b> conversations.")
        return {"success": True, "reply": f"cleared {count} conversations"}

    return None


def _send_diagnostics(chat_id: int | str) -> dict:
    """Send a full system diagnostics report via Telegram."""
    import importlib
    import os
    from config import (
        VERSION, BUILD_DATE, GEMINI_API_KEY,
        GEMINI_CHAT_MODEL, GROQ_CHAT_MODEL, GROQ_FAST_MODEL,
        CONVERSATION_CONTEXT_LIMIT, MEMORY_RECALL_LIMIT,
        CHAT_TEMPERATURE,
    )

    # Module check
    modules = [
        "brain", "ai_client", "sentiment", "context_engine",
        "personality", "memory_engine", "quality_gate",
        "telegram_handler", "proactive", "web_search", "supabase_client",
    ]
    loaded = 0
    failed = []
    for mod in modules:
        try:
            importlib.import_module(mod)
            loaded += 1
        except Exception as e:
            failed.append(f"{mod}: {str(e)[:40]}")

    # DB check
    db_status = "❌ error"
    try:
        from supabase_client import get_client
        get_client().table("sifra_state").select("id").limit(1).execute()
        db_status = "✅ connected"
    except Exception:
        pass

    # Memory & conversation counts
    mem_count = 0
    conv_count = 0
    try:
        from supabase_client import get_all_memories, get_conversations
        mem_count = len(get_all_memories())
        conv_count = len(get_conversations(limit=9999))
    except Exception:
        pass

    # State
    try:
        state = get_sifra_state()
        mood = state.get("current_mood", "unknown")
        energy = state.get("energy_level", "?")
        mode = state.get("personality_mode", "unknown")
    except Exception:
        mood = energy = mode = "error"

    # AI provider
    ai_provider = "Gemini + Groq" if GEMINI_API_KEY else "Groq only"
    chat_model = GEMINI_CHAT_MODEL if GEMINI_API_KEY else GROQ_CHAT_MODEL

    msg = (
        f"🔍 <b>SIFRA:MIND Diagnostics</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Version:</b> v{VERSION} ({BUILD_DATE})\n"
        f"<b>Architecture:</b> v3 rewrite\n\n"
        f"<b>AI Provider:</b> {ai_provider}\n"
        f"<b>Chat Model:</b> {chat_model}\n"
        f"<b>Fast Model:</b> {GROQ_FAST_MODEL}\n"
        f"<b>Temperature:</b> {CHAT_TEMPERATURE}\n"
        f"<b>Context Window:</b> {CONVERSATION_CONTEXT_LIMIT} messages\n"
        f"<b>Memory Limit:</b> {MEMORY_RECALL_LIMIT} per prompt\n\n"
        f"<b>Database:</b> {db_status}\n"
        f"<b>Modules:</b> {loaded}/{len(modules)} loaded\n"
    )

    if failed:
        msg += f"<b>Failed:</b> {', '.join(failed)}\n"

    msg += (
        f"\n<b>Memories:</b> {mem_count} stored\n"
        f"<b>Conversations:</b> {conv_count} messages\n\n"
        f"<b>Current Mood:</b> {mood}\n"
        f"<b>Energy:</b> {energy}/10\n"
        f"<b>Mode:</b> {mode}\n\n"
        f"<b>Gemini Key:</b> {'✅ set' if GEMINI_API_KEY else '⚠️ not set'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    send_message(chat_id, msg)
    return {"success": True, "reply": "diagnostics sent"}


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

        # --- Secret Admin Commands ---
        if text.startswith("/sifra_"):
            result = _handle_admin_command(text, chat_id)
            if result:
                return result

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
