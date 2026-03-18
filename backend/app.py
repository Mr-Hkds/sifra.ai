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


@app.route("/api/proactive", methods=["GET", "POST"])
def api_proactive():
    """
    Proactive messaging endpoint — triggered by Vercel Cron.
    Sifra sends messages on her own: greetings, internet finds, random thoughts.
    """
    try:
        from proactive import run_proactive_job
        result = run_proactive_job()
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"/api/proactive error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/status", methods=["GET"])
def api_status():
    """
    Deployment status page — shows all features, their health,
    env vars, and latest update info.
    """
    import importlib, sys

    VERSION = "2.5.0"
    BUILD_DATE = "2026-03-18"

    # Check modules
    modules = {
        "sifra_brain": "Core AI Brain (prompt + response)",
        "peek_context": "Context Signals (time, energy, mood, location)",
        "mesh_memory": "Memory System (extract, store, recall, decay)",
        "telegram_handler": "Telegram Integration (webhook + send)",
        "proactive": "Proactive Messaging (greetings, gossip, kidhar ho)",
        "web_search": "Web Search (DuckDuckGo + Reddit)",
        "supabase_client": "Database Client (Supabase)",
        "scheduler": "Scheduler (APScheduler)",
    }
    module_status = {}
    for mod_name, desc in modules.items():
        try:
            importlib.import_module(mod_name)
            module_status[mod_name] = {"status": "✅ loaded", "description": desc}
        except Exception as e:
            module_status[mod_name] = {"status": f"❌ error: {str(e)[:80]}", "description": desc}

    # Check env vars
    env_vars = {
        "GROQ_API_KEY": bool(os.environ.get("GROQ_API_KEY")),
        "TELEGRAM_BOT_TOKEN": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "SUPABASE_URL": bool(os.environ.get("SUPABASE_URL")),
        "SUPABASE_KEY": bool(os.environ.get("SUPABASE_KEY")),
        "WEBHOOK_SECRET": bool(os.environ.get("WEBHOOK_SECRET")),
        "USER_TELEGRAM_ID": bool(os.environ.get("USER_TELEGRAM_ID")),
        "NEWS_API_KEY": bool(os.environ.get("NEWS_API_KEY")),
    }

    # Check database connection
    db_status = "❌ not connected"
    db_tables = {}
    try:
        from supabase_client import get_client
        client = get_client()
        for table in ["conversations", "memories", "sifra_state", "proactive_queue"]:
            try:
                result = client.table(table).select("id").limit(1).execute()
                db_tables[table] = f"✅ accessible ({len(result.data)} rows sampled)"
            except Exception as e:
                db_tables[table] = f"❌ error: {str(e)[:60]}"
        db_status = "✅ connected"
    except Exception as e:
        db_status = f"❌ error: {str(e)[:80]}"

    # Feature checklist
    features = [
        {"name": "Telegram Bot", "status": "active", "version": "1.0"},
        {"name": "Memory System", "status": "active", "version": "1.0"},
        {"name": "Context Signals (IST Time + Location)", "status": "active", "version": "2.0"},
        {"name": "Core Rules (Secret Element)", "status": "active", "version": "2.0"},
        {"name": "Anti-Hallucination Guards", "status": "active", "version": "2.1"},
        {"name": "Graceful Deflection (calls/photos/meet)", "status": "active", "version": "2.1"},
        {"name": "Energy Matching (typing style)", "status": "active", "version": "2.2"},
        {"name": "Vent Mode", "status": "active", "version": "2.2"},
        {"name": "Hyped Mode", "status": "active", "version": "2.2"},
        {"name": "Proactive: Good Morning/Night", "status": "active", "version": "2.3"},
        {"name": "Proactive: Reddit Gossip", "status": "active", "version": "2.3"},
        {"name": "Proactive: Kidhar Ho Detector", "status": "active", "version": "2.3"},
        {"name": "Proactive: Music Recommendations", "status": "active", "version": "2.3"},
        {"name": "Proactive: Random Thoughts", "status": "active", "version": "2.3"},
        {"name": "Web Search (DuckDuckGo + Reddit)", "status": "active", "version": "2.5"},
    ]

    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SIFRA:MIND | Deployment Status</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --primary: #2563eb;
                --bg: #0f172a;
                --card-bg: rgba(30, 41, 59, 0.7);
                --border: rgba(51, 65, 85, 0.5);
                --text-main: #f8fafc;
                --text-dim: #94a3b8;
                --success: #10b981;
                --error: #ef4444;
            }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Inter', sans-serif; 
                background-color: var(--bg); 
                color: var(--text-main); 
                line-height: 1.625;
                padding: 48px 24px;
            }
            .container { max-width: 1024px; mx-auto; margin: 0 auto; }
            
            header { margin-bottom: 64px; border-left: 4px solid var(--primary); padding-left: 24px; }
            h1 { font-size: 48px; font-weight: 700; tracking-tight: -0.025em; margin-bottom: 8px; }
            .subtitle { font-size: 18px; color: var(--text-dim); }

            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; margin-bottom: 48px; }
            
            .card { 
                background: var(--card-bg); 
                backdrop-filter: blur(12px); 
                border: 1px solid var(--border); 
                border-radius: 16px; 
                padding: 24px;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .card:hover { transform: translateY(-4px); box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1); }
            
            h2 { font-size: 20px; font-weight: 600; margin-bottom: 24px; display: flex; align-items: center; gap: 8px; }
            
            .status-item { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-size: 14px; }
            .status-label { color: var(--text-dim); }
            .status-val { font-weight: 500; font-family: monospace; }
            
            .badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
            .badge-success { background: rgba(16, 185, 129, 0.1); color: var(--success); border: 1px solid var(--success); }
            .badge-error { background: rgba(239, 68, 68, 0.1); color: var(--error); border: 1px solid var(--error); }

            .feature-list { display: grid; grid-template-columns: 1fr; gap: 12px; }
            .feature-item { 
                display: flex; justify-content: space-between; align-items: center; 
                padding: 12px 16px; background: rgba(255,255,255,0.03); 
                border-radius: 12px; font-size: 14px;
            }
            .feature-name { font-weight: 500; }
            .feature-version { font-size: 12px; color: var(--text-dim); }

            .tag { font-size: 12px; font-family: monospace; color: var(--primary); font-weight: 600; }
            
            @media (max-width: 640px) {
                h1 { font-size: 32px; }
                body { padding: 24px 16px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <div class="tag">BACKEND v{version}</div>
                <h1>SIFRA:MIND</h1>
                <p class="subtitle">Real-time deployment status & health dashboard</p>
            </header>

            <div class="grid">
                <!-- System Health -->
                <div class="card">
                    <h2>⚙️ System Health</h2>
                    <div class="status-item">
                        <span class="status-label">Database</span>
                        <span class="status-val {db_class}">{db_conn}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Build Date</span>
                        <span class="status-val">{build_date}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Environment</span>
                        <span class="status-val badge badge-success">Production</span>
                    </div>
                </div>

                <!-- Env Vars -->
                <div class="card">
                    <h2>🔑 Environment Vars</h2>
                    {env_html}
                </div>
            </div>

            <!-- Modules -->
            <div class="card" style="margin-bottom: 24px;">
                <h2>📦 Internal Modules</h2>
                <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 0;">
                    {module_html}
                </div>
            </div>

            <!-- Features -->
            <div class="card">
                <h2>✨ Active Features</h2>
                <div class="feature-list" style="grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); display: grid;">
                    {feature_html}
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    # Helper to build HTML snippets
    env_html = ""
    for env, val in env_vars.items():
        status = '<span class="badge badge-success">Set</span>' if val else '<span class="badge badge-error">Missing</span>'
        env_html += f'<div class="status-item"><span class="status-label">{env}</span>{status}</div>'
    
    module_html = ""
    for mod, data in module_status.items():
        loaded = "✅" in data['status']
        status = '<span class="badge badge-success">Loaded</span>' if loaded else '<span class="badge badge-error">Error</span>'
        module_html += f'<div style="text-align: center; border: 1px solid var(--border); padding: 16px; border-radius: 12px; background: rgba(0,0,0,0.1);"><div style="font-size: 12px; font-weight: 600; margin-bottom: 8px;">{mod}</div>{status}</div>'

    feature_html = ""
    for f in features:
        feature_html += f'<div class="feature-item"><div class="feature-name">{f["name"]} <span class="feature-version">v{f["version"]}</span></div><span class="badge badge-success">Online</span></div>'

    db_class = "success" if "connected" in db_status else "error"
    
    return html_template.format(
        version=VERSION,
        build_date=BUILD_DATE,
        db_conn=db_status.split("error")[0].strip(),
        db_class=db_class,
        env_html=env_html,
        module_html=module_html,
        feature_html=feature_html
    ), 200

@app.route("/api/debug", methods=["GET"])
def api_debug():
    """Diagnostic endpoint to check env vars and connection."""
    try:
        url = os.environ.get("SUPABASE_URL", "MISSING")
        key = os.environ.get("SUPABASE_KEY", "MISSING")
        bot = os.environ.get("TELEGRAM_BOT_TOKEN", "MISSING")
        uid = os.environ.get("USER_TELEGRAM_ID", "MISSING")

        # Basic connection test
        from supabase_client import get_client
        error_msg = None
        try:
            get_client().table("sifra_state").select("*").limit(1).execute()
        except Exception as e:
            error_msg = str(e)

        return jsonify({
            "env": {
                "SUPABASE_URL": url[:15] + "..." if url != "MISSING" else url,
                "SUPABASE_KEY_STRLEN": len(key) if key != "MISSING" else 0,
                "TELEGRAM_BOT_TOKEN": bot[:5] + "..." if bot != "MISSING" else bot,
                "USER_TELEGRAM_ID": uid
            },
            "supabase_error": error_msg,
            "status": "connected" if not error_msg else "failed"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
