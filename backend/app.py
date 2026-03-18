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

    # Load Tailwind CSS via CDN for the premium look
    html_template = """
    <!DOCTYPE html>
    <html lang="en" class="antialiased">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SIFRA:MIND | Deployment Status</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {
                theme: {
                    extend: {
                        fontFamily: {
                            sans: ['Inter', 'sans-serif'],
                            mono: ['JetBrains Mono', 'monospace'],
                        },
                        colors: {
                            brand: {
                                500: '#3b82f6', // blue-500
                                900: '#1e3a8a', // blue-900
                            }
                        }
                    }
                }
            }
        </script>
        <style>
            body { background-color: #0f172a; color: #f8fafc; } /* slate-900 bg, slate-50 text */
            .glass-card {
                background: rgba(30, 41, 59, 0.5); /* slate-800 w/ opacity */
                backdrop-filter: blur(12px);
                border: 1px solid rgba(51, 65, 85, 0.8); /* slate-700 */
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            }
        </style>
    </head>
    <body class="min-h-screen p-4 md:p-12 lg:p-24 selection:bg-brand-500 selection:text-white">
        <div class="max-w-5xl mx-auto">
            
            <!-- Header Section -->
            <header class="mb-16 border-l-4 border-brand-500 pl-6 py-1">
                <div class="flex items-center gap-3 mb-3">
                    <span class="font-mono text-xs font-semibold px-2 py-1 rounded bg-brand-900 border border-brand-500 text-brand-500 uppercase tracking-widest">
                        System Diagnostics
                    </span>
                    <span class="font-mono text-xs text-slate-400">v{version}</span>
                </div>
                <h1 class="text-4xl md:text-5xl font-bold tracking-tight text-white mb-2">SIFRA:MIND Core</h1>
                <p class="text-lg text-slate-400 max-w-2xl">Real-time telemetry and deployment health metrics.</p>
            </header>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
                
                <!-- System Health Card -->
                <div class="glass-card rounded-2xl p-6 md:p-8 transition-all duration-300 hover:border-slate-500">
                    <h2 class="text-xl font-semibold mb-6 flex items-center gap-3">
                        <svg class="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01"></path></svg>
                        System Health
                    </h2>
                    <div class="space-y-4">
                        <div class="flex justify-between items-center pb-4 border-b border-slate-700/50">
                            <span class="text-sm text-slate-400 font-medium">Database Connection</span>
                            <span class="font-mono text-sm {db_class}">{db_conn}</span>
                        </div>
                        <div class="flex justify-between items-center pb-4 border-b border-slate-700/50">
                            <span class="text-sm text-slate-400 font-medium">Last Deployment</span>
                            <span class="font-mono text-sm text-slate-200">{build_date}</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-sm text-slate-400 font-medium">Environment</span>
                            <span class="px-2.5 py-1 text-xs font-semibold rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Production</span>
                        </div>
                    </div>
                </div>

                <!-- Environment Vars Card -->
                <div class="glass-card rounded-2xl p-6 md:p-8 transition-all duration-300 hover:border-slate-500">
                    <h2 class="text-xl font-semibold mb-6 flex items-center gap-3">
                        <svg class="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"></path></svg>
                        Environment Variables
                    </h2>
                    <div class="space-y-3">
                        {env_html}
                    </div>
                </div>
            </div>

            <!-- Internal Modules -->
            <div class="glass-card rounded-2xl p-6 md:p-8 mb-12 transition-all duration-300 hover:border-slate-500">
                <h2 class="text-xl font-semibold mb-8 flex items-center gap-3">
                    <svg class="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                    Internal Modules
                </h2>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {module_html}
                </div>
            </div>

            <!-- Active Features Dashboard -->
            <div class="glass-card rounded-2xl p-6 md:p-8 transition-all duration-300 hover:border-slate-500">
                <div class="flex justify-between items-center mb-8">
                    <h2 class="text-xl font-semibold flex items-center gap-3">
                        <svg class="w-5 h-5 text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                        Active Features
                    </h2>
                    <span class="text-sm text-slate-400 font-mono">Total: {total_features}</span>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {feature_html}
                </div>
            </div>

            <!-- Footer -->
            <footer class="mt-16 text-center text-sm text-slate-500 font-mono">
                Running continuously since {build_date}
            </footer>
        </div>
    </body>
    </html>
    """

    # Helper styles for components
    success_badge = '<span class="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Set</span>'
    error_badge = '<span class="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded bg-red-500/10 text-red-400 border border-red-500/20">Missing</span>'
    
    env_html = ""
    for env, val in env_vars.items():
        status = success_badge if val else error_badge
        env_html += f'<div class="flex justify-between items-center"><span class="font-mono text-sm text-slate-300">{env}</span>{status}</div>'
    
    module_html = ""
    for mod, data in module_status.items():
        loaded = "✅" in data['status']
        status_dot = '<span class="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></span>' if loaded else '<span class="w-2 h-2 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]"></span>'
        module_html += f'<div class="flex flex-col p-4 rounded-xl bg-slate-800/50 border border-slate-700/50"><div class="flex items-center gap-2 mb-2">{status_dot}<span class="font-mono text-sm font-medium text-slate-200">{mod}</span></div><p class="text-xs text-slate-500 leading-snug">{data["description"]}</p></div>'

    feature_html = ""
    for f in features:
        feature_html += f'<div class="flex justify-between items-center p-4 rounded-xl bg-slate-800/30 border border-slate-700/30 hover:bg-slate-800/50 transition-colors"><div class="flex flex-col"><span class="text-sm font-medium text-slate-200">{f["name"]}</span><span class="font-mono text-xs text-slate-500 mt-0.5">v{f["version"]}</span></div><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span></div>'

    db_class = "text-emerald-400" if "connected" in db_status else "text-red-400"
    
    
    # Use .replace instead of .format to avoid CSS brace conflicts
    content = html_template.replace("{version}", VERSION) \
                           .replace("{build_date}", BUILD_DATE) \
                           .replace("{db_conn}", db_status.split("error")[0].strip()) \
                           .replace("{db_class}", db_class) \
                           .replace("{env_html}", env_html) \
                           .replace("{module_html}", module_html) \
                           .replace("{feature_html}", feature_html)

    return content, 200

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
