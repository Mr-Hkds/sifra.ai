"""
Peek Context System — reads signals from messages and environment
to determine Sifra's personality mode for the current interaction.
"""

import os
import re
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default to IST (UTC+5:30) if not specified
TIMEZONE_OFFSET = float(os.environ.get("TIMEZONE_OFFSET", 5.5))
USER_LOCATION = os.environ.get("USER_LOCATION", "Delhi, India")


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
    """Detect energy signal from message text AND typing style."""
    lower = text.lower()
    low_hits = sum(1 for kw in LOW_ENERGY_KEYWORDS if kw in lower)
    high_hits = sum(1 for kw in HIGH_ENERGY_KEYWORDS if kw in lower)

    # Typing style energy detection
    # Repeated letters (heyyy, hiiiii, yaaaar) = HIGH energy
    if re.search(r"(.)\1{2,}", text):
        high_hits += 2
    # ALL CAPS message = HIGH energy / excitement
    if len(text) > 3 and text.upper() == text and text.strip().isalpha():
        high_hits += 2
    # Lots of exclamation marks = excitement
    if text.count("!") >= 2:
        high_hits += 1
    # Multiple question marks = curious/excited
    if text.count("?") >= 2:
        high_hits += 1
    # Emojis/emoticons patterns = engaged
    if re.search(r"[😂🤣😭💀🔥❤️😍🥺😎🙏👀🫡]", text):
        high_hits += 1
    # Very short dry responses = low energy
    if len(text.split()) <= 2 and not re.search(r"(.)\1{2,}", text) and text.count("!") == 0:
        low_hits += 1

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

    # Vent detection — long emotional messages
    vent_keywords = ["i feel", "mujhe lagta", "samajh nahi", "kya karu", "bahut bura",
                     "dil", "akela", "lonely", "miss", "cry", "ro", "hurt", "pain", "dard"]
    vent_hits = sum(1 for kw in vent_keywords if kw in lower)

    scores = {
        "stressed": stress_hits,
        "bored": bored_hits,
        "happy": happy_hits,
        "low": sad_hits,
        "venting": vent_hits,
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
    Modes: normal, late_night, grind, playful, quiet, vent, hyped
    """
    lower = text.lower()
    work_hits = sum(1 for kw in WORK_KEYWORDS if kw in lower)

    # Vent mode — emotional/sad messages especially at night
    if mood_signal == "venting":
        return "vent"
    if mood_signal == "stressed":
        return "quiet"
    # Hyped mode — user is typing with HIGH energy (heyyy, !!, caps)
    if energy_signal == "high" and work_hits == 0:
        return "hyped"
    if time_label == "late_night":
        if mood_signal in ("low", "venting"):
            return "vent"
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

    Returns
    -------
    dict with keys: time, time_label, day, message_length, has_question,
                    energy_signal, mood_signal, personality_mode, gap_minutes, location
    """
    # Calculate local time based on offset
    utc_now = datetime.now(timezone.utc)
    local_now = utc_now + timedelta(hours=TIMEZONE_OFFSET)
    
    hour = local_now.hour
    time_label = _get_time_label(hour)
    day = local_now.strftime("%A")
    msg_len = _classify_message_length(message_text)
    question = _has_question(message_text)
    energy = _detect_energy(message_text)
    mood = _detect_mood(message_text)

    # Gap since last message
    gap_minutes = None
    if last_message_timestamp:
        try:
            last_ts = datetime.fromisoformat(last_message_timestamp.replace("Z", "+00:00"))
            gap_minutes = int((utc_now - last_ts).total_seconds() / 60)
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
        "location": USER_LOCATION,
    }
