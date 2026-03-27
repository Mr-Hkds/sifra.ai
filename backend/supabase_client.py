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

def insert_memory(content: str, category: str, importance: int, embedding: list[float] | None = None) -> dict | None:
    """Insert a new memory, optionally with a semantic vector embedding."""
    try:
        data = {
            "content": content,
            "category": category,
            "importance": max(1, min(10, importance)),
            "decay_score": 1.0,
            "times_referenced": 1,
            "last_referenced": datetime.now(timezone.utc).isoformat(),
        }
        if embedding:
            data["embedding"] = embedding
            
        result = get_client().table("memories").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"insert_memory: {e}")
        return None


def search_similar_memories(query_embedding: list[float], match_threshold: float = 0.5, match_count: int = 15) -> list[dict]:
    """Perform cosine similarity semantic search across the embedding mesh."""
    try:
        result = get_client().rpc(
            "match_memories",
            {
                "query_embedding": query_embedding,
                "match_threshold": match_threshold,
                "match_count": match_count
            }
        ).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"search_similar_memories failed: {e}")
        return []


def find_similar_memory(content: str) -> dict | None:
    """Find a memory with very high word overlap (dedup only, not retrieval)."""
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
            # High threshold — only for dedup, not retrieval
            if overlap > 0.75 and overlap > best_score:
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


def get_memories_for_ranking(limit: int = 30) -> list[dict]:
    """
    Pre-filter: return top memories by importance + recency for AI ranking.
    This avoids sending ALL memories to the AI — only the best candidates.
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

        def pre_score(mem: dict) -> float:
            imp = (mem.get("importance", 5) / 10.0) * 0.5
            decay = mem.get("decay_score", 1.0) * 0.3
            last_ref_str = mem.get("last_referenced")
            recency = 0.3
            if last_ref_str:
                try:
                    last_ref = datetime.fromisoformat(last_ref_str.replace("Z", "+00:00"))
                    days_ago = (now - last_ref).total_seconds() / 86400
                    recency = max(0.0, 1.0 - days_ago / 30.0)
                except Exception:
                    pass
            return imp + decay + recency * 0.2

        ranked = sorted(result.data, key=pre_score, reverse=True)
        return ranked[:limit]
    except Exception as e:
        logger.error(f"get_memories_for_ranking: {e}")
        return []


def archive_memory(memory_id: str) -> bool:
    """Archive a memory (mark as forgotten) without deleting it."""
    try:
        get_client().table("memories").update(
            {"category": "forget"}
        ).eq("id", memory_id).execute()
        return True
    except Exception as e:
        logger.error(f"archive_memory: {e}")
        return False


def save_episode(summary: str, importance: int = 7) -> dict | None:
    """Save a conversation episode summary as a special memory."""
    try:
        data = {
            "content": summary,
            "category": "episode",
            "importance": max(1, min(10, importance)),
            "decay_score": 1.0,
            "times_referenced": 0,
            "last_referenced": datetime.now(timezone.utc).isoformat(),
        }
        result = get_client().table("memories").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"save_episode: {e}")
        return None


def get_daily_proactive_count() -> int:
    """Count proactive messages sent today."""
    try:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        result = (
            get_client()
            .table("conversations")
            .select("id")
            .eq("role", "sifra")
            .eq("mood_detected", "proactive")
            .gte("timestamp", today_start)
            .execute()
        )
        return len(result.data) if result.data else 0
    except Exception as e:
        logger.error(f"get_daily_proactive_count: {e}")
        return 0


def get_last_proactive_timestamp() -> str | None:
    """Get timestamp of the most recent proactive message."""
    try:
        result = (
            get_client()
            .table("conversations")
            .select("timestamp")
            .eq("role", "sifra")
            .eq("mood_detected", "proactive")
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0].get("timestamp")
        return None
    except Exception as e:
        logger.error(f"get_last_proactive_timestamp: {e}")
        return None


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


# ===================================================================
# RESET / FACTORY WIPE
# ===================================================================

def clear_all_memories() -> int:
    """Delete ALL memories. Returns count deleted."""
    try:
        result = get_client().table("memories").select("id").execute()
        count = len(result.data) if result.data else 0
        if count > 0:
            # Supabase needs a filter for delete — use neq on a non-existent value to match all
            get_client().table("memories").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        return count
    except Exception as e:
        logger.error(f"clear_all_memories: {e}")
        return 0


def clear_all_conversations() -> int:
    """Delete ALL conversation history. Returns count deleted."""
    try:
        result = get_client().table("conversations").select("id").execute()
        count = len(result.data) if result.data else 0
        if count > 0:
            get_client().table("conversations").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        return count
    except Exception as e:
        logger.error(f"clear_all_conversations: {e}")
        return 0


def full_reset() -> dict:
    """
    Factory reset — wipe everything and start fresh.
    Clears: memories, conversations, resets state.
    Returns summary of what was cleared.
    """
    memories_cleared = clear_all_memories()
    conversations_cleared = clear_all_conversations()

    # Reset Sifra's state to defaults
    update_sifra_state({
        "current_mood": "neutral",
        "energy_level": 7,
        "personality_mode": "normal",
        "today_summary": "",
        "core_rules": "",
        "active_memories": [],
    })

    return {
        "memories_cleared": memories_cleared,
        "conversations_cleared": conversations_cleared,
        "state_reset": True,
    }


# ===================================================================
# OBSERVATION LEARNING (Learn from other bots)
# ===================================================================

def log_observation(
    user_message: str,
    bot_response: str,
    bot_name: str = "rumik",
) -> dict | None:
    """Log a captured bot response for later analysis."""
    try:
        data = {
            "user_message": user_message,
            "bot_response": bot_response,
            "bot_name": bot_name,
            "analyzed": False,
        }
        result = get_client().table("observation_log").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"log_observation: {e}")
        return None


def get_unanalyzed_observations(bot_name: str = "rumik", limit: int = 50) -> list[dict]:
    """Fetch observations that haven't been analyzed yet."""
    try:
        result = (
            get_client()
            .table("observation_log")
            .select("*")
            .eq("bot_name", bot_name)
            .eq("analyzed", False)
            .order("created_at")
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"get_unanalyzed_observations: {e}")
        return []


def mark_observations_analyzed(observation_ids: list[str]) -> None:
    """Mark observations as analyzed after batch processing."""
    try:
        for obs_id in observation_ids:
            get_client().table("observation_log").update(
                {"analyzed": True}
            ).eq("id", obs_id).execute()
    except Exception as e:
        logger.error(f"mark_observations_analyzed: {e}")


def upsert_learning(
    category: str,
    pattern: str,
    examples: str = "",
    confidence: float = 0.7,
    source_bot: str = "rumik",
) -> dict | None:
    """Insert or update a learned pattern. If same category+pattern exists, update."""
    try:
        # Check for duplicate
        existing = (
            get_client()
            .table("observation_learnings")
            .select("*")
            .eq("category", category)
            .eq("source_bot", source_bot)
            .execute()
        )

        # Check word overlap with existing patterns in same category
        if existing.data:
            pattern_words = set(pattern.lower().split())
            for row in existing.data:
                existing_words = set(row["pattern"].lower().split())
                overlap = len(pattern_words & existing_words) / max(len(pattern_words), len(existing_words))
                if overlap > 0.6:
                    # Update existing — merge examples, boost confidence
                    merged_examples = row.get("examples", "") + "\n" + examples
                    # Keep examples trimmed
                    merged_lines = merged_examples.strip().split("\n")[-10:]
                    get_client().table("observation_learnings").update({
                        "pattern": pattern,
                        "examples": "\n".join(merged_lines),
                        "confidence": min(1.0, row.get("confidence", 0.5) + 0.05),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", row["id"]).execute()
                    return row

        # Insert new
        data = {
            "category": category,
            "pattern": pattern,
            "examples": examples,
            "confidence": confidence,
            "source_bot": source_bot,
        }
        result = get_client().table("observation_learnings").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"upsert_learning: {e}")
        return None


def get_all_learnings(source_bot: str | None = "rumik") -> list[dict]:
    """Get all learned patterns from a source bot, or all if None."""
    try:
        query = get_client().table("observation_learnings").select("*")
        if source_bot:
            query = query.eq("source_bot", source_bot)
        result = query.order("confidence", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"get_all_learnings: {e}")
        return []


def get_observation_stats(bot_name: str = "rumik") -> dict:
    """Get stats about observations and learnings."""
    try:
        logs = get_client().table("observation_log").select("id, analyzed").eq("bot_name", bot_name).execute()
        learnings = get_client().table("observation_learnings").select("id").eq("source_bot", bot_name).execute()

        total_obs = len(logs.data) if logs.data else 0
        analyzed = sum(1 for r in (logs.data or []) if r.get("analyzed"))

        return {
            "total_observations": total_obs,
            "analyzed": analyzed,
            "pending": total_obs - analyzed,
            "learnings_count": len(learnings.data) if learnings.data else 0,
        }
    except Exception as e:
        logger.error(f"get_observation_stats: {e}")
        return {"total_observations": 0, "analyzed": 0, "pending": 0, "learnings_count": 0}


# ---------------------------------------------------------------------------
# Proactive Messaging — Budget & Cooldown Tracking
# ---------------------------------------------------------------------------

def log_proactive_send(msg_type: str) -> None:
    """
    Log a proactive message send for budget/cooldown tracking.
    Stores as JSON list in the proactive_sends column of sifra_state.
    """
    try:
        import json
        now = datetime.now(timezone.utc).isoformat()
        
        state = get_sifra_state()
        raw = state.get("proactive_sends", "[]")
        sends = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, list) else [])

        # Append new send
        sends.append({"type": msg_type, "timestamp": now})

        # Keep only last 30 entries to prevent bloat
        sends = sends[-30:]

        update_sifra_state({"proactive_sends": json.dumps(sends)})
    except Exception as e:
        logger.error(f"log_proactive_send: {e}")


def get_daily_proactive_count() -> int:
    """Count how many proactive messages were sent today (UTC)."""
    try:
        import json
        state = get_sifra_state()
        raw = state.get("proactive_sends", "[]")
        sends = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, list) else [])

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        count = sum(1 for s in sends if isinstance(s, dict) and s.get("timestamp", "").startswith(today))
        return count
    except Exception as e:
        logger.error(f"get_daily_proactive_count: {e}")
        return 0


def get_last_proactive_timestamp() -> str | None:
    """Get the timestamp of the most recent proactive message."""
    try:
        import json
        state = get_sifra_state()
        raw = state.get("proactive_sends", "[]")
        sends = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, list) else [])

        if not sends:
            return None

        last = sends[-1]
        return last.get("timestamp") if isinstance(last, dict) else None
    except Exception as e:
        logger.error(f"get_last_proactive_timestamp: {e}")
        return None

