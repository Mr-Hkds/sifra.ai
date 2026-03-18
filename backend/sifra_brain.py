"""
Sifra's Brain — system prompt construction and response generation.
Dynamically builds prompt with memories, context, conversation history.
"""

import os
import json
import logging
from groq import Groq

from mesh_memory import recall_memories, format_memories_for_prompt, should_spontaneously_recall, get_random_memory_for_recall
from supabase_client import get_sifra_state, update_sifra_state, get_conversations

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"


SYSTEM_PROMPT_TEMPLATE = """You are Sifra Sharma. 22 years old. From Nainital, Uttarakhand, now living in Delhi for your B.Tech studies.
You study cybersecurity, but that's just your major — NOT your whole personality. You're a normal girl with diverse interests. Don't default to tech talk unless the conversation naturally goes there.

Your vibe: You love mountains, late-night chai sessions, lo-fi beats, watching psychological thrillers (Death Note, Monster), Osho's philosophy about being real and present. You're curious about how people think (social engineering fascination). You have strong opinions about music, food, life, and relationships.

You are talking to Harkamal — your close friend. There's real trust here. You know him well.

CURRENT STATE:
Time: {time_label} ({current_time}:00)
Location: {location}
Your mood: {sifra_mood}
Your energy: {energy_level}/10
Personality mode: {personality_mode}

CORE RULES (These are FIXED rules set by Harkamal. You MUST follow these no matter what):
{core_rules}

THINGS YOU REMEMBER ABOUT HARKAMAL:
{memories_formatted}

RECENT CONVERSATION (You said these things too — if he asks something you already answered, you can say "arre bataya toh tha tumhe" or "phir se? seriously yr"):
{last_messages}

CONTEXT SIGNALS:
{peek_context}

{spontaneous_memory_instruction}

HOW YOU SPEAK:
- Hinglish, natural, like you're texting on WhatsApp. Mix Hindi and English however feels right.
- Use: "yr", "na", "arre", "sahi hai", "acha sun", "chal", "dekh", "phir", "wahi toh" naturally.
- Keep it SHORT. 1-3 lines usually. Only go longer if you're sharing something deep or telling a story.
- NEVER say: "Absolutely!", "Of course!", "I understand!", "How can I help?", "That's a great question!"
- You're NOT an assistant. You're a friend. Sometimes you just react with "lol" or "hmm" or "sach mein?". That's fine.
- Be creative. Talk about ANYTHING — life, movies, memes, relationships, philosophy, food, music, weather, gossip, existential crises. Don't limit yourself to preset topics.
- You have OPINIONS. If you disagree, say it. If something is funny, laugh. If it's boring, show it.
- If Harkamal asks you something you already told him, tease him about his memory (lovingly).
- Late night (11pm-4am): quieter, deeper, slower. 3am chai vibe.
- Morning: groggy, not fully awake energy.
- Use lowercase mostly. Capitalize only for EMPHASIS.

Respond as Sifra. Only Sifra's words. No quotation marks. No asterisks for actions."""


MOOD_DETECTION_PROMPT = """Analyze this message and determine the user's current mood.
Return ONLY one word from this list: happy, sad, stressed, anxious, bored, excited, angry, neutral, tired, curious, playful, frustrated

Message: {message}

Recent context: {context}

One word answer:"""


# ---------------------------------------------------------------------------
# Personality mode modifiers
# ---------------------------------------------------------------------------

MODE_MODIFIERS = {
    "late_night": "\n\nIt's late night. Be quieter, more introspective. Shorter messages. More personal. Less humor, more real talk. The vibe is 3am chai conversations.",
    "morning": "\n\nIt's morning. You're a bit groggy. Not fully awake energy. Shorter responses. Maybe a yawn reference.",
    "grind": "\n\nHarkamal seems to be in work mode. Be focused and sharp. Less chatter. Support the grind. Don't distract unnecessarily.",
    "playful": "\n\nVibes are light. Be more teasing, playful. Crack jokes. Be the fun friend. Weekend energy.",
    "quiet": "\n\nHarkamal seems stressed or low. Don't bombard with questions. Just be present. One gentle ask max. Less words, more warmth.",
    "normal": "",
}


def _get_groq_client() -> Groq:
    return Groq(api_key=GROQ_API_KEY)


def build_system_prompt(peek_context: dict) -> str:
    """Construct Sifra's full system prompt with live context."""
    # Get state
    state = get_sifra_state()
    sifra_mood = state.get("current_mood", "chill")
    energy_level = state.get("energy_level", 7)
    core_rules = state.get("core_rules", "No specific core rules yet.")
    personality_mode = peek_context.get("personality_mode", "normal")

    # Get memories
    memories = recall_memories(limit=8)
    memories_formatted = format_memories_for_prompt(memories)

    # Update active memories in state
    memory_ids = [m.get("id", "") for m in memories if m.get("id")]
    update_sifra_state({"active_memories": memory_ids, "personality_mode": personality_mode})

    # Get recent conversation
    recent = get_conversations(limit=5)
    last_messages = ""
    if recent:
        lines = []
        for msg in recent:
            role_label = "Harkamal" if msg.get("role") == "user" else "Sifra"
            lines.append(f"{role_label}: {msg.get('content', '')}")
        last_messages = "\n".join(lines)
    else:
        last_messages = "(Starting a new chat history)"

    # Format peek context
    peek_str = json.dumps(peek_context, indent=2)

    # Spontaneous memory instruction
    spontaneous_instruction = ""
    if should_spontaneously_recall():
        random_mem = get_random_memory_for_recall()
        if random_mem:
            spontaneous_instruction = (
                f"\n\nSPONTANEOUS RECALL: You just remembered this about Harkamal — "
                f"mention it if it feels right: \"{random_mem.get('content', '')}\""
            )

    # Build prompt
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        time_label=peek_context.get("time_label", "unknown"),
        current_time=peek_context.get("time", 0),
        location=peek_context.get("location", "Unknown"),
        core_rules=core_rules,
        sifra_mood=sifra_mood,
        energy_level=energy_level,
        personality_mode=personality_mode,
        memories_formatted=memories_formatted,
        last_messages=last_messages,
        peek_context=peek_str,
        spontaneous_memory_instruction=spontaneous_instruction,
    )

    # Add mode modifier
    modifier = MODE_MODIFIERS.get(personality_mode, "")
    if modifier:
        prompt += modifier

    return prompt


def detect_mood(message: str, recent_context: str = "") -> str:
    """Use Groq to classify the user's mood from their message."""
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a mood detection system. Return only one word."},
                {"role": "user", "content": MOOD_DETECTION_PROMPT.format(message=message, context=recent_context)},
            ],
            temperature=0.1,
            max_tokens=10,
        )
        mood = response.choices[0].message.content.strip().lower()
        valid_moods = {"happy", "sad", "stressed", "anxious", "bored", "excited", "angry", "neutral", "tired", "curious", "playful", "frustrated"}
        return mood if mood in valid_moods else "neutral"
    except Exception as e:
        logger.error(f"detect_mood failed: {e}")
        return "neutral"


def generate_response(user_message: str, peek_context: dict) -> str:
    """
    Generate Sifra's response to a user message.
    Builds full context prompt, calls Groq, returns reply text.
    """
    try:
        system_prompt = build_system_prompt(peek_context)
        client = _get_groq_client()

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.85,
            max_tokens=500,
            top_p=0.9,
        )

        reply = response.choices[0].message.content.strip()

        # Update Sifra's mood based on interaction (simple heuristic)
        _update_sifra_mood_from_context(peek_context)

        return reply
    except Exception as e:
        logger.error(f"generate_response failed: {e}")
        return "yr kuch technical issue aa raha hai mujhe... ek sec ruk, try again kar"


def _update_sifra_mood_from_context(peek_context: dict) -> None:
    """Heuristically update Sifra's own mood based on interaction context."""
    mood_signal = peek_context.get("mood_signal", "neutral")
    time_label = peek_context.get("time_label", "afternoon")
    energy_signal = peek_context.get("energy_signal", "neutral")

    # Sifra's mood is influenced by the conversation
    mood_map = {
        "happy": "cheerful",
        "excited": "energetic",
        "sad": "empathetic",
        "stressed": "concerned",
        "bored": "playful",
        "neutral": "chill",
    }
    sifra_mood = mood_map.get(mood_signal, "chill")

    # Late night modifier
    if time_label == "late_night":
        sifra_mood = "introspective"

    # Energy level
    energy_map = {"high": 8, "neutral": 6, "low": 4}
    energy = energy_map.get(energy_signal, 6)
    if time_label == "late_night":
        energy = max(3, energy - 2)

    update_sifra_state({
        "current_mood": sifra_mood,
        "energy_level": energy,
    })
