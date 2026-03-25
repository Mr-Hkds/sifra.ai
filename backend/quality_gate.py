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

    # 8. Structural repetition — don't start messages the same way
    if recent_sifra_messages and len(recent_sifra_messages) >= 2:
        resp_opener = response.strip().split()[0].lower() if response.strip() else ""
        if resp_opener:
            recent_openers = [
                msg.strip().split()[0].lower()
                for msg in recent_sifra_messages[-3:]
                if msg and msg.strip()
            ]
            # If last 2+ messages started with the same word, reject
            same_opener_count = sum(1 for op in recent_openers if op == resp_opener)
            if same_opener_count >= 2:
                issues.append(
                    f"Starts with '{resp_opener}' again — vary the opening. "
                    f"Try starting with actual content, a reaction, or a question instead"
                )

    # 9. Length appropriateness — don't write paragraphs for short messages
    # This is checked by the caller who can pass user_message_length

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


# ---------------------------------------------------------------------------
# Humanize — Post-processing rewriter
# Catches AI patterns that slip through the quality gate and fixes them
# ---------------------------------------------------------------------------

# Patterns to strip entirely (these add nothing)
_STRIP_PATTERNS = [
    # Therapist/AI openers
    r"(?i)^(hey there[!,.]?\s*)",
    r"(?i)^(hi there[!,.]?\s*)",
    r"(?i)^(hello[!,.]?\s*)",
    r"(?i)^(hey[!]+\s+)",  # "Hey!!!" but not "hey "
    # Validation fluff
    r"(?i)(i (totally |completely )?understand (how you feel|what you('re| are) going through|that)[.,!]?\s*)",
    r"(?i)(that('s| is) (completely |totally )?(valid|understandable|okay|alright)[.,!]?\s*)",
    r"(?i)(i('m| am) here for you[.,!]?\s*)",
    r"(?i)(i hear you[.,!]?\s*)",
    r"(?i)(your feelings are valid[.,!]?\s*)",
    r"(?i)(it's okay to feel[^.]*[.,!]?\s*)",
    r"(?i)(remember,? you('re| are) not alone[^.]*[.,!]?\s*)",
    r"(?i)(don't hesitate to[^.]*[.,!]?\s*)",
    r"(?i)(feel free to[^.]*[.,!]?\s*)",
    # Formal closers
    r"(?i)(take care[!.]?\s*)$",
    r"(?i)(hope (this |that )helps[!.]?\s*)$",
    r"(?i)(let me know if[^.]*[!.]?\s*)$",
    # AI identity slips
    r"(?i)(as an ai[,.]?\s*)",
    r"(?i)(as a language model[,.]?\s*)",
    r"(?i)(i('m| am) (just )?a(n ai| bot| language model)[,.]?\s*)",
]

# Compiled for performance
_STRIP_COMPILED = [re.compile(p) for p in _STRIP_PATTERNS]

# Numbered list pattern (1. 2. 3. or 1) 2) 3))
_NUMBERED_LIST = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)

# Excessive punctuation
_EXCESSIVE_PUNCT = re.compile(r"([!?.]){3,}")
_EXCESSIVE_EMOJI = re.compile(r"([\U0001F600-\U0001F9FF\U00002702-\U000027B0\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF])\1{2,}")


def humanize(response: str) -> str:
    """
    Post-process a response to remove AI artifacts and enforce Sifra's voice.
    This runs AFTER quality gate validation, as a final cleanup.
    
    Returns the cleaned response.
    """
    if not response:
        return response

    text = response

    # 1. Strip AI/therapist patterns
    for pattern in _STRIP_COMPILED:
        text = pattern.sub("", text)

    # 2. Remove numbered lists → merge into natural text
    if _NUMBERED_LIST.search(text):
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            line = _NUMBERED_LIST.sub("", line).strip()
            if line:
                cleaned.append(line)
        text = " ".join(cleaned)

    # 3. Fix excessive punctuation (!!!! → !)
    text = _EXCESSIVE_PUNCT.sub(r"\1", text)

    # 4. Fix excessive repeated emojis
    text = _EXCESSIVE_EMOJI.sub(r"\1", text)

    # 5. Remove asterisk actions (*hugs* *smiles*)
    text = re.sub(r"\*[^*]+\*", "", text)

    # 6. Remove quotes around the entire response
    stripped = text.strip()
    if stripped.startswith('"') and stripped.endswith('"') and stripped.count('"') == 2:
        text = stripped[1:-1]

    # 7. Clean up extra whitespace from all the removals
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 8. Hard length cap — no one texts 500-word essays 
    # If over 400 chars, trim at last complete sentence within limit
    MAX_LEN = 400
    if len(text) > MAX_LEN:
        # Find last sentence boundary within limit
        trimmed = text[:MAX_LEN]
        # Try to cut at last sentence end
        last_period = max(trimmed.rfind('.'), trimmed.rfind('!'), trimmed.rfind('?'), trimmed.rfind('।'))
        if last_period > MAX_LEN // 2:
            text = trimmed[:last_period + 1]
        else:
            # No good sentence break — cut at last space
            last_space = trimmed.rfind(' ')
            if last_space > MAX_LEN // 2:
                text = trimmed[:last_space] + "..."
            else:
                text = trimmed + "..."

    # 9. If everything got stripped, return original (better than empty)
    if len(text.strip()) < 3:
        return response.strip()

    return text.strip()

