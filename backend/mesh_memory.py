"""
Mesh Memory System — the core intelligence layer.
Handles memory extraction, recall, spontaneous recall, and decay.
"""

import os
import json
import random
import logging
from groq import Groq

from supabase_client import (
    insert_memory,
    find_similar_memory,
    update_memory_reference,
    get_top_memories,
    get_all_memories,
    decay_memories as db_decay_memories,
)

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

EXTRACTION_PROMPT = """You are a memory extraction system.
Read the following conversation message from the user and extract any facts, preferences, emotions, habits, or events worth remembering about them.

Return a JSON array of memory objects. Each object must have:
- "content": string (the memory, written as a fact about the user — e.g. "He stays up till 3am coding")
- "category": one of "core", "emotional", "habit", "preference", "event"
  - core = identity facts (name, age, job, location)
  - emotional = feelings, emotional events, reactions
  - habit = behavioral patterns, routines
  - preference = likes, dislikes, opinions
  - event = specific one-time events or plans
- "importance": integer 1-10 (how significant this is to remember long-term)

If there is nothing worth remembering, return an empty JSON array: []

USER MESSAGE:
{message}

RECENT CONTEXT (for reference):
{context}

Return ONLY the JSON array. No explanation. No markdown fencing."""


def _get_groq_client() -> Groq:
    return Groq(api_key=GROQ_API_KEY)


# ===================================================================
# EXTRACTION — Step 1 of Mesh
# ===================================================================

def extract_memories(user_message: str, recent_context: str = "") -> list[dict]:
    """
    Run a Groq call to extract memorable facts from a user message.
    Returns a list of memory dicts (content, category, importance).
    """
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You extract memories from conversations. Return only valid JSON.",
                },
                {
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(
                        message=user_message, context=recent_context
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=1000,
        )

        raw = response.choices[0].message.content.strip()
        # Clean markdown fencing if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        memories = json.loads(raw)
        if not isinstance(memories, list):
            return []
        return memories
    except json.JSONDecodeError:
        logger.warning("Memory extraction returned invalid JSON")
        return []
    except Exception as e:
        logger.error(f"extract_memories failed: {e}")
        return []


# ===================================================================
# STORE — Step 2 of Mesh
# ===================================================================

def store_memories(extracted: list[dict]) -> int:
    """
    Store extracted memories intelligently.
    - If similar memory exists: update its reference count and importance
    - If new: insert fresh
    Returns count of memories processed.
    """
    count = 0
    for mem in extracted:
        content = mem.get("content", "").strip()
        category = mem.get("category", "event")
        importance = mem.get("importance", 5)

        if not content:
            continue

        # Validate category
        valid_categories = {"core", "emotional", "habit", "preference", "event"}
        if category not in valid_categories:
            category = "event"

        # Check for similar existing memory
        existing = find_similar_memory(content)
        if existing:
            # Update existing — bump importance if new one is higher
            new_imp = max(existing.get("importance", 5), importance)
            update_memory_reference(existing["id"], new_importance=new_imp)
        else:
            insert_memory(content, category, importance)

        count += 1
    return count


def process_memory_extraction(user_message: str, recent_context: str = "") -> int:
    """
    Full pipeline: extract → store. Called async after each message.
    Returns count of memories processed.
    """
    extracted = extract_memories(user_message, recent_context)
    if not extracted:
        return 0
    return store_memories(extracted)


# ===================================================================
# RECALL — Step 3 of Mesh
# ===================================================================

def recall_memories(limit: int = 8) -> list[dict]:
    """Fetch top memories by the scoring formula."""
    return get_top_memories(limit=limit)


def format_memories_for_prompt(memories: list[dict]) -> str:
    """Format recalled memories into a readable string for the system prompt."""
    if not memories:
        return "No specific memories loaded right now."

    lines = []
    for i, mem in enumerate(memories, 1):
        category = mem.get("category", "unknown")
        content = mem.get("content", "")
        importance = mem.get("importance", 5)
        lines.append(f"{i}. [{category}] {content} (importance: {importance}/10)")
    return "\n".join(lines)


# ===================================================================
# SPONTANEOUS RECALL — Step 4 of Mesh
# ===================================================================

def should_spontaneously_recall() -> bool:
    """10% chance per message to spontaneously bring up a memory."""
    return random.random() < 0.10


def get_random_memory_for_recall() -> dict | None:
    """Pick a random memory from top memories for spontaneous recall."""
    memories = get_top_memories(limit=20)
    if not memories:
        return None
    return random.choice(memories)


# ===================================================================
# DECAY — Step 5 of Mesh
# ===================================================================

def run_decay_job() -> int:
    """
    Daily decay pass. Delegates to supabase_client.decay_memories().
    Returns count of affected memories.
    """
    count = db_decay_memories()
    logger.info(f"Decay job completed: {count} memories affected")
    return count
