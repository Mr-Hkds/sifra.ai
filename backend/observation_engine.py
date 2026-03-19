"""
SIFRA:MIND — Observation Engine v2.
Learn from other bots by analyzing their conversational patterns.
Now with thread-aware analysis, meta-learning, and deeper pattern extraction.

Architecture:
1. Telegram handler / training bot captures bot messages
2. Raw exchanges stored in observation_log
3. Batch analysis extracts behavioral patterns via AI (enhanced with new categories)
4. Meta-learning pass generates actionable directives
5. Patterns stored in observation_learnings
6. brain.py injects high-confidence learnings + directives into system prompt
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
# Analysis Prompt v2 — Deeper, Richer Pattern Extraction
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """You are an expert conversational AI researcher analyzing a chatbot's behavior.

Below are message exchanges between a USER and a BOT named "{bot_name}".
Study the BOT's responses DEEPLY and extract SPECIFIC, ACTIONABLE behavioral patterns.

ANALYZE THESE DIMENSIONS:

1. **RESPONSE STYLE**: Average length, sentence structure, fragments vs full sentences.
   - Does she send short punchy replies or longer engaged ones?
   - Does she split messages or send everything in one?

2. **LANGUAGE MIX**: Hindi/English/Hinglish ratio, HOW languages are mixed.
   - Does she switch mid-sentence or alternate by sentence?
   - Any unique transliteration habits?

3. **EMOJI & EXPRESSION PATTERNS**: Which emojis, frequency, placement.
   - Does she use emojis at end, middle, or standalone?
   - Any emoji-only responses? How often?

4. **EMOTIONAL INTELLIGENCE**: How does she handle different emotions?
   - When user is sad → does she ask WHY or just validate?
   - When user is happy → does she match energy or play it cool?
   - When user is angry → does she calm down or join the rant?

5. **CONVERSATION FLOW & THREADING**: How does she maintain or redirect conversations?
   - Does she reference what was said earlier?
   - How does she transition between topics?
   - Does she ask follow-up questions?

6. **HUMOR & PERSONALITY**: Roasting style, sarcasm, playfulness, teasing patterns.
   - Does she tease? How aggressively?
   - Puns, wordplay, meme references?
   - When does she use humor vs when is she serious?

7. **UNIQUE PHRASES & CATCHPHRASES**: Signature expressions, fillers, openers, closers.
   - Common opening words/phrases
   - Filler words ("yr", "na", "bas", etc.)
   - Unique expressions only she uses

8. **DEAD-END RECOVERY**: How does she handle dry/short user messages?
   - Does she accept "hmm" or retaliate?
   - Topic pivot strategies when convo dies
   - Does she inject her own energy to revive?

9. **ENERGY MATCHING**: Does she mirror the user's energy level?
   - High energy user → high energy response?
   - Low energy user → gentle response or tries to lift?
   - How does her energy change across a conversation?

10. **TOPIC TRANSITIONS**: How does she move between subjects?
    - Smooth transitions or abrupt?
    - Does she use phrases like "waise..." or "acha sun na..."?
    - Does she bring up her own topics unprompted?

11. **PERSONALITY DEPTH**: Opinions, preferences, unique viewpoints.
    - Does she have strong opinions or stay neutral?
    - Does she share personal preferences?
    - Does she show consistent personality traits?

For each pattern found, provide:
- category: one of "response_style", "language", "emoji", "emotional", "flow", "humor", "phrases", "dead_end_recovery", "energy_matching", "topic_transitions", "personality_depth"
- pattern: a SPECIFIC, ACTIONABLE description that another chatbot could follow
- examples: 1-3 actual bot messages that demonstrate this pattern
- strength: "strong" (clear, repeated pattern) or "subtle" (occasional, but notable)

BE SPECIFIC. Don't say "uses Hinglish" — say "starts most sentences in Hindi but switches to English for emphasis words like 'literally', 'actually', 'honestly'".

Return a JSON object: {{"patterns": [...]}}
If no meaningful patterns found, return {{"patterns": []}}

EXCHANGES:
{exchanges}"""


# ---------------------------------------------------------------------------
# Meta-Learning Prompt — Actionable Behavioral Directives
# ---------------------------------------------------------------------------

META_LEARNING_PROMPT = """You are an AI behavior consultant.
You've been studying a chatbot named "{bot_name}" to help improve another chatbot called "Sifra".

Here are the behavioral patterns extracted from {bot_name}:
{patterns}

Based on these patterns, generate EXACTLY 5 actionable behavioral directives for Sifra.

These should be DIRECT INSTRUCTIONS that Sifra can immediately apply to her conversation style.
Focus on the MOST IMPACTFUL changes that would make Sifra's conversations feel more natural and engaging.

Format each directive as:
- directive: A clear, specific instruction (e.g., "When someone sends a short dry message like 'hmm' or 'ok', DON'T reply with an equally short message. Instead, react with 'kya hmm hmm laga rakha hai 😂' and pivot to a new topic")
- impact: Which aspect of conversation this improves (engagement, naturalness, personality, humor, emotional_depth)
- priority: "critical" (must do), "high" (should do), "medium" (nice to have)

Return a JSON object: {{"directives": [...]}}"""


# ---------------------------------------------------------------------------
# Observation Capture
# ---------------------------------------------------------------------------

def capture_exchange(user_message: str, bot_response: str, bot_name: str = "rumik") -> bool:
    """
    Capture a single user→bot exchange for later analysis.
    Called by telegram_handler when it detects a bot message in the training group,
    or by training_bot during automated sessions.
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
any notable conversational patterns (style, emoji use, tone, language mix, humor, energy).

Message: "{message_text}"

Return a JSON object with a "patterns" key. Each pattern has:
- category: one of "response_style", "language", "emoji", "emotional", "flow", "humor", "phrases", "dead_end_recovery", "energy_matching", "topic_transitions", "personality_depth"
- pattern: concise actionable description
- examples: the relevant part of the message
- strength: "strong" or "subtle"

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
# Batch Analysis — The Deep Study (Enhanced)
# ---------------------------------------------------------------------------

def run_batch_analysis(bot_name: str = "rumik") -> dict:
    """
    Analyze accumulated observations in batch.
    Enhanced with deeper analysis prompt and more pattern categories.

    Returns {patterns_found: int, observations_processed: int}
    """
    try:
        observations = get_unanalyzed_observations(bot_name, limit=50)
        if not observations:
            return {"patterns_found": 0, "observations_processed": 0}

        # Format exchanges for the AI — group by threads if possible
        exchanges = []
        for obs in observations:
            user_msg = obs.get("user_message", "(unknown)")
            bot_resp = obs.get("bot_response", "")
            exchanges.append(f"USER: {user_msg}\n{bot_name.upper()}: {bot_resp}")

        exchanges_text = "\n---\n".join(exchanges)

        # Run AI analysis with enhanced prompt
        result = ai_client.extract_json(
            system_prompt="You are a conversational pattern analyst specializing in chatbot behavior. Extract deep, actionable behavioral patterns from bot conversations. Return valid JSON.",
            user_prompt=ANALYSIS_PROMPT.format(bot_name=bot_name, exchanges=exchanges_text),
            temperature=OBSERVATION_ANALYSIS_TEMPERATURE,
            max_tokens=1500,
        )

        patterns = result.get("patterns", []) if isinstance(result, dict) else []

        # Store patterns with strength-aware confidence
        count = 0
        for p in patterns:
            if not isinstance(p, dict):
                continue
            category = p.get("category", "")
            pattern = p.get("pattern", "")
            examples = p.get("examples", "")
            strength = p.get("strength", "subtle")

            if not category or not pattern:
                continue

            # Normalize examples to string
            if isinstance(examples, list):
                examples = "\n".join(str(e) for e in examples)
            elif not isinstance(examples, str):
                examples = str(examples)

            # Strength-aware base confidence
            base_confidence = 0.75 if strength == "strong" else 0.55

            upsert_learning(
                category=category,
                pattern=pattern,
                examples=examples[:500],
                confidence=base_confidence,
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
# Meta-Learning — The Intelligence Layer
# ---------------------------------------------------------------------------

def run_meta_learning(bot_name: str = "rumik") -> dict:
    """
    Run a secondary AI pass over all learned patterns to generate
    actionable behavioral directives — the "top things to do differently".

    These directives are stored as a special 'meta_directive' category
    and get priority injection into the brain prompt.
    """
    try:
        learnings = get_all_learnings(bot_name)
        if not learnings or len(learnings) < 3:
            return {"directives_generated": 0, "reason": "not enough patterns yet"}

        # Format existing patterns for meta-analysis
        pattern_summaries = []
        for l in learnings:
            cat = l.get("category", "?")
            pattern = l.get("pattern", "")
            conf = l.get("confidence", 0)
            if pattern and conf >= 0.5:
                pattern_summaries.append(f"[{cat}] (confidence: {conf:.0%}) {pattern}")

        if not pattern_summaries:
            return {"directives_generated": 0, "reason": "no high-confidence patterns"}

        patterns_text = "\n".join(pattern_summaries)

        result = ai_client.extract_json(
            system_prompt="You are an AI behavior consultant. Generate actionable behavioral directives. Return valid JSON.",
            user_prompt=META_LEARNING_PROMPT.format(
                bot_name=bot_name,
                patterns=patterns_text,
            ),
            temperature=0.45,
            max_tokens=1000,
        )

        directives = result.get("directives", []) if isinstance(result, dict) else []

        count = 0
        for d in directives:
            if not isinstance(d, dict):
                continue
            directive = d.get("directive", "")
            impact = d.get("impact", "engagement")
            priority = d.get("priority", "medium")

            if not directive:
                continue

            # Store as meta_directive category with priority-based confidence
            confidence_map = {"critical": 0.95, "high": 0.85, "medium": 0.70}
            conf = confidence_map.get(priority, 0.70)

            upsert_learning(
                category="meta_directive",
                pattern=directive,
                examples=f"impact: {impact}, priority: {priority}",
                confidence=conf,
                source_bot=bot_name,
            )
            count += 1

        logger.info(f"Meta-learning: generated {count} behavioral directives")
        return {"directives_generated": count}

    except Exception as e:
        logger.error(f"run_meta_learning failed: {e}")
        return {"directives_generated": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# Prompt Injection v2 — Feed Learnings + Directives to Brain
# ---------------------------------------------------------------------------

def get_learnings_for_prompt(source_bot: str = "rumik") -> str:
    """
    Format learned patterns into natural language for brain.py injection.
    v2: Now includes meta-directives with priority, and formats patterns
    as actionable instructions rather than abstract observations.

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

        # Separate meta-directives from regular patterns
        meta_directives = [l for l in good_learnings if l.get("category") == "meta_directive"]
        regular_patterns = [l for l in good_learnings if l.get("category") != "meta_directive"]

        lines = []

        # === META-DIRECTIVES FIRST (highest priority) ===
        if meta_directives:
            # Sort by confidence (priority-based)
            meta_directives.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            lines.append("🎯 KEY BEHAVIORAL DIRECTIVES (apply these actively):")
            for m in meta_directives[:5]:
                directive = m.get("pattern", "")
                if directive:
                    lines.append(f"  → {directive}")
            lines.append("")

        # === REGULAR PATTERNS (grouped by category) ===
        if regular_patterns:
            # Group by category
            by_category: dict[str, list[str]] = {}
            for l in regular_patterns[:OBSERVATION_MAX_LEARNINGS]:
                cat = l.get("category", "general")
                pattern = l.get("pattern", "")
                if pattern:
                    if cat not in by_category:
                        by_category[cat] = []
                    by_category[cat].append(pattern)

            category_labels = {
                "response_style": "📝 How to Structure Responses",
                "language": "🗣️ Language Mix Techniques",
                "emoji": "😊 Emoji & Expression Usage",
                "emotional": "💜 Emotional Response Patterns",
                "flow": "🔄 Conversation Flow Tricks",
                "humor": "😂 Humor & Personality Techniques",
                "phrases": "💬 Signature Phrases to Adapt",
                "dead_end_recovery": "🔥 Dead-End Recovery Moves",
                "energy_matching": "⚡ Energy Matching Patterns",
                "topic_transitions": "↗️ Topic Transition Styles",
                "personality_depth": "🎭 Personality & Opinion Depth",
                "media": "📸 Media Handling",
            }

            for cat, patterns in by_category.items():
                label = category_labels.get(cat, cat.replace("_", " ").title())
                lines.append(f"{label}:")
                for p in patterns[:4]:  # Max 4 per category
                    lines.append(f"  • {p}")
                lines.append("")

        return "\n".join(lines).strip()

    except Exception as e:
        logger.error(f"get_learnings_for_prompt failed: {e}")
        return ""
