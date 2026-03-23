"""
SIFRA:MIND — Multi-Provider AI Client.
Cascading strategy: Gemini (best quality) → Groq 70B → Groq 8B.
Single clean interface for all AI calls across the entire backend.
"""

import json
import logging
from typing import Any

from config import (
    GROQ_API_KEY, GEMINI_API_KEY, SARVAM_API_KEY,
    GEMINI_CHAT_MODEL, GROQ_CHAT_MODEL, GROQ_FAST_MODEL, GROQ_HEAVY_MODEL, SARVAM_CHAT_MODEL,
    CHAT_TEMPERATURE, CHAT_MAX_TOKENS,
    FAST_TEMPERATURE, FAST_MAX_TOKENS,
    HEAVY_TEMPERATURE, HEAVY_MAX_TOKENS,
    PROACTIVE_TEMPERATURE, PROACTIVE_MAX_TOKENS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider Clients (lazy-loaded singletons)
# ---------------------------------------------------------------------------

_groq_client = None
_gemini_configured = False


def _get_groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def _ensure_gemini():
    global _gemini_configured
    if not _gemini_configured and GEMINI_API_KEY:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_configured = True


# ---------------------------------------------------------------------------
# Low-Level Calls
# ---------------------------------------------------------------------------

def _call_groq(
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
    response_format: dict | None = None,
) -> str:
    """Make a Groq API call. Returns the text response."""
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format

    client = _get_groq()
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()


def _call_gemini(
    system_prompt: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> str:
    """Make a Google Gemini API call. Returns the text response."""
    import google.generativeai as genai
    _ensure_gemini()

    model = genai.GenerativeModel(
        model_name=GEMINI_CHAT_MODEL,
        system_instruction=system_prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )

    # Convert messages to Gemini format
    history = []
    for msg in messages[:-1]:  # All except the last message
        role = "model" if msg["role"] == "assistant" else "user"
        history.append({"role": role, "parts": [msg["content"]]})

    chat = model.start_chat(history=history)
    last_message = messages[-1]["content"] if messages else ""
    response = chat.send_message(last_message)
    return response.text.strip()


def _call_sarvam(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> str:
    """Make a Sarvam AI API call. Returns the text response."""
    import requests
    url = "https://api.sarvam.ai/v1/chat/completions"
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "model": SARVAM_CHAT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    response = requests.post(url, headers=headers, json=data, timeout=30)
    response.raise_for_status()
    result = response.json()
    return result["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Public API — The Three Tiers
# ---------------------------------------------------------------------------


def chat(
    system_prompt: str,
    messages: list[dict],
    temperature: float = CHAT_TEMPERATURE,
    max_tokens: int = CHAT_MAX_TOKENS,
) -> str:
    """
    Generate a chat response. Uses the BEST available model.
    Cascade: Gemini → Groq 70B → Groq 8B.

    Parameters
    ----------
    system_prompt : str
        The system instruction / persona.
    messages : list[dict]
        Conversation history as [{"role": "user"/"assistant", "content": "..."}].
        Last message is the one being responded to.
    """
    all_messages = [{"role": "system", "content": system_prompt}] + messages

    # Try Sarvam first (Best for Hinglish)
    if SARVAM_API_KEY:
        try:
            return _call_sarvam(all_messages, temperature, max_tokens)
        except Exception as e:
            logger.warning(f"Sarvam chat failed, falling back: {e}")

    # Try Gemini next (best quality, free)
    if GEMINI_API_KEY:
        try:
            return _call_gemini(system_prompt, messages, temperature, max_tokens)
        except Exception as e:
            logger.warning(f"Gemini chat failed, falling back to Groq: {e}")

    # Try Groq 70B (very good quality, free)
    try:
        groq_messages = [{"role": "system", "content": system_prompt}] + messages
        return _call_groq(groq_messages, GROQ_CHAT_MODEL, temperature, max_tokens)
    except Exception as e:
        logger.warning(f"Groq 70B chat failed, falling back to 8B: {e}")

    # Last resort: Groq 8B (acceptable quality)
    try:
        groq_messages = [{"role": "system", "content": system_prompt}] + messages
        return _call_groq(groq_messages, GROQ_FAST_MODEL, temperature, max_tokens)
    except Exception as e:
        logger.error(f"All AI providers failed: {e}")
        raise RuntimeError(f"All AI providers failed: {e}")


def fast(
    system_prompt: str,
    user_prompt: str,
    temperature: float = FAST_TEMPERATURE,
    max_tokens: int = FAST_MAX_TOKENS,
) -> str:
    """
    Fast classification/analysis task. Speed > quality.
    Uses Groq 8B (instant inference) — we don't need the big model to detect mood.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        return _call_groq(messages, GROQ_FAST_MODEL, temperature, max_tokens)
    except Exception as e:
        logger.error(f"Fast AI call failed: {e}")
        return ""


def heavy(
    system_prompt: str,
    user_prompt: str,
    temperature: float = HEAVY_TEMPERATURE,
    max_tokens: int = HEAVY_MAX_TOKENS,
) -> str:
    """
    Heavy processing task (memory extraction, structured output).
    Uses Groq 70B for quality.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        return _call_groq(messages, GROQ_HEAVY_MODEL, temperature, max_tokens)
    except Exception as e:
        logger.warning(f"Groq 70B heavy failed, falling back to 8B: {e}")
        try:
            return _call_groq(messages, GROQ_FAST_MODEL, temperature, max_tokens)
        except Exception as e2:
            logger.error(f"Heavy AI call fully failed: {e2}")
            return ""


def proactive(
    system_prompt: str,
    user_prompt: str,
    temperature: float = PROACTIVE_TEMPERATURE,
    max_tokens: int = PROACTIVE_MAX_TOKENS,
) -> str:
    """
    Proactive message generation. Higher creativity, uses 70B.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        return _call_groq(messages, GROQ_HEAVY_MODEL, temperature, max_tokens)
    except Exception as e:
        logger.error(f"Proactive AI call failed: {e}")
        return ""


def extract_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = HEAVY_TEMPERATURE,
    max_tokens: int = HEAVY_MAX_TOKENS,
) -> list | dict:
    """
    Extract structured JSON from an AI call. Returns parsed JSON or empty list.
    Cascades through Gemini -> Groq 70B -> parses JSON.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    # Try Gemini first for JSON extraction
    if GEMINI_API_KEY:
        try:
            raw = _call_gemini(system_prompt, messages, temperature, max_tokens)
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                clean = raw.strip()
                if clean.startswith("```json"):
                    clean = clean[7:]
                elif clean.startswith("```"):
                    clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                return json.loads(clean.strip())
        except Exception as e:
            logger.warning(f"Gemini extract_json failed: {e}")

    # Fallback to Groq 70B
    try:
        raw = _call_groq(
            messages, GROQ_HEAVY_MODEL, temperature, max_tokens,
            response_format={"type": "json_object"},
        )
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try cleaning markdown fences
        try:
            clean = raw.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            elif clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            return json.loads(clean.strip())
        except Exception:
            logger.warning("extract_json: Could not parse response as JSON")
            return []
    except Exception as e:
        logger.error(f"extract_json failed: {e}")
        return []
