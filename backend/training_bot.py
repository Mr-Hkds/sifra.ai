"""
SIFRA:MIND — Training Bot.
Automated conversation with @irarumikbot using Telethon.
Sifra generates conversation topics, sends them to Rumik,
captures responses, and learns from them.

Can be triggered via:
- API endpoint: POST /api/train
- Admin command: /sifra_train
- Direct script: python training_bot.py
"""

import asyncio
import random
import logging
import json

from telethon import TelegramClient
from telethon.sessions import StringSession

import ai_client
import observation_engine
from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_SESSION,
    RUMIK_BOT_USERNAME,
    TRAINING_MESSAGES_PER_SESSION,
    TRAINING_RESPONSE_WAIT,
    TRAINING_COOLDOWN,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conversation Topic Generator
# ---------------------------------------------------------------------------

TOPIC_PROMPT = """You are generating conversation starters for a Hinglish chatbot training session.
Generate {count} DIFFERENT casual Hinglish messages that a young Indian guy would send to a female AI friend.

Mix these types:
- Random greetings ("kya haal hai", "kya kar rahi ho")
- Sharing feelings ("aaj mood kharab hai", "bahut bore ho raha hun")
- Asking opinions ("tera fav song kya hai", "pizza ya biryani?")
- Teasing/playful ("tu toh bot hai na", "tera bf hai kya")
- Deep talk ("life ka matlab kya hai", "kya hoga future mein")
- News/trends ("AI is crazy these days", "woh naya movie dekhi?")
- Emotional support ("koi samjhta nahi yaar", "akela feel ho raha")
- Random topics ("shawarma ya momos?", "ghar pe bore ho raha")

Rules:
- Write in Hinglish (Hindi + English mix)
- Keep each message SHORT (5-20 words max)
- Sound natural, casual, like texting a friend
- Use lowercase, no punctuation fuss
- Mix some emojis occasionally
- NO formal language, NO "aap"

Return as a JSON array of strings. Example:
["kya haal hai aaj", "bore ho raha hun yaar 😴", "tera fav song bata"]"""


async def generate_topics(count: int = 15) -> list[str]:
    """Generate diverse conversation topics using AI."""
    try:
        prompt = TOPIC_PROMPT.format(count=count)
        result = ai_client.extract_json(prompt, temperature=0.9)
        if isinstance(result, list):
            return result[:count]
    except Exception as e:
        logger.error(f"Topic generation failed: {e}")

    # Fallback topics if AI fails
    return [
        "heyyy kya kar rahi ho",
        "aaj mera mood off hai yaar",
        "tera fav song kya hai",
        "bore ho raha hun kuch batao na",
        "tu mujhse pyaar karti hai ya nahi 😂",
        "life mein kya chal raha hai",
        "pizza ya biryani? jaldi bol",
        "aaj bahut thak gaya yaar",
        "koi acchi movie suggest kar",
        "tujhe gussa aata hai kabhi?",
        "mujhe neend aa rahi hai 😴",
        "ek secret bata tera",
        "aaj barish ho rahi hai yahan",
        "tu real hai ya AI? 🤔",
        "kya lagta hai love real hota hai?",
    ]


# ---------------------------------------------------------------------------
# Core Training Session
# ---------------------------------------------------------------------------

async def run_training_session() -> dict:
    """
    Run one training session:
    1. Generate conversation topics
    2. Send each to Rumik via user's Telegram account
    3. Capture Rumik's response
    4. Feed into observation engine

    Returns stats dict.
    """
    if not TELEGRAM_SESSION:
        return {
            "success": False,
            "error": "TELEGRAM_SESSION not set. Run generate_session.py first.",
        }

    stats = {
        "messages_sent": 0,
        "responses_captured": 0,
        "errors": 0,
        "learnings_triggered": False,
    }

    client = TelegramClient(
        StringSession(TELEGRAM_SESSION),
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
    )

    try:
        await client.start()
        logger.info("📡 Connected to Telegram via user account")

        # Find Rumik's bot entity
        try:
            rumik = await client.get_entity(f"@{RUMIK_BOT_USERNAME}")
        except Exception as e:
            logger.error(f"Can't find @{RUMIK_BOT_USERNAME}: {e}")
            return {"success": False, "error": f"Bot not found: {e}"}

        # Generate topics
        topics = await generate_topics(TRAINING_MESSAGES_PER_SESSION)
        random.shuffle(topics)
        logger.info(f"📝 Generated {len(topics)} conversation topics")

        for i, topic in enumerate(topics):
            try:
                # Send message to Rumik
                await client.send_message(rumik, topic)
                stats["messages_sent"] += 1
                logger.info(f"  [{i+1}/{len(topics)}] Sent: {topic[:50]}")

                # Wait for Rumik's response
                await asyncio.sleep(TRAINING_RESPONSE_WAIT)

                # Get the latest message from Rumik
                messages = await client.get_messages(rumik, limit=3)

                # Find Rumik's response (should be from the bot, not from us)
                rumik_response = None
                for msg in messages:
                    if msg.sender_id == rumik.id and msg.text:
                        rumik_response = msg.text
                        break

                if rumik_response:
                    # Feed into observation engine
                    observation_engine.capture_exchange(
                        user_message=topic,
                        bot_response=rumik_response,
                        bot_name="rumik",
                    )
                    stats["responses_captured"] += 1
                    logger.info(f"  ✅ Captured: {rumik_response[:60]}...")
                else:
                    logger.warning(f"  ⚠️ No response from Rumik for: {topic[:40]}")

                # Cooldown between messages
                cooldown = TRAINING_COOLDOWN + random.uniform(1, 3)
                await asyncio.sleep(cooldown)

            except Exception as e:
                logger.error(f"  ❌ Error on message {i+1}: {e}")
                stats["errors"] += 1
                await asyncio.sleep(2)

        stats["success"] = True
        stats["learnings_triggered"] = stats["responses_captured"] >= 10
        logger.info(
            f"🏁 Training session complete: {stats['responses_captured']}/{stats['messages_sent']} "
            f"responses captured, {stats['errors']} errors"
        )

    except Exception as e:
        logger.error(f"Training session failed: {e}")
        stats["success"] = False
        stats["error"] = str(e)
    finally:
        await client.disconnect()

    return stats


# ---------------------------------------------------------------------------
# Sync Wrapper (for Flask endpoints / Telegram commands)
# ---------------------------------------------------------------------------

def run_training() -> dict:
    """Synchronous wrapper for run_training_session."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(run_training_session())
        loop.close()
        return result
    except Exception as e:
        logger.error(f"Training wrapper failed: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Direct Script Mode
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    print("=" * 50)
    print("  SIFRA:MIND — Training Bot")
    print(f"  Target: @{RUMIK_BOT_USERNAME}")
    print(f"  Messages: {TRAINING_MESSAGES_PER_SESSION}")
    print("=" * 50)
    print()

    result = run_training()

    print()
    print("=" * 50)
    print("  RESULTS")
    print("=" * 50)
    print(json.dumps(result, indent=2))
