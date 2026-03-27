"""
SIFRA:MIND — Memory Engine v2.
Smart memory system: extract → store → AI-ranked retrieval → episodic → consolidation → decay.

Upgrades over v1:
- AI-powered semantic retrieval (replaces word-overlap matching)
- Episodic memory (conversation summaries, not just extracted facts)
- Memory consolidation (merges fragmented entries about the same topic)
- Contradiction resolution (archives old facts when new info contradicts)
"""

import json
import random
import logging

import ai_client
from config import (
    MEMORY_RECALL_LIMIT, MEMORY_DECAY_DAYS,
    MEMORY_FORGET_THRESHOLD,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EXTRACTION — Pull facts from user messages
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are a highly selective memory extraction system. You extract LONG-TERM, MEANINGFUL facts about the USER (Harkamal) from the provided "USER MESSAGE".

CRITICAL RULES:
1. ONLY analyze the exact text under "USER MESSAGE". The context is just for understanding.
2. EXTREME SELECTIVITY: Do NOT extract random conversational events (e.g., "He asked for a joke", "He used informal language", "He wants a GIF"). These are USELESS.
3. ONLY extract concrete, long-term facts: real-life events, persistent preferences (e.g., "His favorite character is Jethalal"), relationships, career details, or strong personal opinions.
4. If the message is just chatting, asking a question, or reacting, return {"memories": []}. It is better to extract NOTHING than to extract garbage.
5. NEVER extract facts about Sifra or the AI's behavior.
6. REFERENCE REQUIREMENT: Every single memory MUST end with at least 1-2 exact quote references from the message to prove it's a real fact. Example: "He stays up till 3am coding. (Quote: 'main toh 3 baje tak code kar raha tha')"

Return a JSON object with a "memories" key containing an array. Each item:
- "content": string (the memory fact. MUST include the exact Quote(s) from the message at the end)
- "category": one of "core", "emotional", "habit", "preference", "event"
  - core = identity (name, age, job, location, relationships)
  - emotional = deep feelings, persistent moods
  - habit = real-life patterns, routines (NOT chat habits)
  - preference = genuine likes, dislikes, opinions
  - event = significant real-life events, plans, news
- "importance": integer 1-10

If there is nothing worth remembering specifically from the USER MESSAGE, return: {{"memories": []}}

RECENT CONTEXT (For reference ONLY. DO NOT extract facts about Sifra!):
{context}

USER MESSAGE (Extract facts ONLY from this!):
{message}"""


def extract_memories(user_message: str, recent_context: str = "") -> list[dict]:
    """
    Extract memorable facts from a user message using AI.
    Uses the FAST model (Groq 8B) for instant inference to stay within Vercel's timeout.
    Returns a list of memory dicts with content, category, importance.
    """
    prompt = EXTRACTION_PROMPT.format(message=user_message, context=recent_context or "(no context)")
    
    try:
        raw = ai_client.fast(
            system_prompt="Extract memories from conversations. Return valid JSON with a 'memories' key. If nothing worth remembering, return {\"memories\": []}.",
            user_prompt=prompt,
            temperature=0.15,
            max_tokens=300,
        )
    except Exception as e:
        logger.error(f"Memory extraction AI call failed: {e}")
        return []

    if not raw:
        return []

    # Parse JSON from response
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Try cleaning markdown fences
        clean = raw.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        try:
            result = json.loads(clean.strip())
        except json.JSONDecodeError:
            logger.warning(f"Memory extraction: could not parse JSON from: {raw[:200]}")
            return []

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

    logger.info(f"Extracted {len(validated)} memories from message")
    return validated


# ---------------------------------------------------------------------------
# STORAGE — Intelligent dedup + contradiction check
# ---------------------------------------------------------------------------

CONTRADICTION_PROMPT = """You are checking if a NEW fact about a person contradicts an EXISTING fact.

EXISTING fact: "{existing}"
NEW fact: "{new}"

Does the NEW fact DIRECTLY CONTRADICT the existing one? (e.g., location changed, relationship status changed, opinion reversed)
Note: additional details are NOT contradictions. Only direct conflicts count.

Return JSON: {{"contradicts": true/false, "reason": "brief explanation"}}"""


def store_memories(extracted: list[dict]) -> int:
    """
    Store extracted memories with smart dedup.
    Optimized for Vercel: skips expensive embedding/contradiction checks.
    Returns count of memories processed.
    """
    from supabase_client import (
        insert_memory, find_similar_memory, update_memory_reference,
    )

    count = 0

    for mem in extracted:
        content = mem["content"]
        category = mem["category"]
        importance = mem["importance"]

        # Step 1: Check for near-duplicate (fast text comparison, no AI call)
        try:
            existing = find_similar_memory(content)
            if existing:
                new_imp = max(existing.get("importance", 5), importance)
                update_memory_reference(existing["id"], new_importance=new_imp)
                logger.info(f"Updated existing memory: {content[:50]}")
                count += 1
                continue
        except Exception as e:
            logger.warning(f"Dedup check failed, inserting anyway: {e}")

        # Step 2: Insert new memory (no embedding — saves 3-5s per memory)
        # Embeddings can be backfilled later via a batch job
        try:
            result = insert_memory(content, category, importance, embedding=None)
            if result:
                logger.info(f"Stored memory: [{category}] {content[:60]}")
                count += 1
            else:
                logger.error(f"insert_memory returned None for: {content[:60]}")
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")

    return count


def process_extraction(user_message: str, recent_context: str = "") -> int:
    """Full pipeline: extract → store. Called async after each message."""
    extracted = extract_memories(user_message, recent_context)
    if not extracted:
        return 0
    return store_memories(extracted)


# ---------------------------------------------------------------------------
# RETRIEVAL — AI-Powered Semantic Recall
# ---------------------------------------------------------------------------

def recall_for_context(current_message: str, limit: int = MEMORY_RECALL_LIMIT) -> list[dict]:
    """
    Retrieve memories relevant to the current conversation using Semantic Vector Search.
    Falls back to recency/importance if embedding fails.
    """
    from supabase_client import get_memories_for_ranking, search_similar_memories

    # 1. Generate embedding for the current user message
    query_embedding = ai_client.get_embedding(current_message)

    if query_embedding:
        # 2. Perform vector search in Supabase (Cosine Similarity)
        # Using a low threshold (0.15) because Gemini embeddings cluster tightly.
        results = search_similar_memories(query_embedding, match_threshold=0.15, match_count=limit)
        
        if results:
            # Sort by similarity combined with a slight boost for importance
            def embed_score(mem):
                sim = mem.get("similarity", 0.0)
                imp = (mem.get("importance", 5) / 10.0) * 0.15
                return sim + imp
                
            ranked = sorted(results, key=embed_score, reverse=True)
            return ranked[:limit]

    # Fallback: if API fails or no vector results
    logger.warning("Vector search skipped or yielded 0 results, using fallback recall.")
    candidates = get_memories_for_ranking(limit=limit)
    return candidates


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
# EPISODIC MEMORY — Conversation summaries
# ---------------------------------------------------------------------------

EPISODE_PROMPT = """Summarize this conversation between Harkamal and Sifra into a brief episodic memory.
Capture the ESSENCE — what was discussed, the emotional tone, and any important takeaways.

Format: One sentence that captures the vibe. Like a diary entry.
Examples:
- "Late night talk where Harkamal was stressed about placements, Sifra comforted him and they ended up sharing childhood memories"
- "Quick excited exchange about a new project idea he had, he was buzzing with energy"
- "He was bored and just wanted to chat, conversation stayed lighthearted with lots of teasing"

CONVERSATION:
{conversation}

Return JSON: {{"summary": "...", "importance": 5-9}}"""


def extract_episode(conversation_messages: list[dict]) -> dict | None:
    """
    Extract an episodic memory from a conversation session.
    Called when a conversation ends (gap > 30 min detected).
    Returns the episode dict or None.
    """
    if len(conversation_messages) < 4:
        return None  # Too short to be meaningful

    # Format conversation
    conv_text = ""
    for msg in conversation_messages[-20:]:  # Last 20 messages max
        role = "Harkamal" if msg.get("role") == "user" else "Sifra"
        content = msg.get("content", "")
        if content:
            conv_text += f"{role}: {content}\n"

    if not conv_text.strip():
        return None

    try:
        result = ai_client.extract_json(
            system_prompt="Summarize conversations into brief episodic memories. Return valid JSON.",
            user_prompt=EPISODE_PROMPT.format(conversation=conv_text.strip()),
            temperature=0.4,
            max_tokens=200,
        )

        if isinstance(result, dict) and result.get("summary"):
            from supabase_client import save_episode
            summary = result["summary"]
            importance = result.get("importance", 7)
            try:
                importance = max(5, min(9, int(importance)))
            except (ValueError, TypeError):
                importance = 7

            saved = save_episode(summary, importance)
            if saved:
                logger.info(f"Episode saved: {summary[:60]}...")
                return saved

    except Exception as e:
        logger.error(f"Episode extraction failed: {e}")

    return None


# ---------------------------------------------------------------------------
# CONSOLIDATION — Merge fragmented memories
# ---------------------------------------------------------------------------

CONSOLIDATION_PROMPT = """You are merging multiple related memory fragments about a person into one rich, consolidated memory.

MEMORIES TO MERGE:
{memories}

Rules:
1. Combine all information into one comprehensive sentence or two
2. Preserve specific quotes and references from the original memories
3. Keep the most important details, drop redundant ones
4. The result should read like a complete understanding, not a list

Return JSON: {{"consolidated": "the merged memory text", "importance": 5-10}}"""


def consolidate_memories() -> int:
    """
    Merge fragmented memories about the same topic into richer entries.
    Run periodically (daily). Groups memories by AI-detected topic similarity.
    Returns count of consolidations performed.
    """
    from supabase_client import get_all_active_memories, insert_memory, archive_memory

    all_memories = get_all_active_memories()
    if len(all_memories) < 10:
        return 0  # Not enough to consolidate

    # Group by category first (cheap filter)
    by_category: dict[str, list[dict]] = {}
    for mem in all_memories:
        cat = mem.get("category", "event")
        if cat in ("episode", "core"):
            continue  # Don't consolidate episodes or core identity
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(mem)

    consolidations = 0

    for category, mems in by_category.items():
        if len(mems) < 3:
            continue  # Need at least 3 to consider consolidation

        # Ask AI to find groups of related memories
        mem_texts = "\n".join(
            f"{i+1}. {m.get('content', '')}" for i, m in enumerate(mems[:20])
        )

        try:
            group_result = ai_client.extract_json(
                system_prompt="Group related memories about the same topic. Return valid JSON.",
                user_prompt=f"""These are memories about a person, all in category "{category}".
Find groups of 2+ memories that are about the SAME topic and could be merged into one richer memory.

MEMORIES:
{mem_texts}

Return JSON: {{"groups": [[1, 3, 5], [2, 7]]}} where numbers are the memory IDs from the list above.
Only group memories that are GENUINELY about the same specific topic.
If no memories should be merged, return {{"groups": []}}""",
                temperature=0.2,
                max_tokens=300,
            )

            groups = []
            if isinstance(group_result, dict):
                groups = group_result.get("groups", [])

            for group in groups:
                if not isinstance(group, list) or len(group) < 2:
                    continue

                # Get the actual memory objects
                group_mems = []
                for idx in group:
                    try:
                        actual_idx = int(idx) - 1
                        if 0 <= actual_idx < len(mems):
                            group_mems.append(mems[actual_idx])
                    except (ValueError, TypeError):
                        continue

                if len(group_mems) < 2:
                    continue

                # Merge them
                merge_text = "\n".join(
                    f"- {m.get('content', '')}" for m in group_mems
                )

                merge_result = ai_client.extract_json(
                    system_prompt="Merge related memories into one. Return valid JSON.",
                    user_prompt=CONSOLIDATION_PROMPT.format(memories=merge_text),
                    temperature=0.3,
                    max_tokens=200,
                )

                if isinstance(merge_result, dict) and merge_result.get("consolidated"):
                    consolidated_text = merge_result["consolidated"]
                    importance = merge_result.get("importance", 7)
                    try:
                        importance = max(5, min(10, int(importance)))
                    except (ValueError, TypeError):
                        importance = 7

                    # Archive old memories and insert consolidated one
                    for old_mem in group_mems:
                        archive_memory(old_mem["id"])

                    insert_memory(consolidated_text, category, importance)
                    consolidations += 1
                    logger.info(f"Consolidated {len(group_mems)} memories → '{consolidated_text[:60]}...'")

        except Exception as e:
            logger.error(f"Consolidation failed for category {category}: {e}")

    logger.info(f"Memory consolidation: {consolidations} merges performed")
    return consolidations


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
