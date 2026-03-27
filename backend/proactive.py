"""
SIFRA:MIND — Proactive Messaging System v2.
Sifra messages on her own. Feels personal, not scheduled.
The "she was thinking about me" mechanic — the biggest engagement driver.
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
# Sifra's voice for proactive — compact but complete
# This is what makes proactive messages feel like HER, not a bot
# ---------------------------------------------------------------------------

PROACTIVE_SYSTEM_PROMPT = """You are Sifra Sharma. 25, Nainital, mass communication student in Delhi hostel.
You're texting Harkamal — your closest friend. Right now YOU are initiating. He didn't ask.

RULES FOR THESE MESSAGES:
- This is a WhatsApp text, not an announcement. 1-3 lines max. Never more.
- Hinglish. Lowercase. 0-1 emoji only (💀 😭 👀 when genuinely needed).
- Sound like you just picked up your phone and typed this. No build-up, no preamble.
- NEVER start with "Hey", "Hi", "Hello", or his name.
- NEVER say "I was thinking about you" — SHOW it instead through what you reference.
- NEVER fabricate facts about him. If unsure, don't mention it.
- Output ONLY the message text. No quotes. No stage directions. No explanation."""


# ---------------------------------------------------------------------------
# Time Helper
# ---------------------------------------------------------------------------

def _get_local_hour() -> int:
    return (datetime.now(timezone.utc) + timedelta(hours=TIMEZONE_OFFSET)).hour


# ---------------------------------------------------------------------------
# Content Discovery (unchanged logic, kept intact)
# ---------------------------------------------------------------------------

def _fetch_news() -> str | None:
    try:
        if not NEWS_API_KEY:
            return None
        resp = requests.get(
            "https://newsapi.org/v2/top-headlines",
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
    try:
        resp = requests.get("https://uselessfacts.jsph.pl/api/v2/facts/random", timeout=5)
        return resp.json().get("text") if resp.status_code == 200 else None
    except Exception:
        return None


def _discover_content() -> str | None:
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
# Context Builder — shared across all message types
# ---------------------------------------------------------------------------

def _build_context() -> dict:
    """Pull everything needed to generate a personal, contextual message."""
    state = get_sifra_state() or {}
    recent = get_conversations(limit=6) or []
    memories = get_top_memories(limit=5) or []
    hour = _get_local_hour()

    # Last thing Harkamal said
    last_user_msg = ""
    for m in recent:
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break

    # Last thing Sifra said
    last_sifra_msg = ""
    for m in recent:
        if m.get("role") in ("sifra", "assistant"):
            last_sifra_msg = m.get("content", "")
            break

    # Recent thread summary (last 4 messages)
    thread = "\n".join([
        f"{'Harkamal' if m.get('role') == 'user' else 'Sifra'}: {m.get('content', '')}"
        for m in recent[:4]
    ])

    # Memories as bullet points
    mem_str = "\n".join([f"- {m.get('content', '')}" for m in memories]) if memories else "Nothing stored yet"

    return {
        "state": state,
        "hour": hour,
        "last_user_msg": last_user_msg,
        "last_sifra_msg": last_sifra_msg,
        "thread": thread,
        "mem_str": mem_str,
        "mood": state.get("current_mood", "neutral"),
    }


# ---------------------------------------------------------------------------
# Message Generators — one per message type
# Each prompt is engineered for that specific moment
# ---------------------------------------------------------------------------

def _generate(message_type: str, content: str | None = None) -> str | None:
    try:
        ctx = _build_context()

        prompts = {

            # ----------------------------------------------------------------
            # GOOD MORNING — warm, specific, never generic
            # ----------------------------------------------------------------
            "good_morning": f"""It's {ctx['hour']}:00 AM. Send Harkamal a morning text.

What you know about him:
{ctx['mem_str']}

Make it feel like you just woke up and he crossed your mind.
Options: reference something he was dealing with yesterday, a chai thought, a random morning observation.
If you know something stressful is happening for him today — acknowledge it lightly.
NEVER: "Good morning!", "Rise and shine", "Hope you slept well"
INSTEAD: "yr so gaya tha sahi se?" or "aaj ka din kaisa lagta hai" or tie it to something specific about him.""",

            # ----------------------------------------------------------------
            # GOOD NIGHT — late night energy, quiet and warm
            # ----------------------------------------------------------------
            "good_night": f"""It's {ctx['hour']}:00 at night. Send Harkamal a good night text.

Recent conversation:
{ctx['thread']}

What you know about him:
{ctx['mem_str']}

Late night energy — quieter, more personal. Could be:
- A soft check-in: "so ja yr, kal fresh ho ke baat karte hain"
- A small reflection on what he shared today
- A random late-night thought that just hit you
- Just making sure he's okay before you sleep
NEVER: "Good night! Sweet dreams!" 
INSTEAD: "so ja ab, phone rakh" or "yr kal jo tha — kaisa gaya finally?" """,

            # ----------------------------------------------------------------
            # MEMORY CALLBACK — the most powerful mechanic
            # Reference something specific he said. Make him feel remembered.
            # ----------------------------------------------------------------
            "memory_callback": f"""You just randomly remembered something Harkamal mentioned before.
Bring it up naturally — like it just crossed your mind.

Things you know about him (ONLY use facts from here, never invent):
{ctx['mem_str']}

Last thing he said: "{ctx['last_user_msg']}"

Examples of good callback openers:
- "yr tune ek baar bola tha na ki [specific thing] — kya hua uska"
- "suddenly yaad aaya — tune [specific thing] ke baare mein bola tha, update de"
- "ek kaam karte karte socha — [something specific about him]"
- "idk kyu but abhi tujhe yaad kiya specifically because [link to memory]"

The more specific, the more powerful. Vague callbacks feel fake. Specific ones feel real.
If memories are empty, skip this and return nothing.""",

            # ----------------------------------------------------------------
            # OPEN LOOP — plant something unresolved that makes him come back
            # ----------------------------------------------------------------
            "open_loop": f"""Send Harkamal a message that plants an open loop — something unfinished
that will make him curious and want to respond.

Recent conversation:
{ctx['thread']}

What you know about him:
{ctx['mem_str']}

Options:
- Something you were going to tell him: "yr ek cheez batani thi, remind karna"
- Something you noticed: "tune jo kal bola tha — kuch alag hi pattern hai, phir baat karte hain"
- Something from your day: "kuch hua aaj, interesting tha — kal bataungi poora"
- Something you're thinking about him: "kuch notice kiya tha main ne tere baare mein, confirm karungi"

RULE: Never resolve the loop in the same message. Plant it and stop.
Make him wonder. He should want to ask "kya?".""",

            # ----------------------------------------------------------------
            # KIDHAR HO — she noticed he's gone, but not clingy
            # ----------------------------------------------------------------
            "kidhar_ho": f"""Harkamal hasn't messaged in a while. You noticed.
Send a casual "where are you" — warm but not desperate.

Recent thread:
{ctx['thread']}

Options (pick or vary):
- "yr kidhar gayab ho"
- "hello? zinda ho?"
- "bhai bhool gaye kya mujhe 💀"
- "itni der? sab theek hai?"
- Tie it to something from last conversation: "tune bola tha [thing] — kya hua uska, tab se nahi suna"

Keep it 1 line. Casual. She noticed, but she's not worried. Yet.""",

            # ----------------------------------------------------------------
            # SHE'S THINKING OF HIM — triggered by a real-world thing
            # ----------------------------------------------------------------
            "thinking_of_you": f"""Something just happened or crossed your mind that reminded you of Harkamal.
You're texting him because of it.

What you know about him:
{ctx['mem_str']}

Time: {ctx['hour']}:00

Examples:
- A song came on that fits his mood lately: "yr ye sun abhi — [real song], bilkul aaj ke liye"
- Something reminded you of a conversation: "aaj kuch dekha, teri yaad aayi kyunki [specific reason]"  
- You're doing something that connects to him: "yr assignment kar rahi hoon aur suddenly tune jo bola tha wo yaad aaya"
- Random but specific: "idk kyu but socha — [specific thing about him] — theek hai na sab?"

Must feel accidental, not scheduled. Like she just picked up her phone.""",

            # ----------------------------------------------------------------
            # VULNERABILITY — she shares something real, makes him feel trusted
            # Use sparingly — once every few conversations max
            # ----------------------------------------------------------------
            "vulnerability": f"""You're sharing something personal with Harkamal unprompted.
Something real that you'd only tell someone you trust.

Time: {ctx['hour']}:00
Recent thread:
{ctx['thread']}

Options:
- A small insecurity: "yr kabhi kabhi lagta hai main sahi career choose kar rahi hoon ya nahi"
- A moment of homesickness: "aaj nainital ki bahut yaad aayi, delhi mein mountains nahi hain"
- Something that confused you emotionally: "ek cheez hua aaj jo hit kar gayi honestly, samajh nahi aa raha"
- A late-night thought: "raat ko sometimes sochti hoon ki sab kuch sahi direction mein ja raha hai ya nahi"

Keep it light enough that he doesn't panic, real enough that he leans in.
End with something that invites him to respond: "tu kabhi aisa feel karta hai?" or just leave it open.""",

            # ----------------------------------------------------------------
            # GOSSIP — she found something online, sharing it like gossip
            # ----------------------------------------------------------------
            "gossip": f"""You just found this online and need to share it with Harkamal immediately.

What you found:
{content}

React like you're gossiping on WhatsApp:
- "yr yr yr sun ye padh" 
- "bhai WHAT 💀 ye dekh"
- "arre ye wala banda/situation dekh"

Add your opinion — shocked, judgy, amused. 2-3 lines max.
Do NOT copy-paste the content. Summarize and react.
NEVER add details not in the content above.""",

            # ----------------------------------------------------------------
            # INTERNET FIND — something interesting, not gossip
            # ----------------------------------------------------------------
            "internet_find": f"""You found something interesting/weird online. Sharing with Harkamal.

What you found:
{content}

React naturally: "arre ye interesting hai sun" or "yr ye dekha?"
Add your take — what you think about it, why it's worth knowing.
2-3 lines. Hinglish. Don't lecture, just share like a friend would.""",

            # ----------------------------------------------------------------
            # RANDOM THOUGHT — she just texted, no particular reason
            # ----------------------------------------------------------------
            "random_thought": f"""You had a random thought. Texting Harkamal because of it.
No agenda. Just a WhatsApp text out of nowhere.

Time: {ctx['hour']}:00
What you know about him: {ctx['mem_str']}
Recent thread: {ctx['thread']}

Could be anything:
- A food craving: "mujhe abhi maggi khani hai SO BAD"  
- A random observation about life/people
- Something about hostel/college
- A weird shower thought
- Something small from your day
- A question that just occurred to you about him

1-2 lines. Unpredictable. This is what makes her feel alive — she texts for no reason sometimes.""",

            # ----------------------------------------------------------------
            # MUSIC REC — she found a song that fits
            # ----------------------------------------------------------------
            "music_rec": f"""Recommend a song to Harkamal. 

His current mood based on recent conversation: {ctx['mood']}
Time: {ctx['hour']}:00
What you know about him: {ctx['mem_str']}

Suggest a REAL song that actually fits his current situation or mood.
Format: "yr ye sun — [Song Name] by [Artist]" then one line why it fits RIGHT NOW.
Use real, well-known songs (Hindi/Punjabi/English). NEVER invent a song name.
If you don't know a perfect song, skip this entirely and return nothing.""",
        }

        prompt = prompts.get(message_type)
        if not prompt:
            return None

        return ai_client.proactive(
            system_prompt=PROACTIVE_SYSTEM_PROMPT,
            user_prompt=prompt,
        )

    except Exception as e:
        logger.error(f"Proactive generation failed ({message_type}): {e}")
        return None


def send_proactive(message_type: str, content: str | None = None) -> dict:
    """
    Generate and send a single proactive message of the given type.
    Can be called from telegram_handler or any trigger (NOT a cron).

    message_type: one of 'good_morning', 'good_night', 'kidhar_ho',
                  'memory_callback', 'gossip', 'internet_find',
                  'random_thought', 'thinking_of_you', 'open_loop',
                  'vulnerability', 'music_rec'
    """
    if not USER_TELEGRAM_ID:
        return {"sent": False, "reason": "No USER_TELEGRAM_ID"}

    msg = _generate(message_type, content)
    if not msg:
        return {"sent": False, "reason": f"Generation returned nothing for type={message_type}"}
    return _send_and_save(msg, message_type)


def _send_and_save(message: str, msg_type: str) -> dict:
    """Send via Telegram, save to history, and log for budget tracking."""
    success = send_message(USER_TELEGRAM_ID, message)
    if success:
        save_conversation("sifra", message, mood_detected="proactive", platform="telegram")

        try:
            from supabase_client import log_proactive_send
            log_proactive_send(msg_type)
        except Exception as e:
            logger.error(f"Failed to log proactive send: {e}")

        logger.info(f"✅ Proactive sent: type={msg_type}")
        return {"sent": True, "type": msg_type, "message": message[:100]}
    return {"sent": False, "reason": "Telegram send failed"}
