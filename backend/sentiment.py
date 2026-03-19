"""
SIFRA:MIND — AI-Powered Sentiment Analysis.
Replaces the old keyword-matching system with actual AI understanding.
Uses Groq 8B for speed — sentiment detection needs to be fast, not deep.
"""

import logging
from dataclasses import dataclass

import ai_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentiment Data Structure
# ---------------------------------------------------------------------------

VALID_EMOTIONS = {
    "happy", "sad", "stressed", "anxious", "bored", "excited",
    "angry", "neutral", "tired", "curious", "playful", "frustrated",
    "nostalgic", "lonely", "grateful", "confused", "romantic",
}


@dataclass
class Sentiment:
    """Rich sentiment analysis result."""
    emotion: str        # Primary emotion
    intensity: int      # 1-10 scale
    energy: str         # "low", "medium", "high"
    sarcasm: bool       # Is the message sarcastic?
    urgency: str        # "casual", "important", "urgent"

    @classmethod
    def neutral(cls) -> "Sentiment":
        return cls(emotion="neutral", intensity=5, energy="medium", sarcasm=False, urgency="casual")


# ---------------------------------------------------------------------------
# The One Function That Matters
# ---------------------------------------------------------------------------

SENTIMENT_PROMPT = """Analyze this message and return EXACTLY this format (one value per line):
emotion: [one word from: happy, sad, stressed, anxious, bored, excited, angry, neutral, tired, curious, playful, frustrated, nostalgic, lonely, grateful, confused, romantic]
intensity: [1-10]
energy: [low/medium/high]
sarcasm: [true/false]
urgency: [casual/important/urgent]

Context of recent conversation:
{context}

Message to analyze:
{message}"""


def analyze(message: str, recent_context: str = "") -> Sentiment:
    """
    Analyze the sentiment of a message using AI.
    Fast call — uses Groq 8B for speed over depth.
    Returns a Sentiment object with emotion, intensity, energy, sarcasm, urgency.
    """
    try:
        raw = ai_client.fast(
            system_prompt="You are a sentiment analysis system. Return ONLY the requested format. No explanations.",
            user_prompt=SENTIMENT_PROMPT.format(message=message, context=recent_context or "(no context)"),
            max_tokens=80,
        )

        if not raw:
            return Sentiment.neutral()

        return _parse_sentiment(raw)

    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        return Sentiment.neutral()


def _parse_sentiment(raw: str) -> Sentiment:
    """Parse the structured sentiment response into a Sentiment object."""
    lines = raw.strip().lower().split("\n")
    data = {}
    for line in lines:
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()

    emotion = data.get("emotion", "neutral")
    if emotion not in VALID_EMOTIONS:
        emotion = "neutral"

    try:
        intensity = max(1, min(10, int(data.get("intensity", "5"))))
    except (ValueError, TypeError):
        intensity = 5

    energy = data.get("energy", "medium")
    if energy not in ("low", "medium", "high"):
        energy = "medium"

    sarcasm = data.get("sarcasm", "false") == "true"

    urgency = data.get("urgency", "casual")
    if urgency not in ("casual", "important", "urgent"):
        urgency = "casual"

    return Sentiment(
        emotion=emotion,
        intensity=intensity,
        energy=energy,
        sarcasm=sarcasm,
        urgency=urgency,
    )
