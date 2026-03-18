"""
Peek Context System — reads signals from messages and environment
to determine Sifra's personality mode for the current interaction.
"""

import re
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Keyword banks for signal detection
# ---------------------------------------------------------------------------

STRESS_KEYWORDS = [
    "stressed", "stress", "tension", "anxious", "anxiety", "panic",
    "overwhelmed", "frustrated", "frustrate", "irritated",
    "thak gaya", "thak gayi", "bahut ho gaya", "nahi hota",
    "pagal", "dimag kharab", "pareshan", "tension", "barbad",
]

LOW_ENERGY_KEYWORDS = [
    "tired", "exhausted", "sleepy", "neend", "thak", "lazy",
    "sust", "bore", "bored", "boring", "kuch nahi", "bakwaas",
    "meh", "blah", "ugh", "urgh",
]

HIGH_ENERGY_KEYWORDS = [
    "excited", "amazing", "awesome", "great", "fantastic", "let's go",
    "maza", "bahut maza", "fire", "lit", "insane", "crazy good",
    "kamaal", "zabardast", "jhakaas", "superb", "pumped",
]

WORK_KEYWORDS = [
    "project", "deadline", "assignment", "kaam", "work", "code",
    "coding", "submit", "exam", "test", "study", "padhai",
    "grind", "hustle", "build", "deploy", "bug", "fix",
]

BORED_KEYWORDS = [
    "bored", "bore", "boring", "kuch nahi", "nothing",
    "timepass", "tp", "bakwaas", "vella", "free", "kya karu",
]


def _get_time_label(hour: int) -> str:
    """Map hour to a time-of-day label."""
    if 23 <= hour or hour < 4:
        return "late_night"
    elif 4 <= hour < 10:
        return "morning"
    elif 10 <= hour < 16:
        return "afternoon"
    elif 16 <= hour < 20:
        return "evening"
    else:
        return "late_evening"


def _classify_message_length(text: str) -> str:
    word_count = len(text.split())
    if word_count <= 5:
        return "short"
    elif word_count <= 25:
        return "medium"
    return "long"


def _detect_energy(text: str) -> str:
    """Detect energy signal from message text."""
    lower = text.lower()
    low_hits = sum(1 for kw in LOW_ENERGY_KEYWORDS if kw in lower)
    high_hits = sum(1 for kw in HIGH_ENERGY_KEYWORDS if kw in lower)
    if low_hits > high_hits:
        return "low"
    if high_hits > low_hits:
        return "high"
    return "neutral"


def _detect_mood(text: str) -> str:
    """Simple keyword-based mood signal detection."""
    lower = text.lower()
    stress_hits = sum(1 for kw in STRESS_KEYWORDS if kw in lower)
    bored_hits = sum(1 for kw in BORED_KEYWORDS if kw in lower)
    happy_hits = sum(1 for kw in HIGH_ENERGY_KEYWORDS if kw in lower)
    sad_hits = sum(1 for kw in LOW_ENERGY_KEYWORDS if kw in lower)

    scores = {
        "stressed": stress_hits,
        "bored": bored_hits,
        "happy": happy_hits,
        "low": sad_hits,
    }
    top = max(scores, key=scores.get)  # type: ignore[arg-type]
    if scores[top] == 0:
        return "neutral"
    return top


def _has_question(text: str) -> bool:
    return "?" in text or bool(re.search(r"\b(kya|kaise|kyun|why|how|what|when|where|who|bata|batao)\b", text, re.IGNORECASE))


def _detect_personality_mode(time_label: str, mood_signal: str, energy_signal: str, text: str) -> str:
    """
    Map context signals → personality mode.
    Modes: normal, late_night, grind, playful, quiet, stressed
    """
    lower = text.lower()
    work_hits = sum(1 for kw in WORK_KEYWORDS if kw in lower)

    if mood_signal == "stressed":
        return "quiet"
    if time_label == "late_night":
        return "late_night"
    if work_hits >= 2 or (energy_signal == "high" and work_hits >= 1):
        return "grind"
    if mood_signal == "bored" or (time_label in ("evening", "late_evening") and mood_signal != "stressed"):
        return "playful"
    if energy_signal == "low":
        return "quiet"
    return "normal"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_context(message_text: str, last_message_timestamp: str | None = None) -> dict:
    """
    Build the full context object for the Peek system.

    Parameters
    ----------
    message_text : str
        The user's current message.
    last_message_timestamp : str | None
        ISO timestamp of the user's previous message (for gap detection).

    Returns
    -------
    dict with keys: time, time_label, day, message_length, has_question,
                    energy_signal, mood_signal, personality_mode, gap_minutes
    """
    now = datetime.now(timezone.utc)
    hour = now.hour
    time_label = _get_time_label(hour)
    day = now.strftime("%A")
    msg_len = _classify_message_length(message_text)
    question = _has_question(message_text)
    energy = _detect_energy(message_text)
    mood = _detect_mood(message_text)

    # Gap since last message
    gap_minutes = None
    if last_message_timestamp:
        try:
            last_ts = datetime.fromisoformat(last_message_timestamp.replace("Z", "+00:00"))
            gap_minutes = int((now - last_ts).total_seconds() / 60)
        except Exception:
            pass

    personality_mode = _detect_personality_mode(time_label, mood, energy, message_text)

    return {
        "time": hour,
        "time_label": time_label,
        "day": day,
        "message_length": msg_len,
        "has_question": question,
        "energy_signal": energy,
        "mood_signal": mood,
        "personality_mode": personality_mode,
        "gap_minutes": gap_minutes,
    }
