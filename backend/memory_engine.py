"""
SIFRA:MIND — Memory Engine.
Complete memory system: extract → store → contextual retrieval → decay.
Replaces the old mesh_memory.py with smarter, context-aware memory handling.
"""

import json
import random
import logging

import ai_client
from config import (
    MEMORY_RECALL_LIMIT, MEMORY_DECAY_DAYS,
    MEMORY_FORGET_THRESHOLD, MEMORY_SIMILARITY_THRESHOLD,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EXTRACTION — Pull facts from user messages
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You extract facts about the USER (Harkamal) from their messages.

RULES:
- ONLY extract info about the USER. Ignore anything Sifra (the AI) said.
- Focus on: life facts, feelings, plans, preferences, habits, opinions, communication style.
- Do NOT extract trivial filler ("ok", "haha", "hmm").
- Write memories as facts about him: "He stays up till 3am coding", "He's stressed about exams".

Return a JSON object with a "memories" key containing an array. Each item:
- "content": string (the memory, as a fact about the user)
- "category": one of "core", "emotional", "habit", "preference", "event"
  - core = identity (name, age, job, location, relationships)
  - emotional = feelings, emotional events, moods
  - habit = patterns, routines, communication style
  - preference = likes, dislikes, opinions
  - event = one-time events, plans, news
- "importance": integer 1-10

If nothing worth remembering, return: {{"memories": []}}

USER MESSAGE:
{message}

RECENT CONTEXT (reference only — don't extract from Sifra's replies):
{context}"""


def extract_memories(user_message: str, recent_context: str = "") -> list[dict]:
    """
    Extract memorable facts from a user message using AI.
    Returns a list of memory dicts with content, category, importance.
    """
    result = ai_client.extract_json(
        system_prompt="Extract memories from conversations. Return valid JSON with a 'memories' key.",
        user_prompt=EXTRACTION_PROMPT.format(message=user_message, context=recent_context or "(no context)"),
    )

    # Handle both {"memories": [...]} and direct [...] formats
    if isinstance(result, dict):
        memories = result.get("memories", [])
    elif isinstance(result, list):
        memories = result
    else:
        return []

    # Validate each memory
    valid_categories = {"core", "emotional", "habit", "preference", "event"}
    validated = []
    for mem in memories:
        if not isinstance(mem, dict):
            continue
        content = mem.get("content", "").strip()
        if not content or len(content) < 5:
            continue

        category = mem.get("category", "event")
        if category not in valid_categories:
            category = "event"

        importance = mem.get("importance", 5)
        try:
            importance = max(1, min(10, int(importance)))
        except (ValueError, TypeError):
            importance = 5

        validated.append({
            "content": content,
            "category": category,
            "importance": importance,
        })

    return validated


# ---------------------------------------------------------------------------
# STORAGE — Intelligent dedup and storage
# ---------------------------------------------------------------------------

def store_memories(extracted: list[dict]) -> int:
    """
    Store extracted memories. If similar exists, update. If new, insert.
    Returns count of memories processed.
    """
    from supabase_client import insert_memory, find_similar_memory, update_memory_reference

    count = 0
    for mem in extracted:
        content = mem["content"]
        category = mem["category"]
        importance = mem["importance"]

        existing = find_similar_memory(content)
        if existing:
            new_imp = max(existing.get("importance", 5), importance)
            update_memory_reference(existing["id"], new_importance=new_imp)
        else:
            insert_memory(content, category, importance)

        count += 1
    return count


def process_extraction(user_message: str, recent_context: str = "") -> int:
    """Full pipeline: extract → store. Called async after each message."""
    extracted = extract_memories(user_message, recent_context)
    if not extracted:
        return 0
    return store_memories(extracted)


# ---------------------------------------------------------------------------
# RETRIEVAL — Context-aware memory recall
# ---------------------------------------------------------------------------

def recall_for_context(current_message: str, limit: int = MEMORY_RECALL_LIMIT) -> list[dict]:
    """
    Retrieve memories relevant to the current conversation.
    Uses a hybrid scoring: topic relevance + importance + recency + decay.
    This is the KEY upgrade over the old system which just grabbed top-N by score.
    """
    from supabase_client import get_all_active_memories
    from datetime import datetime, timezone

    all_memories = get_all_active_memories()
    if not all_memories:
        return []

    now = datetime.now(timezone.utc)
    msg_words = set(current_message.lower().split())
    # Remove very common words for better relevance matching
    stopwords = {"i", "a", "an", "the", "is", "am", "are", "was", "were", "be",
                 "to", "of", "in", "it", "and", "or", "but", "not", "on", "at",
                 "for", "with", "this", "that", "me", "my", "you", "your", "he",
                 "she", "do", "did", "so", "if", "no", "yes", "ok", "hi", "hey",
                 "haan", "nahi", "hai", "ho", "ka", "ki", "ke", "se", "ko", "ne",
                 "toh", "bhi", "ya", "yr", "na", "kya", "mein", "tu", "mujhe"}
    msg_words -= stopwords

    scored = []
    for mem in all_memories:
        mem_content = mem.get("content", "")
        mem_words = set(mem_content.lower().split()) - stopwords
        importance = mem.get("importance", 5)
        decay = mem.get("decay_score", 1.0)

        # Topic relevance (0-1)
        if msg_words and mem_words:
            relevance = len(msg_words & mem_words) / max(len(msg_words), 1)
        else:
            relevance = 0.0

        # Recency (0-1, decays over 30 days)
        last_ref_str = mem.get("last_referenced")
        if last_ref_str:
            try:
                last_ref = datetime.fromisoformat(last_ref_str.replace("Z", "+00:00"))
                days_ago = (now - last_ref).total_seconds() / 86400
                recency = max(0.0, 1.0 - days_ago / 30.0)
            except Exception:
                recency = 0.3
        else:
            recency = 0.3

        # Composite score: relevance is most important when present
        # But importance + recency still matter for general context
        if relevance > 0.15:
            # Message is related to this memory — boost it heavily
            score = relevance * 0.45 + (importance / 10.0) * 0.25 + decay * 0.15 + recency * 0.15
        else:
            # Not directly related — fall back to importance-based ranking
            score = (importance / 10.0) * 0.40 + decay * 0.30 + recency * 0.30

        scored.append((score, mem))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:limit]]


def format_for_prompt(memories: list[dict]) -> str:
    """Format memories into a clean string for the system prompt."""
    if not memories:
        return "Nothing specific saved yet."

    lines = []
    for mem in memories:
        cat = mem.get("category", "")
        content = mem.get("content", "")
        lines.append(f"• [{cat}] {content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SPONTANEOUS RECALL — Random memory surfacing
# ---------------------------------------------------------------------------

def should_spontaneously_recall() -> bool:
    """8% chance per message to bring up a memory unprompted."""
    return random.random() < 0.08


def get_random_memory() -> dict | None:
    """Pick a random memory for spontaneous recall."""
    from supabase_client import get_top_memories
    memories = get_top_memories(limit=20)
    return random.choice(memories) if memories else None


# ---------------------------------------------------------------------------
# DECAY — Memory aging
# ---------------------------------------------------------------------------

def run_decay() -> int:
    """
    Daily decay pass. Fades unreferenced memories.
    Returns count of affected memories.
    """
    from supabase_client import decay_memories
    count = decay_memories()
    logger.info(f"Decay job: {count} memories affected")
    return count
