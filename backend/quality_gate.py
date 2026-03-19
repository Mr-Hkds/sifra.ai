"""
SIFRA:MIND — Response Quality Gate.
Catches AI slop before it reaches the user.
If a response fails checks, provides actionable feedback for regeneration.
"""

import re
import logging

from config import AI_SLOP_PHRASES, MAX_RESPONSE_LENGTH, MIN_RESPONSE_LENGTH

logger = logging.getLogger(__name__)


def validate(response: str, recent_sifra_messages: list[str] | None = None) -> tuple[bool, list[str]]:
    """
    Validate a generated response before sending.

    Returns
    -------
    (is_valid, issues) — is_valid is True if response passes all checks.
    issues is a list of strings describing what went wrong (empty if valid).
    """
    issues = []

    # 1. Empty or too short
    if not response or len(response.strip()) < MIN_RESPONSE_LENGTH:
        issues.append("Response is empty or too short")
        return False, issues

    # 2. Too long
    if len(response) > MAX_RESPONSE_LENGTH:
        issues.append(f"Response is too long ({len(response)} chars). Keep it under {MAX_RESPONSE_LENGTH}")

    lower = response.lower()

    # 3. AI slop phrases
    found_slop = [phrase for phrase in AI_SLOP_PHRASES if phrase in lower]
    if found_slop:
        issues.append(f"Contains AI-ism phrases: {', '.join(found_slop[:3])}")

    # 4. Meta-commentary / breaking character
    if re.search(r"\*[^*]+\*", response):  # *actions in asterisks*
        issues.append("Contains asterisk actions (*action*) — Sifra doesn't do that")
    if re.search(r'^".*"$', response.strip()):  # Entire response in quotes
        issues.append("Response is wrapped in quotes — remove them")
    if re.search(r"\(.*\)", response) and len(response) < 100:  # (parenthetical meta)
        # Only flag short messages with parentheses — longer ones might have legitimate parens
        issues.append("Contains parenthetical meta-commentary")

    # 5. Formal English (not Hinglish)
    formal_markers = [
        "furthermore", "however", "additionally", "therefore",
        "in conclusion", "it is important", "please note",
        "i would like to", "i would suggest", "it seems that",
    ]
    found_formal = [m for m in formal_markers if m in lower]
    if found_formal:
        issues.append(f"Too formal for Sifra: {', '.join(found_formal[:2])}")

    # 6. Repetition with recent messages
    if recent_sifra_messages:
        for prev in recent_sifra_messages[-5:]:
            if not prev:
                continue
            prev_words = set(prev.lower().split())
            resp_words = set(lower.split())
            if prev_words and resp_words:
                overlap = len(prev_words & resp_words) / max(len(resp_words), 1)
                if overlap > 0.7 and len(resp_words) > 4:
                    issues.append("Too similar to a recent Sifra message — vary the response")
                    break

    # 7. Excessive emoji
    emoji_count = len(re.findall(r"[\U0001F600-\U0001F9FF\U00002702-\U000027B0\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]", response))
    if emoji_count > 4:
        issues.append(f"Too many emojis ({emoji_count}) — Sifra uses them sparingly")

    return len(issues) == 0, issues


def build_retry_instruction(issues: list[str]) -> str:
    """
    Build a feedback string to inject when retrying a failed response.
    This goes into the system prompt to guide the regeneration.
    """
    feedback = "\n\nYOUR PREVIOUS RESPONSE WAS REJECTED. Fix these issues:\n"
    for i, issue in enumerate(issues, 1):
        feedback += f"{i}. {issue}\n"
    feedback += "\nGenerate a new response that avoids ALL of the above problems."
    return feedback
