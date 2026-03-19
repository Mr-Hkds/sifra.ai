"""
SIFRA:MIND — Centralized Configuration.
All env vars, model names, feature flags, and tuning constants in one place.
"""

import os

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
USER_TELEGRAM_ID = os.environ.get("USER_TELEGRAM_ID", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
GIPHY_API_KEY = os.environ.get("GIPHY_API_KEY", "GlVGYHkr3WSBnllca54iNt0yFbjz7L65")

# ---------------------------------------------------------------------------
# Timezone & Location
# ---------------------------------------------------------------------------
TIMEZONE_OFFSET = float(os.environ.get("TIMEZONE_OFFSET", 5.5))  # IST
USER_LOCATION = os.environ.get("USER_LOCATION", "Delhi, India")

# ---------------------------------------------------------------------------
# Model Configuration — Cascading Strategy
# ---------------------------------------------------------------------------
# Primary chat model: Gemini (if key available) > Groq 70B > Groq 8B
# Fast tasks (mood, classification): Groq 8B (speed matters more than depth)
# Heavy tasks (memory extraction, proactive): Groq 70B

GEMINI_CHAT_MODEL = "gemini-2.0-flash"
GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"       # Primary Groq chat
GROQ_FAST_MODEL = "llama-3.1-8b-instant"           # Fast classification tasks
GROQ_HEAVY_MODEL = "llama-3.3-70b-versatile"       # Memory extraction, proactive

# ---------------------------------------------------------------------------
# Generation Parameters
# ---------------------------------------------------------------------------
CHAT_TEMPERATURE = 0.72        # Character-consistent but creative
CHAT_MAX_TOKENS = 350          # Punchy, not verbose
FAST_TEMPERATURE = 0.15        # Deterministic for classification
FAST_MAX_TOKENS = 50           # Short structured output
HEAVY_TEMPERATURE = 0.40       # Balanced for extraction/proactive
HEAVY_MAX_TOKENS = 500         # Room for structured output
PROACTIVE_TEMPERATURE = 0.88   # More creative for spontaneous messages
PROACTIVE_MAX_TOKENS = 250     # Keep proactive messages tight

# ---------------------------------------------------------------------------
# Context & Memory Limits
# ---------------------------------------------------------------------------
CONVERSATION_CONTEXT_LIMIT = 18   # Messages to include in context
MEMORY_RECALL_LIMIT = 10          # Memories to inject into prompt
MEMORY_DECAY_DAYS = 7             # Days before decay starts
MEMORY_FORGET_THRESHOLD = 0.2    # Decay score below this = forgotten
MEMORY_SIMILARITY_THRESHOLD = 0.55  # Word overlap to consider "similar"

# ---------------------------------------------------------------------------
# Proactive Messaging
# ---------------------------------------------------------------------------
ABSENCE_THRESHOLD_MINUTES = 240   # 4 hours before "kidhar ho"
KIDHAR_HO_CHANCE = 0.40           # 40% chance when absent
GOOD_MORNING_CHANCE = 0.30
GOOD_NIGHT_CHANCE = 0.30

# ---------------------------------------------------------------------------
# Quality Gate
# ---------------------------------------------------------------------------
AI_SLOP_PHRASES = [
    "absolutely", "of course!", "certainly!", "i understand",
    "that's a great question", "how can i help", "i'm here to help",
    "i appreciate", "no worries", "feel free", "don't hesitate",
    "as an ai", "i'm an ai", "as a language model", "i'm a bot",
    "i cannot", "i'm not able to", "interesting question",
    "great question", "thanks for sharing", "i'd be happy to",
]
MAX_RESPONSE_LENGTH = 500    # Characters — hard cap
MIN_RESPONSE_LENGTH = 5     # Too short = something broke

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
VERSION = "3.0.0"
BUILD_DATE = "2026-03-19"
