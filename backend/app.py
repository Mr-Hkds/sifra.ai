"""
SIFRA:MIND v3.0 Backend — Flask application.
Clean routes, minimal logic. All intelligence lives in the modules.
"""

import os
import logging
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_cors import CORS

from config import VERSION, BUILD_DATE

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"])

@app.before_request
def handle_options():
    """Globally catch OPTIONS requests before route matching to guarantee CORS passes."""
    if request.method == "OPTIONS":
        resp = app.make_default_options_response()
        headers = request.headers.get("Access-Control-Request-Headers", "Content-Type, Authorization")
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = headers
        return resp, 200


# ===================================================================
# TELEGRAM WEBHOOK
# ===================================================================

@app.route("/webhook/telegram", methods=["POST"])
def telegram_webhook():
    """Receive and process Telegram webhook updates."""
    from telegram_handler import process_update, verify_webhook_secret

    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not verify_webhook_secret(secret):
        return jsonify({"error": "Unauthorized"}), 403

    try:
        update = request.get_json(force=True)
        if not update:
            return jsonify({"error": "Empty payload"}), 400

        result = process_update(update)

        if not result.get("success"):
            logger.warning(f"Webhook issue: {result.get('error')}")

        return jsonify({"ok": True}), 200  # Always 200 to Telegram
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"ok": True}), 200


# ===================================================================
# REST API — Dashboard
# ===================================================================

@app.route("/api/state", methods=["GET"])
def api_state():
    from supabase_client import get_sifra_state
    try:
        return jsonify(get_sifra_state()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/memories", methods=["GET"])
def api_memories_get():
    from supabase_client import get_all_memories
    try:
        category = request.args.get("category")
        return jsonify(get_all_memories(category=category)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/memories", methods=["POST"])
def api_memories_post():
    from supabase_client import insert_memory
    try:
        data = request.get_json(force=True)
        content = data.get("content", "").strip()
        if not content:
            return jsonify({"error": "Content required"}), 400

        category = data.get("category", "core")
        valid = {"core", "emotional", "habit", "preference", "event"}
        if category not in valid:
            category = "core"

        importance = data.get("importance", 5)
        result = insert_memory(content, category, importance)
        return jsonify(result) if result else jsonify({"error": "Insert failed"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/memories/<memory_id>/delete", methods=["POST"])
def api_memories_delete(memory_id: str):
    from supabase_client import delete_memory
    try:
        return jsonify({"ok": delete_memory(memory_id)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/conversations", methods=["GET"])
def api_conversations():
    from supabase_client import get_conversations
    try:
        limit = min(request.args.get("limit", 50, type=int), 200)
        return jsonify(get_conversations(limit=limit)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mood_history", methods=["GET"])
def api_mood_history():
    from supabase_client import get_mood_history
    try:
        days = request.args.get("days", 7, type=int)
        return jsonify(get_mood_history(days=days)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================================================================
# RESET ENDPOINTS
# ===================================================================

@app.route("/api/reset/memories", methods=["POST"])
def api_reset_memories():
    from supabase_client import clear_all_memories
    try:
        count = clear_all_memories()
        return jsonify({"ok": True, "memories_cleared": count}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset/conversations", methods=["POST"])
def api_reset_conversations():
    from supabase_client import clear_all_conversations
    try:
        count = clear_all_conversations()
        return jsonify({"ok": True, "conversations_cleared": count}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset/full", methods=["POST"])
def api_reset_full():
    from supabase_client import full_reset
    try:
        result = full_reset()
        return jsonify({"ok": True, **result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================================================================
# CRON ENDPOINTS
# ===================================================================

@app.route("/api/run_decay", methods=["POST"])
def api_run_decay():
    from memory_engine import run_decay, consolidate_memories
    try:
        affected = run_decay()
        consolidated = consolidate_memories()
        return jsonify({
            "ok": True,
            "memories_decayed": affected,
            "memories_consolidated": consolidated,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/proactive", methods=["GET", "POST"])
def api_proactive():
    from proactive import run_proactive_job
    try:
        return jsonify(run_proactive_job()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/train", methods=["POST"])
def api_train():
    """Trigger an automated training session with Rumik."""
    import threading
    from training_bot import run_training

    def _run():
        result = run_training()
        logger.info(f"Training result: {result}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return jsonify({"ok": True, "message": "Training session started in background"}), 200


@app.route("/api/learnings", methods=["GET"])
def api_learnings():
    """Fetch observation learning stats, extracted patterns, AND memories."""
    from supabase_client import get_observation_stats, get_all_learnings, get_top_memories
    try:
        stats = get_observation_stats()
        learnings = get_all_learnings()
        memories = get_top_memories(limit=50)
        return jsonify({
            "ok": True,
            "stats": stats,
            "learnings": learnings,
            "memories": memories or []
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================================================================
# STATUS & HEALTH
# ===================================================================

@app.route("/api/status", methods=["GET"])
def api_status():
    """Deployment telemetry page — premium tech dashboard."""
    import importlib

    modules = {
        "brain": "Core AI Brain (layered prompts + quality gate)",
        "ai_client": "Multi-Provider AI Client (Gemini → Groq cascade)",
        "sentiment": "AI Sentiment Analysis (replaces keyword matching)",
        "context_engine": "Context Engine (time + mood + energy → mode)",
        "personality": "Personality System (identity + style + constraints)",
        "memory_engine": "Memory Engine (contextual retrieval + decay)",
        "quality_gate": "Quality Gate (anti-AI-slop filter)",
        "telegram_handler": "Telegram Integration (pipeline + group observer)",
        "proactive": "Proactive Messaging (greetings, gossip, kidhar ho)",
        "web_search": "Web Search (DuckDuckGo + Reddit)",
        "observation_engine": "Observation Learning (learn from other bots)",
        "supabase_client": "Database Client (Supabase)",
    }
    module_status = {}
    for mod_name, desc in modules.items():
        try:
            importlib.import_module(mod_name)
            module_status[mod_name] = {"status": "loaded", "description": desc}
        except Exception as e:
            module_status[mod_name] = {"status": f"error: {str(e)[:80]}", "description": desc}

    env_vars = {
        "GROQ_API_KEY": bool(os.environ.get("GROQ_API_KEY")),
        "GEMINI_API_KEY": bool(os.environ.get("GEMINI_API_KEY")),
        "TELEGRAM_BOT_TOKEN": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "SUPABASE_URL": bool(os.environ.get("SUPABASE_URL")),
        "SUPABASE_KEY": bool(os.environ.get("SUPABASE_KEY")),
        "WEBHOOK_SECRET": bool(os.environ.get("WEBHOOK_SECRET")),
        "USER_TELEGRAM_ID": bool(os.environ.get("USER_TELEGRAM_ID")),
        "NEWS_API_KEY": bool(os.environ.get("NEWS_API_KEY")),
    }

    db_status = "not connected"
    try:
        from supabase_client import get_client
        get_client().table("sifra_state").select("id").limit(1).execute()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)[:80]}"

    features = [
        "Multi-Provider AI (Gemini + Groq cascade)",
        "AI Sentiment Analysis (not keywords)",
        "Context-Aware Memory Retrieval",
        "Layered Prompt Architecture (7 layers)",
        "Response Quality Gate + Auto-Retry",
        "Anti-Repetition + Opener Variety Guard",
        "Sarcasm Detection",
        "Dynamic Personality Modes (8 modes)",
        "Proactive Messaging (7 types)",
        "Spontaneous Memory Recall",
        "AI-Powered Web Search (intent + query extraction)",
        "Memory Decay System",
        "Core Rules (Secret Element)",
        "Conversation Threading (18 msg context)",
        "Conversation Dynamics (pace, phase, length hints)",
        "Sifra Activity Generator (own life simulation)",
        "AI-Controlled Emoji Reactions",
        "AI-Controlled Sticker Sending",
        "Observation Learning (learn from Rumik.ai)",
        "Training Arena (silent group observer)",
        "High-Energy, Gossipy Messaging Style",
    ]

    # Build HTML
    ok = '<span class="font-mono text-[10px] text-emerald-500 tracking-widest">OK</span>'
    err = '<span class="font-mono text-[10px] text-zinc-500 tracking-widest">MISSING</span>'

    env_html = "".join(
        f'<div class="flex justify-between items-center py-1">'
        f'<span class="font-mono text-xs text-zinc-300">{k}</span>{ok if v else err}</div>'
        for k, v in env_vars.items()
    )

    mod_html = "".join(
        f'<div class="flex flex-col p-4 border border-zinc-800/40 bg-zinc-900/10 '
        f'hover:bg-zinc-900/40 transition-colors">'
        f'<div class="flex items-center gap-3 mb-2">'
        f'<span class="w-1.5 h-1.5 {"bg-emerald-500" if d["status"]=="loaded" else "bg-red-500"}"></span>'
        f'<span class="font-mono text-xs {"text-zinc-200" if d["status"]=="loaded" else "text-zinc-500"} '
        f'tracking-tight">{m}</span></div>'
        f'<p class="font-sans text-xs text-zinc-500 leading-relaxed">{d["description"]}</p></div>'
        for m, d in module_status.items()
    )

    feat_html = "".join(
        f'<div class="flex items-center gap-3 py-2 border-b border-zinc-800/30 group">'
        f'<span class="text-emerald-600 group-hover:text-emerald-400 transition-colors text-xs">▸</span>'
        f'<span class="font-sans text-sm font-medium text-zinc-300 '
        f'group-hover:text-zinc-100 transition-colors">{f}</span></div>'
        for f in features
    )

    db_color = "text-emerald-500" if "connected" in db_status else "text-red-400"

    html = f"""<!DOCTYPE html>
<html lang="en" class="antialiased">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SIFRA:MIND | Telemetry v{VERSION}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{
            background: #050505;
            color: #e4e4e7;
            font-family: 'Inter', sans-serif;
            background-image: radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px);
            background-size: 24px 24px;
        }}
        .tech-card {{
            background: rgba(24,24,27,0.4);
            border: 1px solid rgba(63,63,70,0.2);
            box-shadow: inset 0 1px 0 0 rgba(255,255,255,0.02);
        }}
        .pulse {{ animation: pulse 2s cubic-bezier(0.4,0,0.6,1) infinite; }}
        @keyframes pulse {{ 0%,100% {{ opacity:1 }} 50% {{ opacity:.4 }} }}
    </style>
</head>
<body class="min-h-screen p-6 md:p-16 lg:p-24">
    <div class="max-w-6xl mx-auto flex flex-col gap-16">
        <header class="flex flex-col gap-4">
            <div class="flex items-center gap-4">
                <div class="h-1 w-12 bg-emerald-500"></div>
                <span class="font-mono text-[10px] tracking-[0.2em] text-zinc-500 uppercase">System Telemetry</span>
            </div>
            <h1 class="text-4xl md:text-5xl font-semibold tracking-tighter text-zinc-100">SIFRA:MIND</h1>
            <div class="flex items-center gap-6 mt-2">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 pulse"></span>
                <span class="font-mono text-xs text-zinc-400">v{VERSION} — {BUILD_DATE}</span>
            </div>
        </header>
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div class="lg:col-span-5 flex flex-col gap-6">
                <div class="tech-card rounded-lg p-6">
                    <h2 class="font-mono text-xs font-semibold tracking-widest text-zinc-500 uppercase mb-8">Infrastructure</h2>
                    <div class="flex flex-col gap-5">
                        <div class="flex justify-between items-baseline border-b border-zinc-800/50 pb-4">
                            <span class="text-sm text-zinc-400">Database</span>
                            <span class="font-mono text-sm {db_color}">{db_status}</span>
                        </div>
                        <div class="flex justify-between items-baseline border-b border-zinc-800/50 pb-4">
                            <span class="text-sm text-zinc-400">AI Provider</span>
                            <span class="font-mono text-sm text-zinc-200">{'Gemini + Groq' if os.environ.get('GEMINI_API_KEY') else 'Groq'}</span>
                        </div>
                        <div class="flex justify-between items-baseline">
                            <span class="text-sm text-zinc-400">Architecture</span>
                            <span class="font-mono text-xs text-zinc-500 border border-zinc-800 px-2 py-0.5">v3 REWRITE</span>
                        </div>
                    </div>
                </div>
                <div class="tech-card rounded-lg p-6">
                    <h2 class="font-mono text-xs font-semibold tracking-widest text-zinc-500 uppercase mb-8">API Keys</h2>
                    {env_html}
                </div>
            </div>
            <div class="lg:col-span-7 flex flex-col gap-6">
                <div class="tech-card rounded-lg p-6">
                    <h2 class="font-mono text-xs font-semibold tracking-widest text-zinc-500 uppercase mb-8">Modules</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">{mod_html}</div>
                </div>
                <div class="tech-card rounded-lg p-6">
                    <div class="flex justify-between items-center mb-8">
                        <h2 class="font-mono text-xs font-semibold tracking-widest text-zinc-500 uppercase">Capabilities</h2>
                        <span class="font-mono text-xs text-zinc-600 border border-zinc-800 px-2 py-0.5">{len(features)}</span>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-x-8">{feat_html}</div>
                </div>
            </div>
        </div>
        <div class="tech-card rounded-lg p-6">
            <div class="flex items-center gap-4 mb-8">
                <div class="h-1 w-8 bg-red-500"></div>
                <h2 class="font-mono text-xs font-semibold tracking-widest text-zinc-500 uppercase">Factory Reset</h2>
            </div>
            <p class="text-sm text-zinc-400 mb-6 leading-relaxed max-w-xl">
                Wipe Sifra's memory and start fresh. This is irreversible — all memories and conversations will be permanently deleted.
            </p>
            <div class="flex flex-wrap gap-4">
                <button onclick="resetAction('memories')" id="btn-memories"
                    class="px-5 py-2.5 rounded-lg border border-zinc-700 text-sm font-medium text-zinc-300
                    hover:bg-zinc-800 hover:border-zinc-600 hover:text-zinc-100
                    active:scale-95 transition-all duration-200 cursor-pointer">
                    Clear Memories
                </button>
                <button onclick="resetAction('conversations')" id="btn-conversations"
                    class="px-5 py-2.5 rounded-lg border border-zinc-700 text-sm font-medium text-zinc-300
                    hover:bg-zinc-800 hover:border-zinc-600 hover:text-zinc-100
                    active:scale-95 transition-all duration-200 cursor-pointer">
                    Clear Conversations
                </button>
                <button onclick="resetAction('full')" id="btn-full"
                    class="px-5 py-2.5 rounded-lg border border-red-900/50 bg-red-950/30 text-sm font-medium text-red-400
                    hover:bg-red-950/60 hover:border-red-700 hover:text-red-300
                    active:scale-95 transition-all duration-200 cursor-pointer">
                    ⚠ Full Factory Reset
                </button>
            </div>
            <div id="reset-status" class="mt-4 hidden">
                <p id="reset-msg" class="text-sm font-mono"></p>
            </div>
        </div>
        <footer class="text-xs font-mono text-zinc-600 border-t border-zinc-800/50 pt-8 flex justify-between">
            <span>SIFRA:MIND Core — v{VERSION}</span>
            <span>{BUILD_DATE}</span>
        </footer>
    </div>
    <script>
    async function resetAction(type) {{
        const labels = {{
            memories: 'Clear ALL memories? Sifra will forget everything about you.',
            conversations: 'Clear ALL conversation history? The chat log will be wiped.',
            full: 'FULL FACTORY RESET — This wipes ALL memories, conversations, and resets Sifra to default state. Are you absolutely sure?'
        }};
        if (!confirm(labels[type])) return;
        if (type === 'full' && !confirm('Last chance. This cannot be undone. Proceed?')) return;

        const btn = document.getElementById('btn-' + type);
        const statusDiv = document.getElementById('reset-status');
        const msgP = document.getElementById('reset-msg');

        btn.disabled = true;
        btn.textContent = 'Processing...';
        statusDiv.classList.remove('hidden');
        msgP.className = 'text-sm font-mono text-zinc-400';
        msgP.textContent = '⏳ Working...';

        try {{
            const resp = await fetch('/api/reset/' + type, {{ method: 'POST' }});
            const data = await resp.json();
            if (data.ok) {{
                msgP.className = 'text-sm font-mono text-emerald-400';
                if (type === 'full') {{
                    msgP.textContent = `✅ Factory reset complete — ${{data.memories_cleared}} memories, ${{data.conversations_cleared}} conversations cleared.`;
                }} else if (type === 'memories') {{
                    msgP.textContent = `✅ Cleared ${{data.memories_cleared}} memories.`;
                }} else {{
                    msgP.textContent = `✅ Cleared ${{data.conversations_cleared}} conversations.`;
                }}
            }} else {{
                throw new Error(data.error || 'Unknown error');
            }}
        }} catch (e) {{
            msgP.className = 'text-sm font-mono text-red-400';
            msgP.textContent = '❌ Failed: ' + e.message;
        }} finally {{
            btn.disabled = false;
            btn.textContent = type === 'full' ? '⚠ Full Factory Reset' : type === 'memories' ? 'Clear Memories' : 'Clear Conversations';
        }}
    }}
    </script>
</body>
</html>"""

    return html, 200


@app.route("/api/debug", methods=["GET"])
def api_debug():
    """Diagnostic endpoint."""
    url = os.environ.get("SUPABASE_URL", "MISSING")
    key = os.environ.get("SUPABASE_KEY", "MISSING")
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "MISSING")
    uid = os.environ.get("USER_TELEGRAM_ID", "MISSING")
    gemini = "SET" if os.environ.get("GEMINI_API_KEY") else "NOT SET"

    error_msg = None
    try:
        from supabase_client import get_client
        get_client().table("sifra_state").select("*").limit(1).execute()
    except Exception as e:
        error_msg = str(e)

    return jsonify({
        "version": VERSION,
        "env": {
            "SUPABASE_URL": url[:15] + "..." if url != "MISSING" else url,
            "SUPABASE_KEY_LEN": len(key) if key != "MISSING" else 0,
            "TELEGRAM_BOT_TOKEN": bot[:5] + "..." if bot != "MISSING" else bot,
            "USER_TELEGRAM_ID": uid,
            "GEMINI_API_KEY": gemini,
        },
        "supabase_error": error_msg,
        "status": "connected" if not error_msg else "failed",
    }), 200


@app.route("/health", methods=["GET"])
def health():
    from supabase_client import get_sifra_state
    try:
        state = get_sifra_state()
        return jsonify({
            "status": "alive",
            "version": VERSION,
            "sifra_mood": state.get("current_mood", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 200
    except Exception:
        return jsonify({"status": "alive", "version": VERSION}), 200


@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "name": "SIFRA:MIND Backend",
        "version": VERSION,
        "status": "operational",
        "architecture": "v3 — Multi-provider AI, layered prompts, quality gate",
    }), 200


# ===================================================================
# Run
# ===================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
