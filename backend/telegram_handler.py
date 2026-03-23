"""
SIFRA:MIND — Telegram Handler.
Clean orchestration pipeline: message → sentiment → context → brain → quality → send.
Also handles group observation for learning from other bots.
"""

import os
import re
import random
import logging
import threading

import requests

import sentiment as sentiment_engine
import context_engine
import brain
import memory_engine
import web_search
import observation_engine
from supabase_client import (
    save_conversation, get_conversations, get_sifra_state, update_sifra_state,
    get_observation_stats,
)
from config import TELEGRAM_BOT_TOKEN, USER_TELEGRAM_ID, WEBHOOK_SECRET, RUMIK_BOT_USERNAME

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
CORE_RULES_PATTERN = re.compile(
    r"sifra,?\s*update\s+core\s+rules?:\s*(.+)", re.IGNORECASE | re.DOTALL
)

# Regex to catch AI-controlled actions
ACTION_REACT_PATTERN = re.compile(r"\[REACT:\s*(.+?)\]", re.IGNORECASE)
ACTION_STICKER_PATTERN = re.compile(r"\[STICKER:\s*(.+?)\]", re.IGNORECASE)

# Track recent user messages in groups for pairing with bot responses
_recent_group_user_messages: dict[int, str] = {}  # chat_id → last user message


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


# ---------------------------------------------------------------------------
# Emoji Reactions — react to user messages with relevant emoji
# ---------------------------------------------------------------------------

# Mood → possible reaction emojis (Telegram-supported)
MOOD_REACTIONS = {
    "happy":      ["😊", "❤️", "🔥", "👍"],
    "excited":    ["🔥", "🎉", "❤️", "👏"],
    "sad":        ["❤️", "😢", "🥺"],
    "stressed":   ["❤️", "😢", "👀"],
    "anxious":    ["❤️", "🥺"],
    "bored":      ["😐", "👀", "💤"],
    "angry":      ["👀", "😐"],
    "neutral":    ["👍", "👀"],
    "tired":      ["😢", "❤️", "💤"],
    "curious":    ["👀", "🤔", "👍"],
    "playful":    ["😂", "🔥", "👏", "💀"],
    "frustrated": ["😢", "❤️", "👀"],
    "nostalgic":  ["❤️", "🥺", "😢"],
    "lonely":     ["❤️", "🥺"],
    "grateful":   ["❤️", "🔥", "👍"],
    "confused":   ["🤔", "👀"],
    "romantic":   ["❤️", "🔥", "😊"],
}

# Generic reactions for any mood
GENERIC_REACTIONS = ["👍", "👀", "😂", "🔥", "❤️", "💀"]


def react_to_message_explicit(chat_id: int | str, message_id: int, emoji: str) -> bool:
    """Set a specific emoji reaction on a user's message."""
    try:
        resp = requests.post(
            f"{TELEGRAM_API}/setMessageReaction",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": [{"type": "emoji", "emoji": emoji}],
                "is_big": random.random() < 0.2,  # 20% chance of big reaction if AI chooses it
            },
            timeout=5,
        )
        if resp.status_code == 200:
            logger.info(f"Explicitly reacted with {emoji} to message {message_id}")
            return True
        else:
            logger.warning(f"Reaction failed: {resp.status_code} - {resp.text[:100]}")
            return False
    except Exception as e:
        logger.error(f"react_to_message_explicit failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Stickers — send relevant stickers from popular packs
# ---------------------------------------------------------------------------

# Sticker set names → mapped by emotion category
# These are popular public sticker sets on Telegram
STICKER_SETS = {
    "funny": ["HotCherry", "MrCat", "RaccoonPack", "PepeTheFrog"],
    "cute": ["AnimatedStickerPack", "LoveDoves", "CatMemes"],
    "sad": ["SadCat", "CatMemes"],
    "cool": ["HotCherry", "PepeTheFrog"],
}

# Emotion → sticker mood category
EMOTION_TO_STICKER_MOOD = {
    "happy": "cute", "excited": "funny", "sad": "sad", "stressed": "sad",
    "anxious": "cute", "bored": "funny", "angry": "funny",
    "neutral": "funny", "tired": "sad", "curious": "cool",
    "playful": "funny", "frustrated": "sad", "nostalgic": "cute",
    "lonely": "sad", "grateful": "cute", "confused": "funny",
    "romantic": "cute",
}

# Cache for fetched sticker file_ids
_sticker_cache: dict[str, list[str]] = {}


def _fetch_sticker_set(set_name: str) -> list[str]:
    """Fetch sticker file_ids from a Telegram sticker set."""
    if set_name in _sticker_cache:
        return _sticker_cache[set_name]

    try:
        resp = requests.get(
            f"{TELEGRAM_API}/getStickerSet",
            params={"name": set_name},
            timeout=8,
        )
        if resp.status_code != 200:
            return []

        stickers = resp.json().get("result", {}).get("stickers", [])
        file_ids = [s["file_id"] for s in stickers if "file_id" in s]
        if file_ids:
            _sticker_cache[set_name] = file_ids
        return file_ids
    except Exception as e:
        logger.error(f"Failed to fetch sticker set {set_name}: {e}")
        return []


def send_sticker_explicit(chat_id: int | str, emotion_label: str) -> bool:
    """Send a sticker explicitly requested by the AI based on a mood/emotion label."""
    try:
        mood_category = EMOTION_TO_STICKER_MOOD.get(emotion_label.lower(), "funny")
        set_names = STICKER_SETS.get(mood_category, STICKER_SETS["funny"])

        # Try sticker sets until we find one that works
        random.shuffle(set_names)
        for set_name in set_names:
            file_ids = _fetch_sticker_set(set_name)
            if file_ids:
                chosen = random.choice(file_ids)
                resp = requests.post(
                    f"{TELEGRAM_API}/sendSticker",
                    json={"chat_id": chat_id, "sticker": chosen},
                    timeout=10,
                )
                if resp.status_code == 200:
                    logger.info(f"Sent sticker from {set_name} for requested emotion: {emotion_label}")
                    return True

        logger.warning(f"No sticker sets available for requested emotion: {emotion_label}")
        return False
    except Exception as e:
        logger.error(f"send_sticker_explicit failed: {e}")
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

    new_rules = str(match.group(1)).strip()
    try:
        update_sifra_state({"core_rules": new_rules})
        confirm = f"✅ Core rules updated:\n\n\"{str(new_rules)[:80]}\""
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
    "/sifra_learn_status": "Show observation learning stats",
    "/sifra_train": "Start auto-training with Rumik",
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
        return {"success": True}

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
        return {"success": True}

    if cmd == "/sifra_clear_mem":
        from supabase_client import clear_all_memories
        count = clear_all_memories()
        send_message(chat_id, f"🧹 Cleared <b>{count}</b> memories.")
        return {"success": True}

    if cmd == "/sifra_clear_conv":
        from supabase_client import clear_all_conversations
        count = clear_all_conversations()
        send_message(chat_id, f"🧹 Cleared <b>{count}</b> conversations.")
        return {"success": True}

    if cmd == "/sifra_learn_status":
        return _send_learn_status(chat_id)

    if cmd == "/sifra_train":
        return _start_training(chat_id)

    return None


def _start_training(chat_id: int | str) -> dict:
    """Trigger an auto-training session seamlessly on GitHub Actions or local laptop."""
    import config
    import requests
    
    # 1. Check if GitHub Token is available to trigger Cloud Actions
    github_token = getattr(config, "GITHUB_TOKEN", None)
    if github_token:
        url = "https://api.github.com/repos/Mr-Hkds/sifra.ai/actions/workflows/auto_train.yml/dispatches"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        res = requests.post(url, headers=headers, json={"ref": "main"})
        
        if res.status_code == 204:
            send_message(
                chat_id,
                f"🚀 <b>Cloud Training Triggered!</b>\n\n"
                f"GitHub Actions has received the command and is spinning up a heavy compute server.\n"
                f"The exact process is entirely automated. I will send you a full summary report the exact moment it completes in ~8-12 mins!"
            )
        else:
            send_message(chat_id, f"❌ <b>GitHub Trigger Failed:</b>\n{res.text}")
            
        return {"success": True}

    # 2. Fallback to Local Sync Listener if no Cloud Token is configured
    from supabase_client import insert_memory
    
    # Drop a system core memory that acts as a signal for the local listener
    insert_memory(content="SYSTEM_FLAG_TRIGGER_AUTO_TRAIN", category="system", importance=10)
    
    send_message(
        chat_id,
        f"📡 <b>Signal Sent to Laptop</b>\n\n"
        f"I just dropped a trigger flag in the database. If your laptop is turned on and running the listener, the multi-phase training protocol will auto-engage in ~5 seconds.\n\n"
        f"You will get a confirmation message as soon as it begins!"
    )
    return {"success": True, "reply": "remote trigger inserted"}

def _send_learn_status(chat_id: int | str) -> dict:
    """Send observation learning stats via Telegram. Enhanced v2."""
    stats = get_observation_stats()
    from supabase_client import get_all_learnings

    learnings = get_all_learnings()

    msg = (
        f"🧠 <b>Observation Learning Status</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Source:</b> @{RUMIK_BOT_USERNAME}\n"
        f"<b>Total Observations:</b> {stats['total_observations']}\n"
        f"<b>Analyzed:</b> {stats['analyzed']}\n"
        f"<b>Pending Analysis:</b> {stats['pending']}\n"
        f"<b>Patterns Learned:</b> {stats['learnings_count']}\n"
    )

    if learnings:
        # Separate meta-directives from regular patterns
        meta_directives = [l for l in learnings if l.get('category') == 'meta_directive']
        regular = [l for l in learnings if l.get('category') != 'meta_directive']

        # Count by category
        cat_counts: dict[str, int] = {}
        for l in regular:
            cat = str(l.get('category', '?'))
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        if cat_counts:
            msg += "\n<b>Patterns by Category:</b>\n"
            for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
                msg += f"  • {cat}: {count}\n"

        if meta_directives:
            msg += f"\n🎯 <b>Active Behavioral Directives ({len(meta_directives)}):</b>\n"
            for m in meta_directives[:5]:
                pattern = str(m.get('pattern', ''))[:100]
                conf = float(m.get('confidence', 0))
                msg += f"  → {pattern} <i>({conf:.0%})</i>\n"

        if regular:
            msg += f"\n<b>Top Patterns ({len(regular)} total):</b>\n"
            for l in regular[:6]:
                cat = str(l.get('category', '?'))
                pattern = str(l.get('pattern', ''))[:70]
                conf = float(l.get('confidence', 0))
                msg += f"  • [{cat}] {pattern} <i>({conf:.0%})</i>\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
    send_message(chat_id, msg)
    return {"success": True}


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
        mood = str(state.get("current_mood", "unknown"))
        energy = str(state.get("energy_level", "?"))
        mode = str(state.get("personality_mode", "unknown"))
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

    Handles two modes:
    A) GROUP MODE — If message is from a group and from Rumik's bot, observe silently.
    B) PRIVATE MODE — Normal Sifra conversation pipeline.

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
        chat_type = message["chat"].get("type", "private")
        from_user = message.get("from", {})
        username = from_user.get("username", "").lower()
        user_id = str(from_user.get("id", ""))
        is_bot = from_user.get("is_bot", False)

        # =================================================================
        # GROUP MODE — Observation Learning
        # =================================================================
        if chat_type in ("group", "supergroup"):
            return _handle_group_message(
                text=text,
                chat_id=chat_id,
                username=username,
                is_bot=is_bot,
                user_id=user_id,
            )

        # =================================================================
        # PRIVATE MODE — Normal Sifra Pipeline
        # =================================================================

        # --- Auto-detect forwarded messages from Rumik ---
        if _is_forwarded_from_rumik(message):
            return _handle_forwarded_rumik(text, chat_id)

        if USER_TELEGRAM_ID and user_id != USER_TELEGRAM_ID:
            logger.warning(f"Unauthorized user: {user_id}")
            return {"success": False, "error": "Unauthorized"}

        # --- /start ---
        if text == "/start":
            welcome = "hey! sifra here. bata, kya chal raha hai? 👋"
            send_message(chat_id, welcome)
            save_conversation("sifra", welcome, platform="telegram")
            return {"success": True, "reply": welcome}

        # --- /learn command — learn from a forwarded message ---
        if text.lower().startswith("/learn"):
            return _handle_learn_command(text, chat_id)

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

        # --- Step 3: Build context (now with conversation dynamics) ---
        recent_user_count = sum(1 for m in conversation_history[-10:] if m.get("role") == "user")
        context = context_engine.build_context(
            text, user_sentiment, last_ts,
            recent_message_count=recent_user_count,
        )
        logger.info(f"Context: mode={context['personality_mode']}, pace={context.get('conversation_pace')}, length_hint={context.get('response_length_hint')}")

        # --- Step 4: Save user message ---
        save_conversation("user", text, mood_detected=user_sentiment.emotion, platform="telegram")

        # --- Step 5: Web search if needed (AI-powered intent detection) ---
        search_results = None
        if web_search.should_search(text, recent_str):
            search_results = web_search.search(text)
            if search_results:
                logger.info(f"Web search returned results for: {text[:50]}")

        # --- Step 6: Generate response ---
        state = get_sifra_state()
        core_rules = str(state.get("core_rules", ""))

        reply = brain.generate_response(
            user_message=text,
            context=context,
            conversation_history=conversation_history,
            core_rules=core_rules,
            web_search_results=search_results,
        )

        # --- Step 7: Parse internal AI actions ---
        # Parse reactions
        react_match = ACTION_REACT_PATTERN.search(reply)
        react_emoji = react_match.group(1).strip() if react_match else None
        if react_match:
            reply = ACTION_REACT_PATTERN.sub("", reply).strip()

        # Parse stickers
        sticker_match = ACTION_STICKER_PATTERN.search(reply)
        sticker_mood = sticker_match.group(1).strip() if sticker_match else None
        if sticker_match:
            reply = ACTION_STICKER_PATTERN.sub("", reply).strip()

        # --- Step 8: Save Sifra's response ---
        save_conversation(
            "sifra", reply,
            mood_detected=context["sentiment"].emotion,
            platform="telegram",
        )

        # --- Step 9: React to user's message if AI asked to ---
        if react_emoji:
            message_id = message.get("message_id")
            if message_id:
                threading.Thread(
                    target=react_to_message_explicit,
                    args=(chat_id, message_id, react_emoji),
                    daemon=True,
                ).start()

        # --- Step 10: Send actual reply text ---
        if reply:
            send_message(chat_id, reply)

        # --- Step 11: Send sticker if AI asked to ---
        if sticker_mood:
            threading.Thread(
                target=send_sticker_explicit,
                args=(chat_id, sticker_mood),
                daemon=True,
            ).start()

        # --- Step 12: Update state ---
        sifra_state_update = {
            "current_mood": context["sentiment"].emotion,
            "personality_mode": context["personality_mode"],
            "energy_level": brain._derive_sifra_energy(context["sentiment"], context["time_label"]),
        }
        update_sifra_state(sifra_state_update)

        # --- Step 13: Memory extraction (async) ---
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


# ---------------------------------------------------------------------------
# Forwarded Message Detection — Auto-learn from Rumik
# ---------------------------------------------------------------------------

def _is_forwarded_from_rumik(message: dict) -> bool:
    """
    Detect if a message was forwarded from Rumik's bot.
    Supports both Bot API 7.0+ (forward_origin) and legacy (forward_from).
    """
    # Bot API 7.0+ format
    forward_origin = message.get("forward_origin", {})
    if forward_origin:
        origin_type = forward_origin.get("type", "")
        if origin_type == "user":
            sender = forward_origin.get("sender_user", {})
            if sender.get("is_bot") and sender.get("username", "").lower() == RUMIK_BOT_USERNAME:
                return True

    # Legacy format (older Bot API)
    forward_from = message.get("forward_from", {})
    if forward_from:
        if forward_from.get("is_bot") and forward_from.get("username", "").lower() == RUMIK_BOT_USERNAME:
            return True

    return False


def _handle_forwarded_rumik(text: str, chat_id: int | str) -> dict:
    """
    Auto-learn from a forwarded Rumik message.
    No /learn prefix needed — just forward and Sifra picks it up.
    """
    logger.info(f"Auto-detected forwarded Rumik message: {text[:80]}...")

    def _learn_async():
        result = observation_engine.learn_from_single(text)
        send_message(chat_id, f"📝 {result}")

    threading.Thread(target=_learn_async, daemon=True).start()
    return {"success": True, "reply": "auto-learning from forwarded rumik message"}


# ---------------------------------------------------------------------------
# Group Observation — Silent Learning Mode
# ---------------------------------------------------------------------------

def _handle_group_message(
    text: str, chat_id: int, username: str, is_bot: bool, user_id: str,
) -> dict:
    """
    Handle a message from a group chat.
    If it's from Rumik's bot → observe and learn.
    If it's from a human user → track as context for pairing.
    Sifra NEVER responds in groups — she only observes.
    """
    if is_bot and username == RUMIK_BOT_USERNAME:
        # This is a Rumik response! Capture it.
        user_context = _recent_group_user_messages.get(chat_id, "(unknown)")
        logger.info(f"🔍 Observed Rumik response: {text[:80]}...")

        # Capture in background to not block the webhook
        threading.Thread(
            target=observation_engine.capture_exchange,
            args=(user_context, text, "rumik"),
            daemon=True,
        ).start()

        return {"success": True, "reply": "(observed rumik)"}

    elif not is_bot:
        # Human message — track as context for next bot response
        _recent_group_user_messages[chat_id] = text
        logger.debug(f"Tracked group user message for context: {text[:60]}")
        return {"success": True, "reply": "(tracked context)"}

    return {"success": True, "reply": "(ignored group message)"}


# ---------------------------------------------------------------------------
# /learn Command — Manual Forwarded Message Learning
# ---------------------------------------------------------------------------

def _handle_learn_command(text: str, chat_id: int | str) -> dict:
    """
    Handle /learn command — user forwards a message from another bot.
    Format: /learn <message text>
    """
    content = text[len("/learn"):].strip()
    if not content:
        send_message(chat_id, "forward a message and add /learn before it. example:\n/learn arre yr kya scene hai")
        return {"success": True, "reply": "learn usage"}

    # Analyze in background
    def _learn_async():
        result = observation_engine.learn_from_single(content)
        send_message(chat_id, result)

    threading.Thread(target=_learn_async, daemon=True).start()
    return {"success": True, "reply": "learning..."}


def _format_recent(messages: list[dict]) -> str:
    """Format recent messages for context strings."""
    if not messages:
        return ""
    lines = []
    for msg in messages:
        role = "Harkamal" if msg.get("role") == "user" else "Sifra"
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(lines)
