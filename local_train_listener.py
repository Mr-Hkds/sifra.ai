import os
import sys
import time
import asyncio
from dotenv import load_dotenv

# Ensure we're running from the project root
if os.path.isdir("backend"):
    os.chdir("backend")
    sys.path.insert(0, os.getcwd())

load_dotenv("../.env")  # if .env is in root
load_dotenv(".env")     # if .env is in backend

from supabase_client import get_client
from telegram_handler import send_message, USER_TELEGRAM_ID
from training_bot import run_training, PHASE_CONFIG

def _progress(phase_name, message):
    if USER_TELEGRAM_ID:
        try:
             send_message(USER_TELEGRAM_ID, f"⏳ {phase_name}: {message}")
        except Exception:
             pass

def execute_local_training():
    print(f"[{time.strftime('%X')}] 🚀 Local Training Hook Triggered!")
    
    if USER_TELEGRAM_ID:
        send_message(
            USER_TELEGRAM_ID, 
            "💻 <b>Local Protocol Engaged!</b>\nYour laptop has successfully intercepted the signal and started executing the multi-phase auto-trainer right now."
        )

    # Run the training synchronously (takes ~8-12 minutes)
    result = run_training(progress_callback=_progress)
    
    if not USER_TELEGRAM_ID:
        print("Training finished.")
        return

    if result.get("success"):
        duration = result.get('session_duration', 0)
        mins = int(duration // 60)
        secs = int(duration % 60)

        msg = (
            f"✅ <b>Training Session Complete! (Local)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⏱ Duration: <b>{mins}m {secs}s</b>\n"
            f"📤 Messages Sent: <b>{result.get('total_messages_sent', 0)}</b>\n"
            f"📥 Responses Captured: <b>{result.get('total_responses_captured', 0)}</b>\n"
            f"🔁 Follow-ups Generated: <b>{result.get('total_follow_ups', 0)}</b>\n"
            f"🧵 Threads Completed: <b>{result.get('total_threads', 0)}</b>\n"
            f"⭐ Avg Quality: <b>{result.get('avg_overall_quality', 0)}/10</b>\n"
            f"❌ Errors: {result.get('total_errors', 0)}\n\n"
        )

        # Per-phase breakdown
        msg += "<b>Phase Breakdown:</b>\n"
        phases = result.get("phases", {})
        for phase_key, pstats in phases.items():
            phase_name = PHASE_CONFIG.get(phase_key, {}).get("name", phase_key)
            captured = pstats.get("responses_captured", 0)
            sent = pstats.get("messages_sent", 0)
            quality = pstats.get("avg_quality", 0.0)
            follow = pstats.get("follow_ups", 0)
            msg += f"  {phase_name}: {captured}/{sent}"
            if follow:
                msg += f" (+{follow} follow-ups)"
            msg += f" — quality: {quality}/10\n"

        # Post-training analysis
        post = result.get("post_analysis", {})
        if post and not post.get("error"):
            msg += f"\n🧠 <b>Deep Analysis:</b> {post.get('patterns_found', 0)} new patterns extracted"

        meta = result.get("meta_learning", {})
        if meta and meta.get("directives_generated", 0) > 0:
            msg += f"\n🎯 <b>Meta-Learning:</b> {meta.get('directives_generated', 0)} behavioral directives generated"

        msg += "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
        msg += "\n<i>Use /sifra_learn_status to see what I learned!</i>"
    else:
        err = result.get('error', 'Unknown error')
        msg = f"❌ <b>Local Training Failed</b>\n{err}"

    send_message(USER_TELEGRAM_ID, msg)
    print(f"[{time.strftime('%X')}] 🏁 Training Complete. Waiting for next signal...")

def start_listening():
    print("==================================================")
    print(" SIFRA:MIND Local Train Listener ")
    print(" Waiting for /sifra_train command from Telegram...")
    print(" (Keep this window open in the background)")
    print("==================================================")
    
    supabase = get_client()

    while True:
        try:
            # Check DB for the stealth trigger
            res = supabase.table("memories").select("id").eq("content", "SYSTEM_FLAG_TRIGGER_AUTO_TRAIN").execute()
            if res.data:
                # Destroy the flag instantly so we don't infinitely trigger it
                for record in res.data:
                    supabase.table("memories").delete().eq("id", record["id"]).execute()
                
                # Execute the heavy 12-minute payload
                execute_local_training()
                
        except Exception as e:
            print(f"Database sync issue... waiting 5s. ({str(e)[:50]})")

        time.sleep(5)

if __name__ == "__main__":
    start_listening()
