"""
Proactive Messaging System — Sifra sends messages on her own.
Triggered by Vercel Cron Jobs / external cron at scheduled intervals.

Features:
- Good morning / good night greetings
- Random internet finds (news, Reddit gossip, fun facts)
- Spontaneous thoughts and memory-based messages
- "Kidhar ho" absence detection
- Mood-based music recommendations
"""

import os
import json
import random
import logging
import requests
from datetime import datetime, timezone, timedelta
from groq import Groq

from supabase_client import (
    save_conversation,
    get_sifra_state,
    update_sifra_state,
    get_conversations,
    get_top_memories,
)
from telegram_handler import send_telegram_message

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
USER_TELEGRAM_ID = os.environ.get("USER_TELEGRAM_ID", "")
TIMEZONE_OFFSET = float(os.environ.get("TIMEZONE_OFFSET", 5.5))

# NewsAPI (free tier — 100 requests/day)
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")


def _get_local_hour() -> int:
    """Get the current hour in user's local timezone."""
    utc_now = datetime.now(timezone.utc)
    local_now = utc_now + timedelta(hours=TIMEZONE_OFFSET)
    return local_now.hour


def _get_groq_client() -> Groq:
    return Groq(api_key=GROQ_API_KEY)


# ===================================================================
# CONTENT DISCOVERY — "Scrolling the Internet"
# ===================================================================

def _fetch_trending_news() -> str | None:
    """Fetch a random trending news headline from India."""
    try:
        if not NEWS_API_KEY:
            return None
        url = f"https://newsapi.org/v2/top-headlines?country=in&pageSize=10&apiKey={NEWS_API_KEY}"
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        articles = resp.json().get("articles", [])
        if not articles:
            return None
        article = random.choice(articles)
        title = article.get("title", "")
        description = article.get("description", "")
        return f"Headline: {title}\nSummary: {description}" if title else None
    except Exception as e:
        logger.error(f"News fetch failed: {e}")
        return None


def _fetch_random_fact() -> str | None:
    """Fetch a random fun/interesting fact."""
    try:
        resp = requests.get("https://uselessfacts.jsph.pl/api/v2/facts/random", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("text", None)
        return None
    except Exception:
        return None


def _fetch_reddit_gossip() -> str | None:
    """Fetch a random juicy/interesting/funny story from Reddit gossip-worthy subreddits."""
    gossip_subs = [
        "AmItheAsshole", "relationship_advice", "tifu",
        "TrueOffMyChest", "confessions", "pettyrevenge",
        "MaliciousCompliance", "entitledparents",
    ]
    interesting_subs = [
        "todayilearned", "Showerthoughts", "mildlyinteresting",
        "interestingasfuck", "coolguides", "LifeProTips",
        "AskReddit",
    ]
    funny_subs = [
        "funny", "memes", "meirl", "cursedcomments",
    ]

    # Mix them up — gossip gets higher weight
    all_subs = gossip_subs * 3 + interesting_subs * 2 + funny_subs
    sub = random.choice(all_subs)

    try:
        headers = {"User-Agent": "SifraMind/1.0"}
        resp = requests.get(
            f"https://www.reddit.com/r/{sub}/hot.json?limit=15",
            headers=headers, timeout=8
        )
        if resp.status_code != 200:
            return None
        posts = resp.json().get("data", {}).get("children", [])
        if not posts:
            return None
        # Filter out pinned posts and very short ones
        valid_posts = [p for p in posts if not p.get("data", {}).get("stickied", False)]
        if not valid_posts:
            return None
        post = random.choice(valid_posts)
        data = post.get("data", {})
        title = data.get("title", "")
        selftext = data.get("selftext", "")[:300]
        subreddit = data.get("subreddit", "")

        category = "gossip" if sub in gossip_subs else "interesting" if sub in interesting_subs else "funny"
        return f"[{category}] r/{subreddit}: {title}\n{selftext}" if title else None
    except Exception as e:
        logger.error(f"Reddit fetch failed: {e}")
        return None


def _discover_content() -> str | None:
    """Try multiple sources and return something interesting."""
    sources = [_fetch_reddit_gossip, _fetch_trending_news, _fetch_random_fact, _fetch_reddit_gossip]
    random.shuffle(sources)
    for source in sources:
        content = source()
        if content:
            return content
    return None


# ===================================================================
# ABSENCE DETECTION — "Kidhar ho"
# ===================================================================

def _check_absence() -> int | None:
    """Check how many minutes since the last user message. Returns None if no history."""
    try:
        recent = get_conversations(limit=5)
        if not recent:
            return None
        # Find last user message
        for msg in recent:
            if msg.get("role") == "user":
                ts = msg.get("timestamp", "")
                if ts:
                    last_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    gap = (datetime.now(timezone.utc) - last_time).total_seconds() / 60
                    return int(gap)
        return None
    except Exception:
        return None


# ===================================================================
# MESSAGE GENERATION — Sifra's voice
# ===================================================================

def _generate_proactive_message(message_type: str, content: str | None = None) -> str | None:
    """Use Groq to generate a natural proactive message in Sifra's voice."""
    try:
        state = get_sifra_state()
        recent = get_conversations(limit=3)
        recent_str = ""
        if recent:
            lines = [f"{'Harkamal' if m.get('role') == 'user' else 'Sifra'}: {m.get('content', '')}" for m in recent]
            recent_str = "\n".join(lines)

        memories = get_top_memories(limit=3)
        mem_str = "\n".join([f"- {m.get('content', '')}" for m in memories]) if memories else "Nothing saved yet"

        hour = _get_local_hour()

        prompts = {
            "good_morning": f"""You are Sifra texting your close friend Harkamal first thing in the morning.
It's around {hour}:00 AM in India. Send a natural good morning message.
Be creative — don't just say "good morning". Maybe something about chai, the weather, a dream you had, or a random thought.
Keep it 1-3 lines. Hinglish. Casual. WhatsApp texting style.
Things you know about him: {mem_str}
NEVER fabricate facts about him.""",

            "good_night": f"""You are Sifra texting Harkamal late at night.
It's around {hour}:00 at night. Send a natural good night message.
Be creative — a late-night thought, reflection, philosophical moment, or warm "soja yr" vibe.
Keep it 1-3 lines. Hinglish. Casual.
Things you know about him: {mem_str}""",

            "gossip": f"""You are Sifra and you just read something JUICY on the internet (Reddit/Twitter).
Share it with your close friend Harkamal like you're gossiping. Make it fun and dramatic.

What you found:
{content}

Share it like: "yr yr yr sun ye padh" or "bhai WHAT is this 💀" or "dekh kya mila internet pe"
React to it with your own opinion — judge, joke, roast, be shocked — whatever feels natural.
Keep it 2-4 lines max. Hinglish. Don't copy-paste, REACT to it like a friend would.
NEVER make up additional details that aren't in the content.""",

            "internet_find": f"""You are Sifra and you found something interesting/cool/funny on the internet.
Share it with your friend Harkamal naturally.

What you found:
{content}

React like: "arre sun ye interesting hai" or "lol ye dekh" or "bhai ye padh"
Add your opinion. Keep it 2-3 lines. Hinglish.
NEVER make up details not in the content.""",

            "random_thought": f"""You are Sifra. You just had a random thought and want to share it with Harkamal.
Could be about life, a shower thought, something funny you noticed, existential crisis, food craving, random observation, anything.
Current time: {hour}:00 in India. Things about Harkamal: {mem_str}
Last messages: {recent_str}

Send ONE spontaneous message. 1-2 lines. Hinglish. Like a random WhatsApp text out of nowhere.
Be creative and unpredictable. Don't reference cybersecurity.
NEVER fabricate facts about Harkamal.""",

            "kidhar_ho": f"""You are Sifra. Your friend Harkamal hasn't messaged you in a while and you noticed.
Send a casual "where are you" type message. NOT clingy, just friendly.
Options: "yr kidhar gayab ho?", "hello? zinda ho?", "bhai bhool gye kya mujhe", "kya scene hai, dikhte nahi aajkal"
Pick one style or create something similar. 1 line. Natural. Don't be dramatic.
Last messages: {recent_str}""",

            "music_rec": f"""You are Sifra recommending music to your friend Harkamal.
Current time: {hour}:00. His recent mood seems: {state.get('current_mood', 'neutral')}.
Things about him: {mem_str}
Last messages: {recent_str}

Suggest a REAL song/artist that fits the mood and time. Late night = chill lo-fi or deep songs. Happy = upbeat. Sad = soothing.
Share it naturally: "yr ye sun abhi — [song name by artist]" or "aaj ka mood hai [song] wala"
Keep it 1-2 lines. Don't make up fake songs — use real, popular songs (Hindi, English, or Punjabi).
NEVER fabricate facts about Harkamal.""",

            "memory_callback": f"""You are Sifra. You suddenly remembered something about your friend Harkamal.
Things you know (ONLY use facts from here): {mem_str}
Current time: {hour}:00. Last messages: {recent_str}

Bring up one of these memories naturally: "arre yaad aaya..." or "yr woh..." or "acha sun, remember when..."
1-2 lines max. Hinglish. Only reference facts from the memories above — don't invent new ones.""",
        }

        prompt = prompts.get(message_type, prompts["random_thought"])

        client = _get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are Sifra Sharma, 22, from Nainital. Generate ONLY the message text. No quotes, no meta-commentary. NEVER make up facts you don't know."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.95,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Proactive message generation failed: {e}")
        return None


# ===================================================================
# MAIN CRON HANDLER
# ===================================================================

def run_proactive_job() -> dict:
    """
    Main proactive messaging endpoint. Called by external cron.
    Decides what type of message to send based on time, absence, and randomness.
    """
    if not USER_TELEGRAM_ID:
        return {"sent": False, "reason": "No USER_TELEGRAM_ID"}

    hour = _get_local_hour()

    # ---------------------------------------------------------------
    # Priority 1: "Kidhar ho" — if user hasn't messaged in 4+ hours
    # (only during waking hours 9AM-11PM, max once per check)
    # ---------------------------------------------------------------
    if 9 <= hour <= 23:
        gap_min = _check_absence()
        if gap_min and gap_min > 240:  # 4 hours
            # Only 40% chance so we don't nag every check
            if random.random() < 0.40:
                message = _generate_proactive_message("kidhar_ho")
                if message:
                    return _send_and_save(message, "kidhar_ho")

    # ---------------------------------------------------------------
    # Priority 2: Time-based messages
    # ---------------------------------------------------------------
    message_type = None
    content = None

    # Good morning window: 7-9 AM (30% chance)
    if 7 <= hour <= 9 and random.random() < 0.30:
        message_type = "good_morning"

    # Good night window: 22-24 (30% chance)
    elif 22 <= hour or hour < 1:
        if random.random() < 0.30:
            message_type = "good_night"

    # Active hours: 10 AM - 10 PM
    elif 10 <= hour <= 22:
        roll = random.random()
        if roll < 0.12:
            # Reddit gossip / internet find
            content = _discover_content()
            if content:
                is_gossip = "[gossip]" in content.lower()
                message_type = "gossip" if is_gossip else "internet_find"
            else:
                message_type = "random_thought"
        elif roll < 0.18:
            message_type = "random_thought"
        elif roll < 0.22:
            message_type = "music_rec"
        elif roll < 0.26:
            message_type = "memory_callback"

    # Sleep hours: 1 AM - 7 AM — don't message
    else:
        return {"sent": False, "reason": f"Sleep hours ({hour}:00)"}

    if not message_type:
        return {"sent": False, "reason": "Random chance skipped this cycle"}

    # Generate and send
    message = _generate_proactive_message(message_type, content)
    if not message:
        return {"sent": False, "reason": "Generation failed"}

    return _send_and_save(message, message_type)


def _send_and_save(message: str, message_type: str) -> dict:
    """Send message via Telegram and save to conversation history."""
    success = send_telegram_message(USER_TELEGRAM_ID, message)
    if success:
        save_conversation("sifra", message, mood_detected="proactive", platform="telegram")
        logger.info(f"Proactive message sent: type={message_type}")
        return {"sent": True, "type": message_type, "message": message[:100]}
    else:
        return {"sent": False, "reason": "Telegram send failed"}
