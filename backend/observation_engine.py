"""
SIFRA:MIND — Observation Engine.
Learn from other bots by analyzing their conversational patterns.
Captures → Analyzes → Distills → Injects into Sifra's personality.

Architecture:
1. Telegram handler captures bot messages in training group
2. Raw exchanges stored in observation_log
3. Batch analysis extracts behavioral patterns via AI
4. Patterns stored in observation_learnings
5. brain.py injects high-confidence learnings into system prompt
"""

import logging
import threading

import ai_client
from config import (
    OBSERVATION_BATCH_SIZE,
    OBSERVATION_MAX_LEARNINGS,
    OBSERVATION_ANALYSIS_TEMPERATURE,
)
from supabase_client import (
    log_observation,
    get_unanalyzed_observations,
    mark_observations_analyzed,
    upsert_learning,
    get_all_learnings,
    get_observation_stats,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Analysis Prompt — The Brain of Observation
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """You are analyzing a chatbot's conversational behavior to extract patterns.

Below are message exchanges between a USER and a BOT named "{bot_name}".
Study the BOT's responses carefully and extract SPECIFIC behavioral patterns.

FOCUS ON:
1. RESPONSE STYLE: Average length, sentence structure, use of fragments vs full sentences
2. LANGUAGE MIX: Ratio of Hindi/English/Hinglish, how languages are mixed
3. EMOJI/STICKER PATTERNS: Which emojis used, frequency, placement (start/middle/end)
4. EMOTIONAL REACTIONS: How the bot responds to different emotions (sadness, excitement, anger, boredom)
5. CONVERSATION FLOW: How it opens conversations, changes topics, asks follow-ups
6. HUMOR STYLE: Roasting, sarcasm, puns, self-deprecating, dry humor
7. UNIQUE PHRASES: Signature phrases, common openings, filler words, catchphrases
8. IMAGE/MEDIA HANDLING: How it reacts to photos, links, media

For each pattern found, provide:
- category: one of "response_style", "language", "emoji", "emotional", "flow", "humor", "phrases", "media"
- pattern: a concise, actionable description that could guide another chatbot's behavior
- examples: 1-2 actual bot messages that demonstrate this pattern

Return a JSON object with a "patterns" key containing an array of pattern objects.
If you can't find meaningful patterns, return {{"patterns": []}}

EXCHANGES:
{exchanges}"""


# ---------------------------------------------------------------------------
# Observation Capture
# ---------------------------------------------------------------------------

def capture_exchange(user_message: str, bot_response: str, bot_name: str = "rumik") -> bool:
    """
    Capture a single user→bot exchange for later analysis.
    Called by telegram_handler when it detects a bot message in the training group.
    """
    try:
        result = log_observation(user_message, bot_response, bot_name)
        if result:
            logger.info(f"Captured observation from {bot_name}: {bot_response[:60]}...")

            # Check if we've accumulated enough for batch analysis
            stats = get_observation_stats(bot_name)
            if stats["pending"] >= OBSERVATION_BATCH_SIZE:
                logger.info(f"Batch threshold reached ({stats['pending']} pending). Triggering analysis...")
                thread = threading.Thread(
                    target=run_batch_analysis,
                    args=(bot_name,),
                    daemon=True,
                )
                thread.start()

            return True
        return False
    except Exception as e:
        logger.error(f"capture_exchange failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Single Message Learning (for /learn command)
# ---------------------------------------------------------------------------

def learn_from_single(message_text: str, bot_name: str = "rumik") -> str:
    """
    Analyze a single forwarded message and extract quick patterns.
    Returns a human-readable summary of what was learned.
    """
    try:
        # Store it
        log_observation("(forwarded — no user context)", message_text, bot_name)

        # Quick single-message analysis
        prompt = f"""Analyze this single message from a chatbot called "{bot_name}" and identify
any notable conversational patterns (style, emoji use, tone, language mix, humor).

Message: "{message_text}"

Return a JSON object with a "patterns" key. Each pattern has:
- category: one of "response_style", "language", "emoji", "emotional", "flow", "humor", "phrases", "media"
- pattern: concise description
- examples: the relevant part of the message

If nothing notable, return {{"patterns": []}}"""

        result = ai_client.extract_json(
            system_prompt="Extract conversational patterns from bot messages. Return valid JSON.",
            user_prompt=prompt,
        )

        patterns = result.get("patterns", []) if isinstance(result, dict) else []

        if not patterns:
            return "noted, but nothing new to learn from this one 📝"

        count = 0
        for p in patterns:
            if isinstance(p, dict) and p.get("category") and p.get("pattern"):
                upsert_learning(
                    category=p["category"],
                    pattern=p["pattern"],
                    examples=p.get("examples", message_text[:100]),
                    source_bot=bot_name,
                )
                count += 1

        return f"learned {count} pattern{'s' if count != 1 else ''} from this message 🧠"

    except Exception as e:
        logger.error(f"learn_from_single failed: {e}")
        return "couldn't analyze that one, try again?"


# ---------------------------------------------------------------------------
# Batch Analysis — The Deep Study
# ---------------------------------------------------------------------------

def run_batch_analysis(bot_name: str = "rumik") -> dict:
    """
    Analyze accumulated observations in batch.
    This is where the real learning happens — AI studies multiple exchanges
    and extracts recurring behavioral patterns.

    Returns {patterns_found: int, observations_processed: int}
    """
    try:
        observations = get_unanalyzed_observations(bot_name, limit=50)
        if not observations:
            return {"patterns_found": 0, "observations_processed": 0}

        # Format exchanges for the AI
        exchanges = []
        for obs in observations:
            user_msg = obs.get("user_message", "(unknown)")
            bot_resp = obs.get("bot_response", "")
            exchanges.append(f"USER: {user_msg}\n{bot_name.upper()}: {bot_resp}")

        exchanges_text = "\n---\n".join(exchanges)

        # Run AI analysis
        result = ai_client.extract_json(
            system_prompt="You are a conversational pattern analyst. Extract behavioral patterns from bot conversations. Return valid JSON.",
            user_prompt=ANALYSIS_PROMPT.format(bot_name=bot_name, exchanges=exchanges_text),
        )

        patterns = result.get("patterns", []) if isinstance(result, dict) else []

        # Store patterns
        count = 0
        for p in patterns:
            if not isinstance(p, dict):
                continue
            category = p.get("category", "")
            pattern = p.get("pattern", "")
            examples = p.get("examples", "")

            if not category or not pattern:
                continue

            # Normalize examples to string
            if isinstance(examples, list):
                examples = "\n".join(str(e) for e in examples)
            elif not isinstance(examples, str):
                examples = str(examples)

            upsert_learning(
                category=category,
                pattern=pattern,
                examples=examples[:500],
                source_bot=bot_name,
            )
            count += 1

        # Mark as analyzed
        obs_ids = [obs["id"] for obs in observations if "id" in obs]
        if obs_ids:
            mark_observations_analyzed(obs_ids)

        logger.info(f"Batch analysis: {count} patterns from {len(observations)} observations")
        return {"patterns_found": count, "observations_processed": len(observations)}

    except Exception as e:
        logger.error(f"run_batch_analysis failed: {e}")
        return {"patterns_found": 0, "observations_processed": 0}


# ---------------------------------------------------------------------------
# Prompt Injection — Feed Learnings to Brain
# ---------------------------------------------------------------------------

def get_learnings_for_prompt(source_bot: str = "rumik") -> str:
    """
    Format learned patterns into natural language for brain.py injection.
    Only includes high-confidence patterns.
    Returns empty string if no learnings.
    """
    try:
        learnings = get_all_learnings(source_bot)
        if not learnings:
            return ""

        # Only include patterns with decent confidence
        good_learnings = [l for l in learnings if l.get("confidence", 0) >= 0.5]
        if not good_learnings:
            return ""

        # Group by category
        by_category: dict[str, list[str]] = {}
        for l in good_learnings[:OBSERVATION_MAX_LEARNINGS]:
            cat = l.get("category", "general")
            pattern = l.get("pattern", "")
            if pattern:
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(pattern)

        if not by_category:
            return ""

        # Format naturally
        category_labels = {
            "response_style": "Response Style",
            "language": "Language Mix",
            "emoji": "Emoji & Sticker Use",
            "emotional": "Emotional Responses",
            "flow": "Conversation Flow",
            "humor": "Humor Style",
            "phrases": "Signature Phrases",
            "media": "Media Handling",
        }

        lines = []
        for cat, patterns in by_category.items():
            label = category_labels.get(cat, cat.title())
            lines.append(f"{label}:")
            for p in patterns[:5]:  # Max 5 per category
                lines.append(f"  • {p}")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"get_learnings_for_prompt failed: {e}")
        return ""
