"""
SIFRA:MIND — Supabase Database Client.
All database operations: memories, conversations, state, proactive queue.
Clean, focused, properly error-handled.
"""

import logging
from datetime import datetime, timedelta, timezone

from supabase import create_client, Client

from config import (
    SUPABASE_URL, SUPABASE_KEY,
    MEMORY_SIMILARITY_THRESHOLD, MEMORY_DECAY_DAYS, MEMORY_FORGET_THRESHOLD,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_client: Client | None = None


def get_client() -> Client:
    """Singleton Supabase client."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ===================================================================
# MEMORIES
# ===================================================================

def insert_memory(content: str, category: str, importance: int) -> dict | None:
    """Insert a new memory."""
    try:
        data = {
            "content": content,
            "category": category,
            "importance": max(1, min(10, importance)),
            "decay_score": 1.0,
            "times_referenced": 0,
            "last_referenced": datetime.now(timezone.utc).isoformat(),
        }
        result = get_client().table("memories").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"insert_memory: {e}")
        return None


def find_similar_memory(content: str) -> dict | None:
    """Find a memory with significant word overlap (deduplication)."""
    try:
        result = (
            get_client()
            .table("memories")
            .select("*")
            .neq("category", "forget")
            .execute()
        )
        if not result.data:
            return None

        words_new = set(content.lower().split())
        best_match = None
        best_score = 0.0

        for mem in result.data:
            words_existing = set(mem["content"].lower().split())
            if not words_existing:
                continue
            overlap = len(words_new & words_existing) / max(len(words_new), len(words_existing))
            if overlap > MEMORY_SIMILARITY_THRESHOLD and overlap > best_score:
                best_score = overlap
                best_match = mem

        return best_match
    except Exception as e:
        logger.error(f"find_similar_memory: {e}")
        return None


def update_memory_reference(memory_id: str, new_importance: int | None = None) -> None:
    """Bump reference count and timestamp for a memory."""
    try:
        current = (
            get_client()
            .table("memories")
            .select("times_referenced")
            .eq("id", memory_id)
            .execute()
        )
        if not current.data:
            return

        update_data: dict = {
            "last_referenced": datetime.now(timezone.utc).isoformat(),
            "times_referenced": current.data[0]["times_referenced"] + 1,
        }
        if new_importance is not None:
            update_data["importance"] = max(1, min(10, new_importance))

        get_client().table("memories").update(update_data).eq("id", memory_id).execute()
    except Exception as e:
        logger.error(f"update_memory_reference: {e}")


def get_top_memories(limit: int = 8) -> list[dict]:
    """
    Fetch top memories by composite score.
    Used for proactive messages and spontaneous recall.
    """
    try:
        result = (
            get_client()
            .table("memories")
            .select("*")
            .neq("category", "forget")
            .execute()
        )
        if not result.data:
            return []

        now = datetime.now(timezone.utc)

        def score(mem: dict) -> float:
            imp = (mem.get("importance", 5) / 10.0) * 0.5
            decay = mem.get("decay_score", 1.0) * 0.3
            last_ref_str = mem.get("last_referenced")
            recency = 0.5
            if last_ref_str:
                try:
                    last_ref = datetime.fromisoformat(last_ref_str.replace("Z", "+00:00"))
                    days_ago = (now - last_ref).total_seconds() / 86400
                    recency = max(0.0, 1.0 - days_ago / 30.0)
                except Exception:
                    pass
            return imp + decay + recency * 0.2

        ranked = sorted(result.data, key=score, reverse=True)
        return ranked[:limit]
    except Exception as e:
        logger.error(f"get_top_memories: {e}")
        return []


def get_all_active_memories() -> list[dict]:
    """Return all non-forgotten memories (for context-aware retrieval)."""
    try:
        result = (
            get_client()
            .table("memories")
            .select("*")
            .neq("category", "forget")
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"get_all_active_memories: {e}")
        return []


def get_all_memories(category: str | None = None) -> list[dict]:
    """Return all non-forgotten memories, optionally filtered. For dashboard."""
    try:
        query = get_client().table("memories").select("*").neq("category", "forget")
        if category:
            query = query.eq("category", category)
        result = query.order("importance", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"get_all_memories: {e}")
        return []


def delete_memory(memory_id: str) -> bool:
    """Delete a memory by ID."""
    try:
        get_client().table("memories").delete().eq("id", memory_id).execute()
        return True
    except Exception as e:
        logger.error(f"delete_memory: {e}")
        return False


def decay_memories() -> int:
    """
    Daily decay pass.
    - Decrease decay_score by 0.05 for memories not referenced in 7+ days
    - Archive (category='forget') if decay < threshold AND not core
    """
    try:
        result = (
            get_client()
            .table("memories")
            .select("*")
            .neq("category", "forget")
            .execute()
        )
        if not result.data:
            return 0

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=MEMORY_DECAY_DAYS)
        affected = 0

        for mem in result.data:
            last_ref_str = mem.get("last_referenced")
            if not last_ref_str:
                continue

            try:
                last_ref = datetime.fromisoformat(last_ref_str.replace("Z", "+00:00"))
            except Exception:
                continue

            if last_ref < cutoff:
                new_decay = max(0.0, mem.get("decay_score", 1.0) - 0.05)
                update_data: dict = {"decay_score": new_decay}

                if new_decay < MEMORY_FORGET_THRESHOLD and mem.get("category") != "core":
                    update_data["category"] = "forget"

                get_client().table("memories").update(update_data).eq("id", mem["id"]).execute()
                affected += 1

        return affected
    except Exception as e:
        logger.error(f"decay_memories: {e}")
        return 0


# ===================================================================
# CONVERSATIONS
# ===================================================================

def save_conversation(
    role: str,
    content: str,
    mood_detected: str = "",
    platform: str = "telegram",
) -> dict | None:
    """Save a message to conversation history."""
    try:
        data = {
            "role": role,
            "content": content,
            "mood_detected": mood_detected,
            "platform": platform,
        }
        result = get_client().table("conversations").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"save_conversation: {e}")
        return None


def get_conversations(limit: int = 50) -> list[dict]:
    """Fetch recent conversations in chronological order."""
    try:
        result = (
            get_client()
            .table("conversations")
            .select("*")
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        rows = result.data or []
        rows.reverse()  # chronological
        return rows
    except Exception as e:
        logger.error(f"get_conversations: {e}")
        return []


def get_mood_history(days: int = 7) -> list[dict]:
    """Return mood counts grouped by day."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = (
            get_client()
            .table("conversations")
            .select("timestamp, mood_detected")
            .gte("timestamp", cutoff)
            .neq("mood_detected", "")
            .order("timestamp")
            .execute()
        )
        if not result.data:
            return []

        day_moods: dict[str, dict[str, int]] = {}
        for row in result.data:
            try:
                day = row["timestamp"][:10]
            except Exception:
                continue
            mood = row.get("mood_detected", "neutral")
            if day not in day_moods:
                day_moods[day] = {}
            day_moods[day][mood] = day_moods[day].get(mood, 0) + 1

        return [{"date": d, "moods": m} for d, m in sorted(day_moods.items())]
    except Exception as e:
        logger.error(f"get_mood_history: {e}")
        return []


# ===================================================================
# SIFRA STATE
# ===================================================================

def get_sifra_state() -> dict:
    """Return Sifra's current state or sensible defaults."""
    try:
        result = get_client().table("sifra_state").select("*").limit(1).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"get_sifra_state: {e}")

    return {
        "current_mood": "neutral",
        "energy_level": 7,
        "last_active": datetime.now(timezone.utc).isoformat(),
        "active_memories": [],
        "today_summary": "",
        "personality_mode": "normal",
        "core_rules": "",
    }


def update_sifra_state(updates: dict) -> None:
    """Upsert Sifra's state."""
    try:
        updates["last_active"] = datetime.now(timezone.utc).isoformat()
        existing = get_client().table("sifra_state").select("id").limit(1).execute()
        if existing.data:
            get_client().table("sifra_state").update(updates).eq("id", existing.data[0]["id"]).execute()
        else:
            get_client().table("sifra_state").insert(updates).execute()
    except Exception as e:
        logger.error(f"update_sifra_state: {e}")


# ===================================================================
# PROACTIVE QUEUE
# ===================================================================

def get_pending_proactive_messages() -> list[dict]:
    """Get unsent proactive messages that are due."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        result = (
            get_client()
            .table("proactive_queue")
            .select("*")
            .eq("sent", False)
            .lte("scheduled_for", now)
            .order("scheduled_for")
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"get_pending_proactive_messages: {e}")
        return []


def mark_proactive_sent(message_id: str) -> None:
    """Mark a proactive message as sent."""
    try:
        get_client().table("proactive_queue").update({"sent": True}).eq("id", message_id).execute()
    except Exception as e:
        logger.error(f"mark_proactive_sent: {e}")
