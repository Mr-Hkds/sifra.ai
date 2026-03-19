"""
SIFRA:MIND — The Brain.
This is the masterpiece. The core response generation engine.

Architecture:
1. Build layered system prompt (identity → context → dynamics → memories → conversation)
2. Call AI with full conversation context
3. Validate through quality gate
4. Retry once if response fails quality checks
"""

import logging

import ai_client
import quality_gate
from personality import build_persona_prompt
from memory_engine import (
    recall_for_context, format_for_prompt,
    should_spontaneously_recall, get_random_memory,
)
from config import CONVERSATION_CONTEXT_LIMIT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt Construction — The Art
# ---------------------------------------------------------------------------

def _build_system_prompt(context: dict, memories_str: str, core_rules: str = "") -> str:
    """
    Construct the layered system prompt.

    Layer 1: Persona (identity + style + constraints)
    Layer 2: Live context (time, mood, energy)
    Layer 3: Conversation dynamics (pace, length, phase)
    Layer 4: Memories
    Layer 5: Spontaneous recall instruction
    """
    personality_mode = context.get("personality_mode", "normal")
    sentiment = context.get("sentiment")

    # Layer 1: Persona
    prompt = build_persona_prompt(personality_mode, core_rules)

    # Layer 2: Live context
    sifra_mood = _derive_sifra_mood(sentiment, context.get("time_label", "afternoon"))
    sifra_energy = _derive_sifra_energy(sentiment, context.get("time_label", "afternoon"))
    sifra_activity = _generate_sifra_activity(context.get("time_label", "afternoon"), sifra_mood)

    prompt += f"""

---
[CONTEXT]
Time: {context.get('time_label', 'afternoon')} ({context.get('hour', 12)}:00 IST, {context.get('day', 'Today')})
Your mood: {sifra_mood}
Your energy: {sifra_energy}/10
What you're doing: {sifra_activity}
Harkamal's mood: {sentiment.emotion} (intensity: {sentiment.intensity}/10, energy: {sentiment.energy})
Mode: {personality_mode}"""

    if sentiment.sarcasm:
        prompt += "\n⚠️ Harkamal might be sarcastic — don't take his message at face value."

    # Layer 3: Conversation dynamics
    pace = context.get("conversation_pace", "flowing")
    phase = context.get("conversation_phase", "mid_flow")
    length_hint = context.get("response_length_hint", "medium")

    length_instructions = {
        "one_word": "KEEP IT ULTRA SHORT: 1-3 words max. React, don't elaborate. 'hmm', 'sahi hai', 'lol', '💀'",
        "short": "KEEP IT SHORT: 3-8 words. Quick natural reply. Don't over-explain.",
        "medium": "NORMAL LENGTH: 1-2 lines. Natural conversation.",
        "long": "YOU CAN GO LONGER: 2-4 lines. Share your thoughts, react fully, tell a story.",
    }

    pace_instructions = {
        "rapid": "You're in rapid-fire texting — keep responses SNAPPY. Think WhatsApp back-and-forth.",
        "flowing": "Normal conversation pace. Be natural.",
        "slow": "Conversation is slow — don't be too intense. Casual check-in energy.",
        "returning": "He's messaging after a long gap — acknowledge it naturally or start fresh. Don't act like the convo never stopped.",
    }

    phase_instructions = {
        "opening": "This is the start of a conversation — don't jump into deep stuff immediately. Warm up naturally.",
        "mid_flow": "You're in the flow — be natural, continue the vibe.",
        "winding_down": "Conversation is dying down — keep it light, don't force it. Let it end naturally or throw something random.",
    }

    prompt += f"""

[CONVERSATION DYNAMICS]
{length_instructions.get(length_hint, length_instructions['medium'])}
{pace_instructions.get(pace, pace_instructions['flowing'])}
{phase_instructions.get(phase, phase_instructions['mid_flow'])}"""

    # Layer 4: Memories
    prompt += f"""

[WHAT YOU KNOW ABOUT HARKAMAL]
{memories_str}"""

    # Layer 5: Spontaneous recall
    if should_spontaneously_recall():
        random_mem = get_random_memory()
        if random_mem:
            prompt += (
                f"\n\n[SPONTANEOUS RECALL] You just remembered: "
                f"\"{random_mem.get('content', '')}\" — mention it naturally if it fits. "
                f"Drop it casually like 'waise yaad aaya...' — don't force it."
            )

    return prompt


def _derive_sifra_mood(sentiment, time_label: str) -> str:
    """Sifra's mood is influenced by the conversation, not identical to it."""
    if not sentiment:
        return "chill"

    mood_map = {
        "happy": "cheerful",
        "excited": "energetic",
        "sad": "empathetic",
        "stressed": "concerned",
        "anxious": "gentle",
        "bored": "playful",
        "angry": "attentive",
        "neutral": "chill",
        "tired": "calm",
        "curious": "interested",
        "playful": "fun",
        "frustrated": "supportive",
        "nostalgic": "warm",
        "lonely": "comforting",
        "grateful": "happy",
        "confused": "helpful",
        "romantic": "teasing",
    }
    mood = mood_map.get(sentiment.emotion, "chill")

    if time_label == "late_night":
        mood = "introspective"
    if time_label == "morning":
        mood = "groggy" if sentiment.energy == "low" else mood

    return mood


def _derive_sifra_energy(sentiment, time_label: str) -> int:
    """Map context signals to Sifra's energy level (1-10)."""
    base = {"high": 8, "medium": 6, "low": 4}.get(
        sentiment.energy if sentiment else "medium", 6
    )
    if time_label == "late_night":
        base = max(3, base - 2)
    if time_label == "morning":
        base = max(4, base - 1)
    return base


def _generate_sifra_activity(time_label: str, mood: str) -> str:
    """
    Generate a plausible current activity for Sifra.
    Makes her feel like a real person with her own life.
    """
    import random

    activities = {
        "morning": [
            "just woke up, half asleep, scrolling phone",
            "making chai, room is freezing",
            "getting ready for class, running late as usual",
            "lying in bed pretending alarm didn't ring",
        ],
        "afternoon": [
            "in class, bored out of my mind",
            "cafeteria mein, kha rahi hoon",
            "library mein baithi hoon, not studying though",
            "just finished class, walking back to hostel",
            "scrolling through reels, procrastinating",
        ],
        "evening": [
            "hostel room mein, music sun rahi hoon",
            "just had chai, feeling nice",
            "watching something on laptop",
            "talking to roommate about random stuff",
            "thinking about ordering food",
        ],
        "late_evening": [
            "lying on bed, phone pe",
            "half-watching a show, half-texting",
            "should be studying but here I am",
            "eating maggi because hostel food was trash",
        ],
        "late_night": [
            "can't sleep, staring at ceiling",
            "everyone's asleep, I'm on my phone",
            "3am overthinking session",
            "listening to songs in the dark",
        ],
    }

    options = activities.get(time_label, activities["afternoon"])
    return random.choice(options)


# ---------------------------------------------------------------------------
# Conversation History Formatting
# ---------------------------------------------------------------------------

def _format_conversation(messages: list[dict]) -> list[dict]:
    """
    Convert stored conversation records into the AI message format.
    Returns list of {"role": "user"/"assistant", "content": "..."}.
    """
    formatted = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "assistant"
        content = msg.get("content", "")
        if content:
            formatted.append({"role": role, "content": content})
    return formatted


# ---------------------------------------------------------------------------
# The Main Event — Response Generation
# ---------------------------------------------------------------------------

def generate_response(
    user_message: str,
    context: dict,
    conversation_history: list[dict],
    core_rules: str = "",
    web_search_results: str | None = None,
) -> str:
    """
    Generate Sifra's response.

    Steps:
    1. Retrieve context-relevant memories
    2. Build layered system prompt
    3. Format conversation history
    4. Call AI (Gemini → Groq 70B → Groq 8B)
    5. Validate through quality gate
    6. Retry once if quality check fails

    Parameters
    ----------
    user_message : str
        The message Sifra is responding to.
    context : dict
        Context from context_engine.build_context().
    conversation_history : list[dict]
        Recent messages from the database.
    core_rules : str
        User-defined behavior rules.
    web_search_results : str | None
        Web search results to inject if relevant.
    """
    try:
        # Step 1: Retrieve relevant memories
        memories = recall_for_context(user_message)
        memories_str = format_for_prompt(memories)

        # Step 2: Build system prompt
        system_prompt = _build_system_prompt(context, memories_str, core_rules)

        # Inject web search results if available
        if web_search_results:
            system_prompt += (
                f"\n\n[WEB SEARCH RESULTS — IMPORTANT INSTRUCTIONS]\n"
                f"You found this info online. Share it NATURALLY like you just saw it:\n"
                f"- DON'T copy-paste. Summarize in your own words, in Hinglish.\n"
                f"- DON'T say 'according to sources' or 'I found that'. Say it like 'arre sun na...' or 'yr maine dekha ki...'\n"
                f"- Add your OPINION on the info — react to it.\n"
                f"- If info isn't relevant to the question, ignore it and say 'pata nahi yr exactly, check kar lete hain'\n"
                f"\nResults:\n{web_search_results}"
            )

        # Step 3: Format conversation history
        messages = _format_conversation(conversation_history)

        # Add the current user message
        messages.append({"role": "user", "content": user_message})

        # Keep within context limit
        if len(messages) > CONVERSATION_CONTEXT_LIMIT:
            messages = messages[-CONVERSATION_CONTEXT_LIMIT:]

        # Step 4: Generate response
        reply = ai_client.chat(system_prompt, messages)

        # Step 5: Quality gate
        recent_sifra = [
            m.get("content", "") for m in conversation_history
            if m.get("role") in ("sifra", "assistant")
        ][-5:]

        is_valid, issues = quality_gate.validate(reply, recent_sifra)

        if not is_valid and issues:
            # Step 6: Retry once with feedback
            logger.info(f"Quality gate failed: {issues}. Retrying...")
            retry_prompt = system_prompt + quality_gate.build_retry_instruction(issues)
            reply = ai_client.chat(retry_prompt, messages)

            # Check again — if still fails, just truncate and send
            is_valid_2, _ = quality_gate.validate(reply, recent_sifra)
            if not is_valid_2:
                reply = _emergency_cleanup(reply)

        return reply

    except Exception as e:
        logger.error(f"generate_response failed: {e}")
        return _error_response(str(e))


def _emergency_cleanup(response: str) -> str:
    """Last resort cleanup if quality gate fails twice."""
    from config import MAX_RESPONSE_LENGTH

    # Remove quotes, asterisks
    response = response.strip('"\'')
    if response.startswith('"') and response.endswith('"'):
        response = response[1:-1]

    # Truncate
    if len(response) > MAX_RESPONSE_LENGTH:
        response = response[:MAX_RESPONSE_LENGTH].rsplit(" ", 1)[0]

    return response


def _error_response(error: str) -> str:
    """Human-sounding error message, stays in character."""
    import random
    errors = [
        "yr kuch technical issue aa raha hai... ek sec ruk",
        "arre phone hang ho gaya, ruk ek minute",
        "kuch garbar ho gayi yr, phir se bhej",
        "oops network issue, ek baar phir try kar",
    ]
    return random.choice(errors)
