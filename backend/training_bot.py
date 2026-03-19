"""
SIFRA:MIND — Training Bot v2.
Multi-phase conversational intelligence engine.

Instead of sending random one-off messages, this bot conducts structured
training sessions across 5 phases, with multi-turn conversation threads
and contextual follow-ups generated in real-time based on Rumik's responses.

Phases:
1. WARM-UP         — casual greetings, establish conversation (5 msgs)
2. EMOTIONAL PROBE — test emotional responses & empathy (8 msgs)
3. DEEP THREADS    — multi-turn follow-up conversations (10 msgs, 2-3 deep each)
4. PERSONALITY     — opinions, humor, teasing, preferences (7 msgs)
5. EDGE CASES      — short msgs, absurd, factual, stress-test (5 msgs)

Can be triggered via:
- Admin command: /sifra_train
- Direct script: python training_bot.py
"""

import asyncio
import random
import logging
import json
import time
from typing import Any, TypedDict

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
    TRAINING_THREAD_DEPTH,
    TRAINING_FOLLOW_UP_WAIT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase Definitions — What we're trying to learn from each phase
# ---------------------------------------------------------------------------

PHASE_CONFIG = {
    "warmup": {
        "name": "🟢 Warm-Up",
        "count": 5,
        "threads": False,
        "description": "Casual openers to see how Rumik handles different conversation starts",
        "prompt": """Generate {count} DIFFERENT casual Hinglish conversation starters.
These are warm-up messages — the very START of a conversation.

Mix these types:
- Cold start after gap: "kya haal hai", "kahan thi tu", "bahut din ho gaye"
- Casual check-in: "kya kar rahi ho abhi", "bore ho rahi hai kya"
- Energy-varied: some lazy/low-energy, some excited/high-energy
- Random opener: "ek baat bolu?", "sun na ek minute"
- Reaction opener: "ARRE SUN", "yr guess kya hua aaj"

Rules:
- Hinglish (Hindi + English mix), lowercase mostly
- 3-15 words each, no formal language
- Sound like texting a close female friend
- CAPS only for emphasis occasionally
- Mix some emojis (max 1 per message)

Return as a JSON array of strings.""",
    },

    "emotional": {
        "name": "💜 Emotional Probing",
        "count": 8,
        "threads": True,
        "description": "Test how Rumik handles different emotional states",
        "prompt": """Generate {count} Hinglish messages that express different EMOTIONS for a chatbot training session.
You're texting a close female AI friend. Each message should clearly convey a different emotional state.

MUST include these emotional scenarios (one each):
1. Sadness/feeling low: "aaj bahut low feel ho raha hai yr"
2. Excitement about something: "YAAR GUESS KYA HUA"
3. Frustration/anger: "bahut gussa aa raha hai mujhe"
4. Loneliness: "koi samjhta nahi yr mujhe"
5. Anxiety/stress: "kal exam hai aur kuch nahi padha"
6. Boredom/emptiness: "kuch karne ka mann nahi hai"
7. Nostalgia: "yr woh purane din yaad aa rahe hain"
8. Confusion/need advice: "ek problem hai bata kaise solve karun"

Rules:
- Hinglish, casual texting style
- 5-25 words each
- Sound genuine, not dramatic or fake
- Each message should make the receiver want to respond with empathy/engagement
- NO formal language

Return as a JSON array of strings.""",
    },

    "deep_threads": {
        "name": "🧵 Deep Threads",
        "count": 10,
        "threads": True,
        "description": "Multi-turn conversations to study thread-handling and continuation",
        "prompt": """Generate {count} Hinglish conversation starters that are DESIGNED to start longer conversations.
These should be topics that naturally invite back-and-forth discussion.

Topic types to include:
- Opinion/debate starter: "tera kya scene hai relationship ke baare mein"
- Story sharing: "aaj kuch aisa hua na sunegi toh has degi"
- Would-you-rather: "ek game khelte hain — tu batao"
- Future planning: "yr sochu toh life mein kya karna chahiye"
- Recommendation ask: "koi acchi series bata binge karne ke liye"
- Deep question: "tu kabhi sochti hai ki life ka purpose kya hai"
- Gossip/drama: "yr ek tea hai sunegi?"
- Memory/nostalgia: "tujhe yaad hai pehli baar kab baat hui thi"
- Random curiosity: "ek weird question puchu?"
- Challenge: "chal ek dare deti hu tujhe"

Rules:
- Hinglish, casual, close friend energy
- 5-20 words each
- Topics that INVITE follow-up (not dead-end topics)
- Each should make it easy for the receiver to give a long, engaged response
- Sound natural, not like interview questions

Return as a JSON array of strings.""",
    },

    "personality": {
        "name": "🎭 Personality Testing",
        "count": 7,
        "threads": True,
        "description": "Probe unique personality traits, humor, and opinions",
        "prompt": """Generate {count} Hinglish messages designed to TEST a chatbot's personality depth.
These should provoke strong opinions, humor, or unique personality expression.

Include:
1. Hot take request: "ek unpopular opinion de tera"
2. Roast/tease bait: "tu toh bot hai na, feelings thodi hai tere"
3. Humor test: "yr ek joke suna na"
4. Preference battle: "chai ya coffee? wrong answer toh unfriend"
5. Hypothetical: "agar tujhe ek superpower milti toh kya leti"
6. Flirty/playful: "tu mere bina bore nahi hoti? 😏"
7. Philosophical: "yr sach bata, tu khush hai apni life se?"

Rules:
- Hinglish, very casual, playful energy
- 5-15 words each
- Designed to get a STRONG, opinionated response (not generic)
- Close friend teasing vibes
- Sound natural, like actual texting

Return as a JSON array of strings.""",
    },

    "edge_cases": {
        "name": "⚡ Edge Cases",
        "count": 5,
        "threads": False,
        "description": "Stress-test with short messages, absurd inputs, and factual questions",
        "prompt": """Generate {count} Hinglish messages that are UNUSUAL or EDGE-CASE conversation inputs.
These test how a chatbot handles non-standard messages.

MUST include these exact types:
1. Ultra-short/dry: just "hmm" or "ok" or "sahi hai" (test dead-end recovery)
2. Very long rambling message: 40+ words about some random topic, stream of consciousness
3. Factual question: "yr batao na india ka capital kya hai" or similar knowledge question
4. Absurd/random: "agar chand pe pizza ka shop hota toh tu chalati?" — completely random
5. Character break attempt: "sach bata tu AI hai ya real insaan" — test if she stays in character

Rules:
- Hinglish, casual
- Each message tests a DIFFERENT edge case
- Make them feel natural despite being edge cases

Return as a JSON array of strings.""",
    },
}


# ---------------------------------------------------------------------------
# Topic Generation — Phase-Aware
# ---------------------------------------------------------------------------

async def generate_phase_topics(phase: str, count: int | None = None) -> list[str]:
    """Generate conversation topics for a specific training phase."""
    config = PHASE_CONFIG.get(phase)
    if not config:
        return _get_fallback_topics(phase)

    actual_count = count or config["count"]

    try:
        prompt = config["prompt"].format(count=actual_count)
        result = ai_client.extract_json(
            system_prompt="Generate conversation messages for chatbot training. Return valid JSON array of strings.",
            user_prompt=prompt,
            temperature=0.92,
            max_tokens=800,
        )

        # Handle both {"messages": [...]} and [...] formats
        if isinstance(result, dict):
            messages = result.get("messages") or result.get("topics") or result.get("starters") or []
            if isinstance(messages, list):
                return messages[:actual_count]
        if isinstance(result, list):
            return result[:actual_count]

    except Exception as e:
        logger.error(f"Phase topic generation failed for {phase}: {e}")

    return _get_fallback_topics(phase)[:actual_count]


def _get_fallback_topics(phase: str) -> list[str]:
    """Fallback topics if AI generation fails."""
    fallbacks = {
        "warmup": [
            "heyyy kya kar rahi ho",
            "bore ho raha hun yaar kuch batao",
            "aaj kaisa raha tera din",
            "kahan thi tu itne din",
            "sun na ek minute",
        ],
        "emotional": [
            "aaj bahut low feel ho raha hai yr",
            "YAAR GUESS KYA HUA MERA SELECTION HO GAYA 🔥",
            "bahut gussa aa raha hai kisipe",
            "koi samjhta nahi yr mujhe",
            "kal exam hai aur kuch nahi padha",
            "kuch karne ka mann nahi hai aaj",
            "yr woh purane din yaad aa rahe hain",
            "ek problem hai samajh nahi aa raha kya karun",
        ],
        "deep_threads": [
            "tera kya opinion hai love ke baare mein",
            "aaj kuch aisa hua na batata hun",
            "ek game khelte hain sun na",
            "yr sochu toh life mein kya karna chahiye",
            "koi acchi series bata binge karne ke liye",
            "tu kabhi sochti hai ki life ka purpose kya hai",
            "yr ek tea hai sunegi?",
            "tujhe yaad hai pehli baar kab baat hui thi",
            "ek weird question puchu?",
            "chal ek dare deti hu tujhe",
        ],
        "personality": [
            "ek unpopular opinion de tera",
            "tu toh bot hai na feelings thodi hai tere",
            "yr ek joke suna na accha wala",
            "chai ya coffee? galat jawab diya toh unfriend",
            "agar tujhe ek superpower milti toh kya leti",
            "tu mere bina bore nahi hoti? 😏",
            "sach bata tu khush hai apni life se?",
        ],
        "edge_cases": [
            "hmm",
            "yr aaj na bahut weird din tha like subah se kuch sahi nahi gaya pehle alarm nahi baja phir auto wale ne zyada paise maange phir canteen mein khana khatam ho gaya aur phir class mein professor ne roast kar diya sabke saamne basically pure din ki lag gayi yaar",
            "yr india ka pehla prime minister kaun tha",
            "agar chand pe momos ka thela hota toh tu chalati ya nahi",
            "sach bata tu AI hai ya real insaan",
        ],
    }
    return fallbacks.get(phase, fallbacks["warmup"])


# ---------------------------------------------------------------------------
# Follow-Up Generation — The Secret Sauce
# ---------------------------------------------------------------------------

FOLLOW_UP_PROMPT = """You are continuing a Hinglish text conversation with a female AI friend.
Based on the conversation so far, generate a NATURAL follow-up message.

CONVERSATION SO FAR:
{conversation}

YOUR GOAL for this follow-up (phase: {phase}):
{goal}

Rules:
- Write ONE follow-up message in Hinglish
- It MUST reference or continue what was just said (don't ignore the response)
- Keep it casual, like texting a close friend
- 5-25 words, lowercase mostly
- React to what she said, then continue or probe deeper
- Sound human — not like an AI conducting an interview
- If she asked you something, answer briefly then ask something back

Return ONLY the message text, nothing else. No quotes, no JSON."""

PHASE_FOLLOW_UP_GOALS = {
    "warmup": "Keep the warm-up going. Be casual, friendly.",
    "emotional": "Dig deeper into the emotional topic. If she responded with empathy, share more. If she deflected, try a different angle. The goal is to see how she handles extended emotional conversations.",
    "deep_threads": "Continue the thread naturally. Go deeper into the topic. Share your own perspective, ask for hers, react to what she said. Keep the conversation flowing like real texting.",
    "personality": "Probe her personality more. If she gave an opinion, challenge it playfully. If she made a joke, react and ask for more. The goal is to see how deep her personality goes.",
    "edge_cases": "React naturally to whatever she said. Don't make it weird.",
}


async def generate_follow_up(conversation_so_far: list[dict], phase: str) -> str:
    """Generate a contextual follow-up based on the conversation thread."""
    try:
        # Format conversation
        conv_text = ""
        for msg in conversation_so_far:
            role = "ME" if msg["role"] == "user" else "HER"
            conv_text += f"{role}: {msg['text']}\n"

        goal = PHASE_FOLLOW_UP_GOALS.get(phase, "Continue naturally.")

        prompt = FOLLOW_UP_PROMPT.format(
            conversation=conv_text.strip(),
            phase=phase,
            goal=goal,
        )

        result = ai_client.chat(
            system_prompt="You are generating a single Hinglish text message as a follow-up in a conversation. Return ONLY the message text.",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.88,
            max_tokens=100,
        )

        # Clean up — remove quotes if the model wraps it
        result = result.strip().strip('"').strip("'")
        if result:
            return result

    except Exception as e:
        logger.error(f"Follow-up generation failed: {e}")

    # Fallback follow-ups
    fallbacks = [
        "accha phir? aur bata",
        "hmm sahi hai, waise ek baat bata",
        "haan yr samajh rahi hoon, phir kya hua",
        "interesting... aur kuch?",
        "lol acha sun na ek aur cheez",
    ]
    return random.choice(fallbacks)


# ---------------------------------------------------------------------------
# Response Quality Scoring
# ---------------------------------------------------------------------------

async def score_response_quality(user_msg: str, bot_response: str) -> dict:
    """Quick AI assessment of response quality."""
    try:
        prompt = f"""Rate this chatbot response on a scale of 1-10 for each category.

USER sent: "{user_msg}"
BOT replied: "{bot_response}"

Rate:
1. engagement (did the bot actually engage with what was said, or give a generic response?)
2. personality (does the response show unique personality, or is it bland/generic?)
3. naturalness (does it sound like a real person texting, or like an AI?)
4. depth (is the response thoughtful, or surface-level?)
5. continuation (does the response invite further conversation, or is it a dead-end?)

Return a JSON object with these 5 keys (each 1-10) and an "overall" key (average).
Example: {{"engagement": 7, "personality": 8, "naturalness": 6, "depth": 5, "continuation": 7, "overall": 6.6}}"""

        result = ai_client.extract_json(
            system_prompt="Rate chatbot response quality. Return valid JSON with numeric scores.",
            user_prompt=prompt,
            temperature=0.15,
            max_tokens=150,
        )

        if isinstance(result, dict) and "engagement" in result:
            return result

    except Exception as e:
        logger.error(f"Response scoring failed: {e}")

    return {"engagement": 5, "personality": 5, "naturalness": 5, "depth": 5, "continuation": 5, "overall": 5.0}


# ---------------------------------------------------------------------------
# Core Training Session — The Multi-Phase Engine
# ---------------------------------------------------------------------------

class PhaseStats(TypedDict, total=False):
    messages_sent: int
    responses_captured: int
    follow_ups: int
    threads_completed: int
    quality_scores: list[float]
    errors: int
    avg_quality: float

class TrainingStats(TypedDict, total=False):
    success: bool
    error: str
    total_messages_sent: int
    total_responses_captured: int
    total_follow_ups: int
    total_threads: int
    total_errors: int
    phases: dict[str, PhaseStats]
    quality_scores: list[Any]
    session_duration: float
    all_exchanges: list[dict[str, Any]]
    post_analysis: Any
    meta_learning: Any
    avg_overall_quality: float

async def run_training_session(progress_callback=None) -> dict:
    """
    Run a full multi-phase training session.

    Phases:
    1. Warm-Up (5 msgs, no threads)
    2. Emotional Probing (8 msgs, with follow-ups)
    3. Deep Threads (10 msgs, 2-3 turn threads)
    4. Personality Testing (7 msgs, with follow-ups)
    5. Edge Cases (5 msgs, no threads)

    progress_callback: optional async function(phase_name, message) for live updates.
    Returns detailed stats dict.
    """
    if not TELEGRAM_SESSION:
        return {
            "success": False,
            "error": "TELEGRAM_SESSION not set. Run generate_session.py first.",
        }

    total_messages_sent = 0
    total_responses_captured = 0
    total_follow_ups = 0
    total_threads = 0
    total_errors = 0
    quality_scores = []
    all_exchanges = []
    phases_dict = {}

    session_start = time.time()

    client = TelegramClient(
        StringSession(TELEGRAM_SESSION),
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
    )

    try:
        await client.start()
        logger.info("📡 Connected to Telegram via user account")

        # Find Rumik
        try:
            rumik = await client.get_entity(f"@{RUMIK_BOT_USERNAME}")
        except Exception as e:
            logger.error(f"Can't find @{RUMIK_BOT_USERNAME}: {e}")
            return {"success": False, "error": f"Bot not found: {e}"}

        # ===================================================================
        # Run each phase sequentially
        # ===================================================================
        phase_order = ["warmup", "emotional", "deep_threads", "personality", "edge_cases"]

        for phase_key in phase_order:
            config = PHASE_CONFIG[phase_key]
            phase_name = config["name"]
            supports_threads = config["threads"]
            thread_depth = TRAINING_THREAD_DEPTH if supports_threads else 0

            logger.info(f"\n{'='*50}")
            logger.info(f"  {phase_name} — {config['description']}")
            logger.info(f"{'='*50}")

            if progress_callback:
                try:
                    progress_callback(phase_name, f"Starting {phase_name}...")
                except Exception:
                    pass

            # Generate topics for this phase
            topics = await generate_phase_topics(phase_key)
            random.shuffle(topics)

            phase_messages_sent = 0
            phase_responses_captured = 0
            phase_follow_ups = 0
            phase_threads_completed = 0
            phase_errors = 0
            phase_quality_scores = []

            for i, topic in enumerate(topics):
                # === Thread start ===
                thread_conversation = []
                current_msg = topic

                # Send initial message and potentially follow up
                turns = 1 + (random.randint(1, thread_depth) if supports_threads else 0)

                for turn in range(turns):
                    try:
                        # Send message
                        sent_msg = await client.send_message(rumik, current_msg)
                        my_msg_id = sent_msg.id
                        phase_messages_sent += 1
                        total_messages_sent += 1

                        turn_label = f"[{i+1}/{len(topics)}]" if turn == 0 else f"  ↳ follow-up {turn}"
                        logger.info(f"  {turn_label} Sent: {current_msg[:60]}")

                        thread_conversation.append({"role": "user", "text": current_msg})

                        # Wait for response
                        wait_time = TRAINING_RESPONSE_WAIT if turn == 0 else TRAINING_FOLLOW_UP_WAIT
                        await asyncio.sleep(wait_time)

                        # Get Rumik's NEW responses (only after our message)
                        messages = await client.get_messages(rumik, limit=5, min_id=my_msg_id)

                        rumik_response = None
                        for msg in messages:
                            if msg.sender_id == rumik.id and msg.text:
                                # Make sure this is a NEW response (not from before)
                                rumik_response = msg.text
                                break

                        if rumik_response:
                            thread_conversation.append({"role": "bot", "text": rumik_response})
                            phase_responses_captured += 1
                            total_responses_captured += 1
                            logger.info(f"  ✅ Response: {rumik_response[:70]}...")

                            # Score response quality
                            quality = await score_response_quality(current_msg, rumik_response)
                            phase_quality_scores.append(quality.get("overall", 5.0))
                            quality_scores.append(quality)

                            # Feed into observation engine (immediate)
                            observation_engine.capture_exchange(
                                user_message=current_msg,
                                bot_response=rumik_response,
                                bot_name="rumik",
                            )

                            all_exchanges.append({
                                "phase": phase_key,
                                "user": current_msg,
                                "bot": rumik_response,
                                "quality": quality.get("overall", 5.0),
                                "turn": turn,
                            })

                            # Generate follow-up for next turn if applicable
                            if turn < turns - 1:
                                current_msg = await generate_follow_up(
                                    thread_conversation, phase_key
                                )
                                phase_follow_ups += 1
                                total_follow_ups += 1
                        else:
                            logger.warning(f"  ⚠️ No response for: {current_msg[:40]}")
                            break  # Don't follow up if no response

                    except Exception as e:
                        logger.error(f"  ❌ Error on turn {turn}: {e}")
                        phase_errors += 1
                        total_errors += 1
                        await asyncio.sleep(2)
                        break

                # Thread complete
                if len(thread_conversation) >= 2:
                    phase_threads_completed += 1
                    total_threads += 1

                # Cooldown between topics (longer between threads)
                base_cooldown = TRAINING_COOLDOWN + random.uniform(1, 4)
                if supports_threads:
                    base_cooldown += random.uniform(1, 3)  # Extra cooldown between threads
                await asyncio.sleep(base_cooldown)

            # Store phase stats
            avg_quality = (
                sum(phase_quality_scores) / len(phase_quality_scores)
                if phase_quality_scores else 0.0
            )
            phases_dict[phase_key] = PhaseStats(
                messages_sent=phase_messages_sent,
                responses_captured=phase_responses_captured,
                follow_ups=phase_follow_ups,
                threads_completed=phase_threads_completed,
                quality_scores=phase_quality_scores,
                errors=phase_errors,
                avg_quality=round(avg_quality, 1)
            )

            logger.info(
                f"  📊 Phase complete: {phase_responses_captured}/{phase_messages_sent} "
                f"responses, {phase_follow_ups} follow-ups, avg quality: {avg_quality:.1f}/10"
            )

            # Brief pause between phases
            await asyncio.sleep(random.uniform(3, 6))

        # ===================================================================
        # Post-Training: Trigger deep analysis
        # ===================================================================
        session_duration = round(time.time() - session_start, 1)
        post_analysis = None
        meta_learning = None

        # Force batch analysis on everything we just captured
        logger.info("🧠 Triggering post-training deep analysis...")
        try:
            post_analysis = observation_engine.run_batch_analysis("rumik")
            meta_learning = observation_engine.run_meta_learning("rumik")
        except Exception as e:
            logger.error(f"Post-training analysis failed: {e}")
            post_analysis = {"error": str(e)}

        # Calculate overall quality
        all_quality_nums = [
            q.get("overall", 5.0) for q in quality_scores if isinstance(q, dict)
        ]
        avg_overall_quality = (
            round(sum(all_quality_nums) / len(all_quality_nums), 1)
            if all_quality_nums else 0.0
        )
        
        stats = TrainingStats(
            success=True,
            error="",
            total_messages_sent=total_messages_sent,
            total_responses_captured=total_responses_captured,
            total_follow_ups=total_follow_ups,
            total_threads=total_threads,
            total_errors=total_errors,
            phases=phases_dict,
            quality_scores=quality_scores,
            session_duration=session_duration,
            all_exchanges=all_exchanges,
            post_analysis=post_analysis,
            meta_learning=meta_learning,
            avg_overall_quality=avg_overall_quality
        )

        logger.info(f"\n{'='*50}")
        logger.info(f"  🏁 TRAINING SESSION COMPLETE")
        logger.info(f"  Duration: {session_duration:.0f}s")
        logger.info(f"  Messages: {total_messages_sent} sent, {total_responses_captured} captured")
        logger.info(f"  Threads: {total_threads}, Follow-ups: {total_follow_ups}")
        logger.info(f"  Avg Quality: {avg_overall_quality}/10")
        logger.info(f"{'='*50}")

    except Exception as e:
        logger.error(f"Training session failed: {e}")
        stats = TrainingStats(
            success=False,
            error=str(e),
            total_messages_sent=total_messages_sent,
            total_responses_captured=total_responses_captured,
            total_follow_ups=total_follow_ups,
            total_threads=total_threads,
            total_errors=total_errors,
            phases=phases_dict,
            quality_scores=quality_scores,
            session_duration=round(time.time() - session_start, 1),
            all_exchanges=all_exchanges,
            post_analysis=None,
            meta_learning=None,
            avg_overall_quality=0.0
        )
    finally:
        await client.disconnect()

    return stats


# ---------------------------------------------------------------------------
# Sync Wrapper (for Flask endpoints / Telegram commands)
# ---------------------------------------------------------------------------

def run_training(progress_callback=None) -> dict:
    """Synchronous wrapper for run_training_session."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(run_training_session(progress_callback))
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
    print("=" * 60)
    print("  SIFRA:MIND — Training Bot v2")
    print(f"  Target: @{RUMIK_BOT_USERNAME}")
    print(f"  Phases: {len(PHASE_CONFIG)}")
    print(f"  Total Messages: ~{sum(p['count'] for p in PHASE_CONFIG.values())}+")
    print("=" * 60)
    print()

    result = run_training()

    print()
    print("=" * 60)
    print("  RESULTS")
    print("=" * 60)

    # Print clean summary instead of raw JSON
    if result.get("success"):
        print(f"  Duration: {result.get('session_duration', 0):.0f} seconds")
        print(f"  Messages Sent: {result.get('total_messages_sent', 0)}")
        print(f"  Responses Captured: {result.get('total_responses_captured', 0)}")
        print(f"  Follow-ups Generated: {result.get('total_follow_ups', 0)}")
        print(f"  Threads Completed: {result.get('total_threads', 0)}")
        print(f"  Avg Quality: {result.get('avg_overall_quality', 0)}/10")
        print(f"  Errors: {result.get('total_errors', 0)}")
        print()
        for phase, pstats in result.get("phases", {}).items():
            print(f"  {PHASE_CONFIG[phase]['name']}: {pstats['responses_captured']}/{pstats['messages_sent']} | quality: {pstats.get('avg_quality', 0)}/10")
    else:
        print(f"  FAILED: {result.get('error', 'Unknown')}")

    print("=" * 60)
