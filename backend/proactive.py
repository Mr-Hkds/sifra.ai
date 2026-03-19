"""
SIFRA:MIND — Proactive Messaging System.
Sifra sends messages on her own: greetings, gossip, random thoughts, kidhar ho.
Triggered by Vercel Cron Jobs.
"""

import random
import logging
import requests
from datetime import datetime, timezone, timedelta

import ai_client
from supabase_client import (
    save_conversation, get_sifra_state, get_conversations, get_top_memories,
)
from telegram_handler import send_message
from config import (
    TIMEZONE_OFFSET, USER_TELEGRAM_ID, NEWS_API_KEY,
    ABSENCE_THRESHOLD_MINUTES, KIDHAR_HO_CHANCE,
    GOOD_MORNING_CHANCE, GOOD_NIGHT_CHANCE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Time Helpers
# ---------------------------------------------------------------------------

def _get_local_hour() -> int:
    utc_now = datetime.now(timezone.utc)
    local_now = utc_now + timedelta(hours=TIMEZONE_OFFSET)
    return local_now.hour


# ---------------------------------------------------------------------------
# Content Discovery
# ---------------------------------------------------------------------------

def _fetch_news() -> str | None:
    """Fetch a trending news headline from India."""
    try:
        if not NEWS_API_KEY:
            return None
        resp = requests.get(
            f"https://newsapi.org/v2/top-headlines",
            params={"country": "in", "pageSize": 10, "apiKey": NEWS_API_KEY},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        articles = resp.json().get("articles", [])
        if not articles:
            return None
        article = random.choice(articles)
        title = article.get("title", "")
        desc = article.get("description", "")
        return f"Headline: {title}\nSummary: {desc}" if title else None
    except Exception as e:
        logger.error(f"News fetch: {e}")
        return None


def _fetch_reddit() -> str | None:
    """Fetch an interesting/gossip-worthy Reddit post."""
    gossip = ["AmItheAsshole", "relationship_advice", "tifu", "TrueOffMyChest",
              "confessions", "pettyrevenge", "MaliciousCompliance"]
    interesting = ["todayilearned", "Showerthoughts", "interestingasfuck",
                   "LifeProTips", "AskReddit"]
    funny = ["funny", "memes", "meirl"]

    all_subs = gossip * 3 + interesting * 2 + funny
    sub = random.choice(all_subs)
    category = "gossip" if sub in gossip else "interesting" if sub in interesting else "funny"

    try:
        resp = requests.get(
            f"https://www.reddit.com/r/{sub}/hot.json?limit=15",
            headers={"User-Agent": "SifraMind/3.0"},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        posts = resp.json().get("data", {}).get("children", [])
        valid = [p for p in posts if not p.get("data", {}).get("stickied", False)]
        if not valid:
            return None
        post = random.choice(valid)
        d = post["data"]
        title = d.get("title", "")
        selftext = d.get("selftext", "")[:300]
        subreddit = d.get("subreddit", "")
        return f"[{category}] r/{subreddit}: {title}\n{selftext}" if title else None
    except Exception as e:
        logger.error(f"Reddit fetch: {e}")
        return None


def _fetch_fact() -> str | None:
    """Fetch a random fun fact."""
    try:
        resp = requests.get("https://uselessfacts.jsph.pl/api/v2/facts/random", timeout=5)
        return resp.json().get("text") if resp.status_code == 200 else None
    except Exception:
        return None


def _discover_content() -> str | None:
    """Try sources and return something interesting."""
    sources = [_fetch_reddit, _fetch_news, _fetch_fact, _fetch_reddit]
    random.shuffle(sources)
    for source in sources:
        content = source()
        if content:
            return content
    return None


# ---------------------------------------------------------------------------
# Absence Detection
# ---------------------------------------------------------------------------

def _check_absence() -> int | None:
    """Minutes since last user message. None if no history."""
    try:
        recent = get_conversations(limit=5)
        for msg in (recent or []):
            if msg.get("role") == "user" and msg.get("timestamp"):
                last = datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))
                return int((datetime.now(timezone.utc) - last).total_seconds() / 60)
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Message Generation
# ---------------------------------------------------------------------------

def _generate(message_type: str, content: str | None = None) -> str | None:
    """Generate a proactive message in Sifra's voice."""
    try:
        state = get_sifra_state()
        recent = get_conversations(limit=3)
        recent_str = "\n".join([
            f"{'Harkamal' if m.get('role') == 'user' else 'Sifra'}: {m.get('content', '')}"
            for m in (recent or [])
        ])
        memories = get_top_memories(limit=3)
        mem_str = "\n".join([f"- {m.get('content', '')}" for m in memories]) if memories else "Nothing saved yet"
        hour = _get_local_hour()

        prompts = {
            "good_morning": (
                f"Text Harkamal good morning. It's ~{hour}:00 AM India. "
                f"Be creative — chai, dreams, random morning thought. 1-3 lines. Hinglish.\n"
                f"Things about him: {mem_str}\nNEVER fabricate facts."
            ),
            "good_night": (
                f"Text Harkamal good night. It's ~{hour}:00 at night. "
                f"Late-night thought, reflection, warm 'soja yr' vibe. 1-3 lines.\n"
                f"Things about him: {mem_str}"
            ),
            "gossip": (
                f"You just read something JUICY online. Share it with Harkamal.\n\n"
                f"What you found:\n{content}\n\n"
                f"React like gossiping: 'yr yr yr sun ye padh' or 'bhai WHAT 💀'. "
                f"Add your opinion — judge, joke, be shocked. 2-4 lines. Don't copy-paste. "
                f"NEVER add details not in the content."
            ),
            "internet_find": (
                f"You found something interesting online. Share with Harkamal.\n\n"
                f"What you found:\n{content}\n\n"
                f"React: 'arre sun ye interesting hai'. Add opinion. 2-3 lines. "
                f"NEVER add details not in the content."
            ),
            "random_thought": (
                f"You had a random thought. Share it with Harkamal.\n"
                f"Could be about life, shower thought, food craving, existential crisis, anything.\n"
                f"Time: {hour}:00 India. About Harkamal: {mem_str}\n"
                f"Recent: {recent_str}\n\n"
                f"1-2 lines. Hinglish. Random WhatsApp text out of nowhere. Be unpredictable. "
                f"NEVER fabricate facts about Harkamal."
            ),
            "kidhar_ho": (
                f"Harkamal hasn't messaged in a while. Send a casual 'where are you'.\n"
                f"NOT clingy. Options: 'yr kidhar gayab ho?', 'hello? zinda ho?', "
                f"'bhai bhool gye kya mujhe'. 1 line. Natural.\n"
                f"Recent: {recent_str}"
            ),
            "music_rec": (
                f"Recommend music to Harkamal.\n"
                f"Time: {hour}:00. His mood: {state.get('current_mood', 'neutral')}.\n"
                f"About him: {mem_str}\n\nSuggest a REAL song. "
                f"'yr ye sun abhi — [song by artist]'. 1-2 lines. "
                f"Use real popular songs (Hindi/English/Punjabi). NEVER make up fake songs."
            ),
            "memory_callback": (
                f"You remembered something about Harkamal.\n"
                f"Facts (ONLY USE THESE): {mem_str}\n"
                f"Time: {hour}:00. Recent: {recent_str}\n\n"
                f"Bring it up: 'arre yaad aaya...' or 'yr woh...'. 1-2 lines. "
                f"ONLY reference facts from memories above."
            ),
        }

        prompt = prompts.get(message_type, prompts["random_thought"])

        return ai_client.proactive(
            system_prompt=(
                "You are Sifra Sharma, 22, from Nainital. "
                "Generate ONLY the message text. No quotes, no meta-commentary. "
                "NEVER make up facts you don't know."
            ),
            user_prompt=prompt,
        )
    except Exception as e:
        logger.error(f"Proactive generation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Main Cron Handler
# ---------------------------------------------------------------------------

def run_proactive_job() -> dict:
    """
    Main proactive endpoint. Called by cron.
    Decides message type based on time, absence, and randomness.
    """
    if not USER_TELEGRAM_ID:
        return {"sent": False, "reason": "No USER_TELEGRAM_ID"}

    hour = _get_local_hour()

    # Priority 1: Kidhar ho — if absent 4+ hours (waking hours only)
    if 9 <= hour <= 23:
        gap = _check_absence()
        if gap and gap > ABSENCE_THRESHOLD_MINUTES and random.random() < KIDHAR_HO_CHANCE:
            msg = _generate("kidhar_ho")
            if msg:
                return _send_and_save(msg, "kidhar_ho")

    # Priority 2: Time-based
    msg_type = None
    content = None

    if 7 <= hour <= 9 and random.random() < GOOD_MORNING_CHANCE:
        msg_type = "good_morning"
    elif (22 <= hour or hour < 1) and random.random() < GOOD_NIGHT_CHANCE:
        msg_type = "good_night"
    elif 10 <= hour <= 22:
        roll = random.random()
        if roll < 0.12:
            content = _discover_content()
            if content:
                msg_type = "gossip" if "[gossip]" in content.lower() else "internet_find"
            else:
                msg_type = "random_thought"
        elif roll < 0.18:
            msg_type = "random_thought"
        elif roll < 0.22:
            msg_type = "music_rec"
        elif roll < 0.26:
            msg_type = "memory_callback"
    elif 1 <= hour < 7:
        return {"sent": False, "reason": f"Sleep hours ({hour}:00)"}

    if not msg_type:
        return {"sent": False, "reason": "Random chance skipped"}

    msg = _generate(msg_type, content)
    if not msg:
        return {"sent": False, "reason": "Generation failed"}

    return _send_and_save(msg, msg_type)


def _send_and_save(message: str, msg_type: str) -> dict:
    """Send via Telegram and save to history."""
    success = send_message(USER_TELEGRAM_ID, message)
    if success:
        save_conversation("sifra", message, mood_detected="proactive", platform="telegram")
        logger.info(f"Proactive sent: type={msg_type}")
        return {"sent": True, "type": msg_type, "message": message[:100]}
    return {"sent": False, "reason": "Telegram send failed"}
