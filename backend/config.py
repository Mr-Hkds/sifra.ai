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
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")

# ---------------------------------------------------------------------------
# Timezone & Location
# ---------------------------------------------------------------------------
TIMEZONE_OFFSET = float(os.environ.get("TIMEZONE_OFFSET", 5.5))  # IST
USER_LOCATION = os.environ.get("USER_LOCATION", "Delhi, India")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

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

SARVAM_CHAT_MODEL = "sarvam-105b"                   # Primary Hinglish model

# ---------------------------------------------------------------------------
# Generation Parameters
# ---------------------------------------------------------------------------
CHAT_TEMPERATURE = 0.78        # Slightly more creative for varied responses
CHAT_MAX_TOKENS = 350          # Punchy, not verbose
FAST_TEMPERATURE = 0.15        # Deterministic for classification
FAST_MAX_TOKENS = 300          # Enough for memory extraction JSON
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
MEMORY_AI_RANKING_CANDIDATES = 30 # Pre-filter candidates for AI ranking
MEMORY_EPISODE_GAP_MINUTES = 30   # Gap before saving conversation episode

# ---------------------------------------------------------------------------
# Proactive Messaging
# ---------------------------------------------------------------------------
ABSENCE_THRESHOLD_MINUTES = 240   # 4 hours before "kidhar ho"
KIDHAR_HO_CHANCE = 0.40           # 40% chance when absent
GOOD_MORNING_CHANCE = 0.30
GOOD_NIGHT_CHANCE = 0.30
PROACTIVE_DAILY_BUDGET = 3        # Max proactive messages per day
PROACTIVE_COOLDOWN_HOURS = 3      # Min hours between proactive messages
PROACTIVE_CONVERSATION_BUFFER_MIN = 30  # Don't send if user chatted recently

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
    # v4.2 additions — more AI giveaways
    "i don't have feelings", "i can't feel", "i was programmed",
    "i'm just a", "i'm designed to", "my purpose is",
    "i'm here for you no matter what", "that's completely valid",
    "i hear you", "your feelings are valid", "that must be",
    "i want you to know", "remember that you're",
    "it's okay to feel", "you're not alone in this",
    "certainly", "delighted to", "wonderful question",
]
MAX_RESPONSE_LENGTH = 500    # Characters — hard cap
MIN_RESPONSE_LENGTH = 5     # Too short = something broke

# ---------------------------------------------------------------------------
# Search Intelligence
# ---------------------------------------------------------------------------
SEARCH_INTENT_TEMPERATURE = 0.15   # Deterministic for search intent detection
SEARCH_QUERY_TEMPERATURE = 0.30   # Balanced for query extraction

# ---------------------------------------------------------------------------
# Observation Learning (Learn from other bots)
# ---------------------------------------------------------------------------
RUMIK_BOT_USERNAME = "irarumikbot"
OBSERVATION_BATCH_SIZE = 10          # Analyze after this many observations
OBSERVATION_MAX_LEARNINGS = 80       # Max stored learning patterns (up from 50)
OBSERVATION_ANALYSIS_TEMPERATURE = 0.40  # Slightly higher for richer patterns



# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
VERSION = "5.0.0"
BUILD_DATE = "2026-03-25"
