# SIFRA:MIND — AI Companion System

A full-stack AI companion system featuring **Sifra Sharma** — a 25-year-old mass communication student from Nainital who speaks in natural Hinglish. The system includes a Python/Flask backend powering a Telegram bot and a React dashboard for neural observation.

## Architecture

```
├── backend/           Python/Flask API + Telegram bot
│   ├── app.py         Flask routes (webhook, REST API)
│   ├── sifra_brain.py Response generation + system prompt
│   ├── mesh_memory.py Memory extraction, recall, decay
│   ├── peek_context.py Context signal analysis
│   ├── telegram_handler.py Webhook processing
│   ├── supabase_client.py Database operations
│   └── scheduler.py   APScheduler jobs
│
├── frontend/          React + Vite dashboard (SIFRA:MIND)
│   └── src/
│       ├── components/ NeuralHeader, MemoryCore, LiveFeed, etc.
│       ├── hooks/      useSifraState, useMemories, useConversations
│       └── utils/      API helpers
```

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Supabase project
- Telegram bot (via @BotFather)
- Groq API key

### 1. Supabase Tables

Create these tables in your Supabase dashboard:

```sql
-- Memories
CREATE TABLE memories (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  content text NOT NULL,
  category text NOT NULL DEFAULT 'event',
  importance int NOT NULL DEFAULT 5,
  created_at timestamptz DEFAULT now(),
  last_referenced timestamptz DEFAULT now(),
  times_referenced int DEFAULT 0,
  decay_score float DEFAULT 1.0
);

-- Conversations
CREATE TABLE conversations (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  role text NOT NULL,
  content text NOT NULL,
  timestamp timestamptz DEFAULT now(),
  mood_detected text DEFAULT '',
  platform text DEFAULT 'telegram'
);

-- Sifra State (single row)
CREATE TABLE sifra_state (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  current_mood text DEFAULT 'neutral',
  energy_level int DEFAULT 7,
  last_active timestamptz DEFAULT now(),
  active_memories jsonb DEFAULT '[]',
  today_summary text DEFAULT '',
  personality_mode text DEFAULT 'normal'
);

-- Proactive Queue
CREATE TABLE proactive_queue (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  message text NOT NULL,
  scheduled_for timestamptz NOT NULL,
  sent boolean DEFAULT false,
  trigger_type text DEFAULT 'time_based'
);

-- Insert initial state row
INSERT INTO sifra_state (current_mood, energy_level, personality_mode)
VALUES ('neutral', 7, 'normal');
```

### 2. Environment Variables

Create a `.env` file in `/backend`:

```env
GROQ_API_KEY=your_groq_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
WEBHOOK_SECRET=your_random_secret_string
USER_TELEGRAM_ID=your_telegram_user_id
```

Create a `.env` file in `/frontend`:

```env
VITE_API_URL=http://localhost:5000
```

### 3. Backend Setup

```bash
cd backend
pip install -r requirements.txt
python app.py
```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### 5. Set Telegram Webhook

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-backend.vercel.app/webhook/telegram", "secret_token": "your_random_secret_string"}'
```

## Deployment (Vercel)

### Backend
```bash
cd backend
vercel --prod
```

### Frontend
```bash
cd frontend
npm run build
vercel --prod
```

Update `VITE_API_URL` in frontend to point to your deployed backend URL.

## Key Systems

- **Mesh Memory**: Extracts, stores, recalls, and naturally forgets memories like a human brain
- **Peek Context**: Reads time, mood signals, energy levels to adapt Sifra's personality mode
- **Proactive Messages**: Scheduled messages Sifra sends unprompted
- **Decay System**: Daily cron reduces memory strength — unused memories fade naturally

## Tech Stack

| Layer     | Technology                |
|-----------|---------------------------|
| Backend   | Python 3.11, Flask, Groq  |
| LLM       | Llama 3.3 70B Versatile   |
| Database  | Supabase (PostgreSQL)     |
| Chat      | Telegram Bot API          |
| Frontend  | React 19, Vite 6          |
| Styling   | Tailwind CSS 4            |
| Charts    | Recharts                  |
| Animation | Framer Motion             |
| Deploy    | Vercel                    |
