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

EXTRACTION_PROMPT = """You extract facts EXCLUSIVELY about the USER (Harkamal) and EXCLUSIVELY from the provided "USER MESSAGE" section.

CRITICAL RULES:
1. ONLY analyze the exact text under "USER MESSAGE".
2. The "RECENT CONTEXT" is ONLY provided to help you understand what the USER MESSAGE is referring to.
3. NEVER, UNDER ANY CIRCUMSTANCES, extract facts, events, or preferences from Sifra's messages in the context. Ignore what Sifra likes or does.
4. Focus on the USER's: life facts, feelings, plans, preferences, habits, opinions, communication style.
5. Do NOT extract trivial filler ("ok", "haha", "hmm").
6. Write memories as facts about him. For habits, preferences, and events, you MUST include an exact quote as a reference. Example: "He stays up till 3am coding. (Quote: 'main toh 3 baje tak code kar raha tha')"

Return a JSON object with a "memories" key containing an array. Each item:
- "content": string (the memory fact. MUST include the exact Quote from the message at the end)
- "category": one of "core", "emotional", "habit", "preference", "event"
  - core = identity (name, age, job, location, relationships)
  - emotional = feelings, emotional events, moods
  - habit = patterns, routines, communication style
  - preference = likes, dislikes, opinions
  - event = one-time events, plans, news
- "importance": integer 1-10

If there is nothing worth remembering specifically from the USER MESSAGE, return: {{"memories": []}}

RECENT CONTEXT (For reference ONLY. DO NOT extract facts about Sifra!):
{context}

USER MESSAGE (Extract facts ONLY from this!):
{message}"""


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
    Store extracted memories with smart dedup and contradiction resolution.
    If similar exists, update. If contradicts, archive old and store new.
    Returns count of memories processed.
    """
    from supabase_client import (
        insert_memory, find_similar_memory, update_memory_reference,
        archive_memory, get_all_active_memories,
    )

    count = 0
    all_memories = None  # Lazy load

    for mem in extracted:
        content = mem["content"]
        category = mem["category"]
        importance = mem["importance"]

        # Step 1: Check for near-duplicate
        existing = find_similar_memory(content)
        if existing:
            new_imp = max(existing.get("importance", 5), importance)
            update_memory_reference(existing["id"], new_importance=new_imp)
            count += 1
            continue

        # Step 2: Check for contradictions (only for core/habit/preference)
        if category in ("core", "habit", "preference"):
            if all_memories is None:
                all_memories = get_all_active_memories()

            same_category = [
                m for m in all_memories
                if m.get("category") == category
            ]

            for old_mem in same_category:
                try:
                    result = ai_client.extract_json(
                        system_prompt="Check for factual contradictions. Return valid JSON.",
                        user_prompt=CONTRADICTION_PROMPT.format(
                            existing=old_mem.get("content", ""),
                            new=content,
                        ),
                        temperature=0.1,
                        max_tokens=100,
                    )
                    if isinstance(result, dict) and result.get("contradicts"):
                        logger.info(
                            f"Contradiction found: archiving old memory '{old_mem.get('content', '')[:50]}' "
                            f"→ replaced with '{content[:50]}'"
                        )
                        archive_memory(old_mem["id"])
                        break
                except Exception as e:
                    logger.warning(f"Contradiction check failed: {e}")

        # Step 3: Insert new memory
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
# RETRIEVAL — AI-Powered Semantic Recall
# ---------------------------------------------------------------------------

RANKING_PROMPT = """You are a memory retrieval system. Given a current message from a user, rank how relevant each memory is to the current conversation.

CURRENT MESSAGE: "{message}"

MEMORIES TO RANK (each has an ID number):
{memories_list}

For each memory, rate its relevance to the current message on a scale of 0-10:
- 10 = directly about the same topic, should definitely be recalled
- 7-9 = related topic, would add meaningful context
- 4-6 = loosely related, might be useful background
- 1-3 = not related to current message
- 0 = completely irrelevant

Consider SEMANTIC meaning, not just word matches. "kal test hai" is related to memories about exams, studying, academic stress, etc.

Return a JSON object: {{"rankings": [{{"id": 1, "score": 8}}, {{"id": 2, "score": 3}}, ...]}}"""


def recall_for_context(current_message: str, limit: int = MEMORY_RECALL_LIMIT) -> list[dict]:
    """
    Retrieve memories relevant to the current conversation using AI ranking.
    
    Strategy:
    1. Pre-filter: get top 30 memories by importance + recency (fast, no AI)
    2. AI rank: send to AI for semantic relevance scoring
    3. Blend: combine AI relevance with importance/recency for final ranking
    
    Falls back to importance-based ranking if AI call fails.
    """
    from supabase_client import get_memories_for_ranking

    candidates = get_memories_for_ranking(limit=30)
    if not candidates:
        return []

    # If very few memories, skip AI ranking — just return them all
    if len(candidates) <= limit:
        return candidates

    # Build numbered list for AI
    memories_list = ""
    for i, mem in enumerate(candidates):
        memories_list += f"{i+1}. [{mem.get('category', '?')}] {mem.get('content', '')}\n"

    try:
        result = ai_client.extract_json(
            system_prompt="Rank memory relevance to current message. Return valid JSON.",
            user_prompt=RANKING_PROMPT.format(
                message=current_message,
                memories_list=memories_list.strip(),
            ),
            temperature=0.15,
            max_tokens=500,
        )

        rankings = []
        if isinstance(result, dict):
            rankings = result.get("rankings", [])

        if rankings:
            # Build score map: memory index → AI relevance score
            score_map = {}
            for r in rankings:
                if isinstance(r, dict):
                    idx = r.get("id", 0) - 1  # Convert 1-indexed to 0-indexed
                    score = r.get("score", 0)
                    if 0 <= idx < len(candidates):
                        score_map[idx] = score

            # Blend AI relevance with importance for final ranking
            scored = []
            for i, mem in enumerate(candidates):
                ai_score = score_map.get(i, 3)  # Default to low relevance if missing
                importance = mem.get("importance", 5)
                # AI relevance is primary (60%), importance is secondary (40%)
                final_score = (ai_score / 10.0) * 0.6 + (importance / 10.0) * 0.4
                scored.append((final_score, mem))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [m for _, m in scored[:limit]]

    except Exception as e:
        logger.warning(f"AI memory ranking failed, using fallback: {e}")

    # Fallback: return candidates already sorted by importance+recency
    return candidates[:limit]


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
