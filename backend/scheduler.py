"""
Scheduler — APScheduler jobs for decay and proactive messages.
Note: On Vercel serverless, APScheduler won't persist between invocations.
Use the /api/run_decay endpoint or Vercel Cron Jobs for production.
"""

import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from mesh_memory import run_decay_job
from supabase_client import get_pending_proactive_messages, mark_proactive_sent
from telegram_handler import send_telegram_message

logger = logging.getLogger(__name__)

USER_TELEGRAM_ID = os.environ.get("USER_TELEGRAM_ID", "")

_scheduler: BackgroundScheduler | None = None


def _daily_decay_task() -> None:
    """Run the memory decay job at 3 AM daily."""
    logger.info("Running daily memory decay job...")
    affected = run_decay_job()
    logger.info(f"Decay job complete: {affected} memories processed")


def _proactive_message_task() -> None:
    """Check for and send pending proactive messages every 5 minutes."""
    try:
        pending = get_pending_proactive_messages()
        if not pending:
            return

        for msg in pending:
            message_text = msg.get("message", "")
            message_id = msg.get("id", "")

            if not message_text or not message_id:
                continue

            if USER_TELEGRAM_ID:
                success = send_telegram_message(USER_TELEGRAM_ID, message_text)
                if success:
                    mark_proactive_sent(message_id)
                    logger.info(f"Sent proactive message: {message_id}")
                else:
                    logger.warning(f"Failed to send proactive message: {message_id}")
            else:
                logger.warning("USER_TELEGRAM_ID not set, skipping proactive message")

    except Exception as e:
        logger.error(f"Proactive message task failed: {e}")


def start_scheduler() -> None:
    """Initialize and start the background scheduler."""
    global _scheduler

    if _scheduler is not None:
        logger.info("Scheduler already running, skipping init")
        return

    _scheduler = BackgroundScheduler()

    # Daily decay at 3 AM UTC
    _scheduler.add_job(
        _daily_decay_task,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_decay",
        replace_existing=True,
        name="Daily Memory Decay",
    )

    # Proactive messages every 5 minutes
    _scheduler.add_job(
        _proactive_message_task,
        trigger=IntervalTrigger(minutes=5),
        id="proactive_messages",
        replace_existing=True,
        name="Proactive Message Checker",
    )

    _scheduler.start()
    logger.info("Scheduler started with decay and proactive message jobs")


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
