"""
Supabase client and all database query helpers for SIFRA:MIND.
Handles memories, conversations, sifra_state, and proactive_queue tables.
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

_client: Client | None = None


def get_client() -> Client:
    """Return a singleton Supabase client."""
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
    """Insert a new memory. Returns the created row or None on error."""
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
        logger.error(f"insert_memory failed: {e}")
        return None


def find_similar_memory(content: str) -> dict | None:
    """Fuzzy-match: look for a memory whose content overlaps significantly."""
    try:
        # Pull all non-forgotten memories and do a simple keyword overlap check
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
            if overlap > 0.6 and overlap > best_score:
                best_score = overlap
                best_match = mem

        return best_match
    except Exception as e:
        logger.error(f"find_similar_memory failed: {e}")
        return None


def update_memory_reference(memory_id: str, new_importance: int | None = None) -> None:
    """Bump reference count and timestamp for an existing memory."""
    try:
        update_data: dict = {
            "last_referenced": datetime.now(timezone.utc).isoformat(),
            "times_referenced": get_client()
            .table("memories")
            .select("times_referenced")
            .eq("id", memory_id)
            .execute()
            .data[0]["times_referenced"]
            + 1,
        }
        if new_importance is not None:
            update_data["importance"] = max(1, min(10, new_importance))
        get_client().table("memories").update(update_data).eq("id", memory_id).execute()
    except Exception as e:
        logger.error(f"update_memory_reference failed: {e}")


def get_top_memories(limit: int = 8) -> list[dict]:
    """
    Fetch top memories ranked by:
      (importance * 0.5) + (decay_score * 0.3) + (recency * 0.2)
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
            # Recency: 1.0 if referenced today, decays towards 0 over 30 days
            last_ref_str = mem.get("last_referenced")
            if last_ref_str:
                try:
                    last_ref = datetime.fromisoformat(last_ref_str.replace("Z", "+00:00"))
                    days_ago = (now - last_ref).total_seconds() / 86400
                    recency = max(0.0, 1.0 - days_ago / 30.0)
                except Exception:
                    recency = 0.5
            else:
                recency = 0.5
            return imp + decay + (recency * 0.2)

        ranked = sorted(result.data, key=score, reverse=True)
        return ranked[:limit]
    except Exception as e:
        logger.error(f"get_top_memories failed: {e}")
        return []


def get_all_memories(category: str | None = None) -> list[dict]:
    """Return all non-forgotten memories, optionally filtered by category."""
    try:
        query = get_client().table("memories").select("*").neq("category", "forget")
        if category:
            query = query.eq("category", category)
        result = query.order("importance", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"get_all_memories failed: {e}")
        return []


def delete_memory(memory_id: str) -> bool:
    try:
        get_client().table("memories").delete().eq("id", memory_id).execute()
        return True
    except Exception as e:
        logger.error(f"delete_memory failed: {e}")
        return False


def decay_memories() -> int:
    """
    Run the daily decay pass.
    - Decrease decay_score by 0.05 for memories not referenced in 7+ days
    - Archive (category='forget') if decay < 0.2 AND category != 'core'
    Returns count of affected memories.
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
        cutoff = now - timedelta(days=7)
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

                if new_decay < 0.2 and mem.get("category") != "core":
                    update_data["category"] = "forget"

                get_client().table("memories").update(update_data).eq("id", mem["id"]).execute()
                affected += 1

        return affected
    except Exception as e:
        logger.error(f"decay_memories failed: {e}")
        return 0


# ===================================================================
# CONVERSATIONS
# ===================================================================

def save_conversation(role: str, content: str, mood_detected: str = "", platform: str = "telegram") -> dict | None:
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
        logger.error(f"save_conversation failed: {e}")
        return None


def get_conversations(limit: int = 50) -> list[dict]:
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
        rows.reverse()  # chronological order
        return rows
    except Exception as e:
        logger.error(f"get_conversations failed: {e}")
        return []


def get_mood_history(days: int = 7) -> list[dict]:
    """Return mood counts grouped by day for the last N days."""
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

        # Group by date
        day_moods: dict[str, dict[str, int]] = {}
        for row in result.data:
            try:
                day = row["timestamp"][:10]  # YYYY-MM-DD
            except Exception:
                continue
            mood = row.get("mood_detected", "neutral")
            if day not in day_moods:
                day_moods[day] = {}
            day_moods[day][mood] = day_moods[day].get(mood, 0) + 1

        return [{"date": d, "moods": m} for d, m in sorted(day_moods.items())]
    except Exception as e:
        logger.error(f"get_mood_history failed: {e}")
        return []


# ===================================================================
# SIFRA STATE
# ===================================================================

def get_sifra_state() -> dict:
    """Return the single sifra_state row (or sensible defaults)."""
    try:
        result = get_client().table("sifra_state").select("*").limit(1).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"get_sifra_state failed: {e}")

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
    """Upsert the single sifra_state row."""
    try:
        updates["last_active"] = datetime.now(timezone.utc).isoformat()
        existing = get_client().table("sifra_state").select("id").limit(1).execute()
        if existing.data:
            get_client().table("sifra_state").update(updates).eq("id", existing.data[0]["id"]).execute()
        else:
            get_client().table("sifra_state").insert(updates).execute()
    except Exception as e:
        logger.error(f"update_sifra_state failed: {e}")


# ===================================================================
# PROACTIVE QUEUE
# ===================================================================

def get_pending_proactive_messages() -> list[dict]:
    """Get unsent proactive messages whose scheduled_for has passed."""
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
        logger.error(f"get_pending_proactive_messages failed: {e}")
        return []


def mark_proactive_sent(message_id: str) -> None:
    try:
        get_client().table("proactive_queue").update({"sent": True}).eq("id", message_id).execute()
    except Exception as e:
        logger.error(f"mark_proactive_sent failed: {e}")


def add_proactive_message(message: str, scheduled_for: str, trigger_type: str = "time_based") -> None:
    try:
        get_client().table("proactive_queue").insert({
            "message": message,
            "scheduled_for": scheduled_for,
            "sent": False,
            "trigger_type": trigger_type,
        }).execute()
    except Exception as e:
        logger.error(f"add_proactive_message failed: {e}")
