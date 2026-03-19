"""
SIFRA:MIND — Context Engine.
Replaces the old peek_context.py keyword system.
Combines time awareness, AI sentiment, energy detection, and personality mode selection.
"""

import re
import logging
from datetime import datetime, timezone, timedelta

from config import TIMEZONE_OFFSET, USER_LOCATION
from sentiment import Sentiment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Time Awareness
# ---------------------------------------------------------------------------

def _get_local_time() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=TIMEZONE_OFFSET)


def _get_time_label(hour: int) -> str:
    if 0 <= hour < 4 or hour >= 23:
        return "late_night"
    if 4 <= hour < 10:
        return "morning"
    if 10 <= hour < 16:
        return "afternoon"
    if 16 <= hour < 20:
        return "evening"
    return "late_evening"


# ---------------------------------------------------------------------------
# Personality Mode Selection — the brain of context
# ---------------------------------------------------------------------------

def _select_personality_mode(
    time_label: str,
    sentiment: Sentiment,
    message: str,
    gap_minutes: int | None,
) -> str:
    """
    Select the personality mode based on all context signals.
    Modes: normal, late_night, morning, grind, playful, quiet, vent, hyped
    """
    lower = message.lower()

    # Priority 1: Emotional states override everything
    if sentiment.emotion in ("sad", "lonely", "frustrated") and sentiment.intensity >= 6:
        return "vent"
    if sentiment.emotion in ("stressed", "anxious"):
        return "quiet"

    # Priority 2: Energy-based modes
    if sentiment.energy == "high" and sentiment.emotion in ("excited", "happy", "playful"):
        return "hyped"

    # Priority 3: Work detection
    work_keywords = {"project", "deadline", "assignment", "kaam", "work", "code",
                     "coding", "submit", "exam", "test", "study", "padhai",
                     "grind", "hustle", "build", "deploy", "bug", "fix"}
    work_hits = sum(1 for kw in work_keywords if kw in lower)
    if work_hits >= 2 or (work_hits >= 1 and sentiment.energy == "high"):
        return "grind"

    # Priority 4: Time-based defaults
    if time_label == "late_night":
        if sentiment.emotion in ("sad", "lonely", "nostalgic"):
            return "vent"
        return "late_night"
    if time_label == "morning":
        return "morning"

    # Priority 5: Bored / Playful
    if sentiment.emotion == "bored" or time_label in ("evening", "late_evening"):
        return "playful"

    # Priority 6: Low energy
    if sentiment.energy == "low":
        return "quiet"

    return "normal"


# ---------------------------------------------------------------------------
# Message Analysis — lightweight, no AI call needed
# ---------------------------------------------------------------------------

def _classify_length(text: str) -> str:
    words = len(text.split())
    if words <= 3:
        return "very_short"
    if words <= 8:
        return "short"
    if words <= 25:
        return "medium"
    return "long"


def _has_question(text: str) -> bool:
    return "?" in text or bool(re.search(
        r"\b(kya|kaise|kyun|why|how|what|when|where|who|bata|batao|kaun|kidhar|kab)\b",
        text, re.IGNORECASE
    ))


def _detect_typing_energy(text: str) -> str:
    """
    Detect energy from HOW the message is typed, not what it says.
    This supplements the AI sentiment analysis.
    """
    score = 0

    # Repeated letters: heyyy, hiiiii = high energy
    if re.search(r"(.)\1{2,}", text):
        score += 2
    # ALL CAPS
    if len(text) > 3 and text == text.upper() and text.strip().replace(" ", "").isalpha():
        score += 3
    # Multiple exclamation marks
    score += min(text.count("!"), 3)
    # Multiple question marks
    if text.count("?") >= 2:
        score += 1
    # Emojis
    if re.search(r"[😂🤣😭💀🔥❤️😍🥺😎🙏👀🫡😤🥳🎉✨💅]", text):
        score += 1
    # Very short dry response
    if len(text.split()) <= 2 and score == 0:
        score -= 2

    if score >= 3:
        return "high"
    if score <= -1:
        return "low"
    return "medium"


# ---------------------------------------------------------------------------
# Gap Detection
# ---------------------------------------------------------------------------

def _calculate_gap(last_message_timestamp: str | None) -> int | None:
    if not last_message_timestamp:
        return None
    try:
        last_ts = datetime.fromisoformat(last_message_timestamp.replace("Z", "+00:00"))
        gap = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
        return int(gap)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Conversation Dynamics — pace, phase, length suggestion
# ---------------------------------------------------------------------------

def _detect_conversation_pace(gap_minutes: int | None) -> str:
    """How fast is this conversation moving?"""
    if gap_minutes is None:
        return "returning"  # First message or no history
    if gap_minutes < 2:
        return "rapid"       # Back-and-forth texting
    if gap_minutes < 15:
        return "flowing"     # Normal conversation pace
    if gap_minutes < 60:
        return "slow"        # Occasional check-ins
    return "returning"       # Coming back after a long gap


def _detect_conversation_phase(gap_minutes: int | None, message_length: str, msg_count_in_session: int) -> str:
    """What phase is this conversation in?"""
    if gap_minutes is None or gap_minutes > 60:
        return "opening"           # Starting fresh
    if msg_count_in_session < 3:
        return "opening"           # Still warming up
    if message_length in ("very_short", "short") and gap_minutes > 10:
        return "winding_down"      # Conversation dying out
    return "mid_flow"              # In the groove


def _suggest_response_length(message_length: str, pace: str, energy: str, phase: str) -> str:
    """
    Suggest how long Sifra's response should be.
    This is a HINT, not a hard rule.
    """
    # If the user gives a one word reply and we are winding down, it's fine to reply short.
    # But if it's mid_flow or opening, don't just say 'hmm'.
    if message_length == "very_short" and phase == "winding_down":
        return "one_word"
    
    if message_length in ("very_short", "short") and phase != "winding_down":
        # User is being brief, Sifra should try to carry the conversation by giving medium responses 
        # or asking a question to spark things up.
        return "medium"
    
    # Rapid pace = keep it snappy but don't strictly require 'short'. 
    if pace == "rapid" and energy != "high":
        return "short"
    
    # Long emotional input = longer response
    if message_length == "long" and energy != "low":
        return "long"
    
    # Default is medium / chatty
    return "medium"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_context(
    message: str,
    sentiment: Sentiment,
    last_message_timestamp: str | None = None,
    recent_message_count: int = 0,
) -> dict:
    """
    Build the complete context object for this interaction.
    Combines time, sentiment, typing energy, conversation dynamics, and personality mode.

    Returns a context dict used by brain.py to construct the prompt.
    """
    local_time = _get_local_time()
    hour = local_time.hour
    time_label = _get_time_label(hour)
    day = local_time.strftime("%A")
    gap_minutes = _calculate_gap(last_message_timestamp)

    # Merge AI sentiment energy with typing energy
    typing_energy = _detect_typing_energy(message)
    # Typing energy overrides sentiment energy if it's stronger signal
    final_energy = sentiment.energy
    if typing_energy == "high" and sentiment.energy != "low":
        final_energy = "high"
    elif typing_energy == "low" and sentiment.energy != "high":
        final_energy = "low"

    effective_sentiment = Sentiment(
        emotion=sentiment.emotion,
        intensity=sentiment.intensity,
        energy=final_energy,
        sarcasm=sentiment.sarcasm,
        urgency=sentiment.urgency,
    )

    personality_mode = _select_personality_mode(
        time_label, effective_sentiment, message, gap_minutes
    )

    # Conversation dynamics
    message_length = _classify_length(message)
    pace = _detect_conversation_pace(gap_minutes)
    phase = _detect_conversation_phase(gap_minutes, message_length, recent_message_count)
    length_hint = _suggest_response_length(message_length, pace, final_energy, phase)

    return {
        "hour": hour,
        "time_label": time_label,
        "day": day,
        "message_length": message_length,
        "has_question": _has_question(message),
        "sentiment": effective_sentiment,
        "personality_mode": personality_mode,
        "gap_minutes": gap_minutes,
        "location": USER_LOCATION,
        "typing_energy": typing_energy,
        "conversation_pace": pace,
        "conversation_phase": phase,
        "response_length_hint": length_hint,
    }
