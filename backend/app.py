"""
SIFRA:MIND Backend — Flask application with all API routes.
Handles Telegram webhook, REST API for the dashboard, and decay cron.
"""

import os
import json
import logging
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS

from telegram_handler import process_telegram_update, verify_webhook_secret
from supabase_client import (
    get_sifra_state,
    get_all_memories,
    get_conversations,
    get_mood_history,
    insert_memory,
    delete_memory,
)
from mesh_memory import run_decay_job
from scheduler import start_scheduler

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"])

# Start scheduler (will be a no-op on subsequent serverless invocations)
try:
    start_scheduler()
except Exception as e:
    logger.warning(f"Scheduler startup skipped (expected in serverless): {e}")


# ===================================================================
# TELEGRAM WEBHOOK
# ===================================================================

@app.route("/webhook/telegram", methods=["POST"])
def telegram_webhook():
    """Receive and process Telegram webhook updates."""
    # Verify webhook secret
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not verify_webhook_secret(secret_token):
        return jsonify({"error": "Unauthorized"}), 403

    try:
        update = request.get_json(force=True)
        if not update:
            return jsonify({"error": "Empty payload"}), 400

        result = process_telegram_update(update)

        if result.get("success"):
            return jsonify({"ok": True}), 200
        else:
            logger.warning(f"Webhook processing issue: {result.get('error')}")
            return jsonify({"ok": True}), 200  # Return 200 to Telegram anyway
    except Exception as e:
        logger.error(f"Webhook handler error: {e}")
        return jsonify({"ok": True}), 200  # Always return 200 to Telegram


# ===================================================================
# REST API — Dashboard endpoints
# ===================================================================

@app.route("/api/state", methods=["GET"])
def api_state():
    """Return Sifra's current state for the dashboard."""
    try:
        state = get_sifra_state()
        return jsonify(state), 200
    except Exception as e:
        logger.error(f"/api/state error: {e}")
        return jsonify({"error": "Failed to fetch state"}), 500


@app.route("/api/memories", methods=["GET"])
def api_memories_get():
    """Return all memories, optionally filtered by category."""
    try:
        category = request.args.get("category")
        memories = get_all_memories(category=category)
        return jsonify(memories), 200
    except Exception as e:
        logger.error(f"/api/memories GET error: {e}")
        return jsonify({"error": "Failed to fetch memories"}), 500


@app.route("/api/memories", methods=["POST"])
def api_memories_post():
    """Manually add a memory from the dashboard."""
    try:
        data = request.get_json(force=True)
        content = data.get("content", "").strip()
        category = data.get("category", "core")
        importance = data.get("importance", 5)

        if not content:
            return jsonify({"error": "Content is required"}), 400

        valid_categories = {"core", "emotional", "habit", "preference", "event"}
        if category not in valid_categories:
            category = "core"

        result = insert_memory(content, category, importance)
        if result:
            return jsonify(result), 201
        return jsonify({"error": "Failed to insert memory"}), 500
    except Exception as e:
        logger.error(f"/api/memories POST error: {e}")
        return jsonify({"error": "Failed to add memory"}), 500


@app.route("/api/memories/<memory_id>/delete", methods=["POST"])
def api_memories_delete(memory_id: str):
    """Delete a memory by ID."""
    try:
        success = delete_memory(memory_id)
        if success:
            return jsonify({"ok": True}), 200
        return jsonify({"error": "Failed to delete memory"}), 500
    except Exception as e:
        logger.error(f"/api/memories DELETE error: {e}")
        return jsonify({"error": "Failed to delete memory"}), 500


@app.route("/api/conversations", methods=["GET"])
def api_conversations():
    """Return recent conversations."""
    try:
        limit = request.args.get("limit", 50, type=int)
        limit = min(limit, 200)  # Cap at 200
        conversations = get_conversations(limit=limit)
        return jsonify(conversations), 200
    except Exception as e:
        logger.error(f"/api/conversations error: {e}")
        return jsonify({"error": "Failed to fetch conversations"}), 500


@app.route("/api/mood_history", methods=["GET"])
def api_mood_history():
    """Return mood data grouped by day for the last 7 days."""
    try:
        days = request.args.get("days", 7, type=int)
        history = get_mood_history(days=days)
        return jsonify(history), 200
    except Exception as e:
        logger.error(f"/api/mood_history error: {e}")
        return jsonify({"error": "Failed to fetch mood history"}), 500


@app.route("/api/run_decay", methods=["POST"])
def api_run_decay():
    """
    Manually trigger the memory decay job.
    Use this with Vercel Cron Jobs for production.
    """
    try:
        affected = run_decay_job()
        return jsonify({"ok": True, "memories_affected": affected}), 200
    except Exception as e:
        logger.error(f"/api/run_decay error: {e}")
        return jsonify({"error": "Decay job failed"}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    try:
        state = get_sifra_state()
        return jsonify({
            "status": "alive",
            "sifra_mood": state.get("current_mood", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 200
    except Exception:
        return jsonify({"status": "alive", "sifra_mood": "unknown"}), 200


# ===================================================================
# Root
# ===================================================================

@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "name": "SIFRA:MIND Backend",
        "version": "1.0.0",
        "status": "operational",
    }), 200


# ===================================================================
# Run
# ===================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
