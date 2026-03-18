# SIFRA:MIND — Complete Setup Guide

This guide will walk you through setting up every single component of the SIFRA system from start to finish.

## Phase 1: Accounts & API Keys

### 1. Groq API (Sifra's Brain)
1. Go to [console.groq.com](https://console.groq.com/).
2. Create an account or log in.
3. Go to **API Keys** on the left menu.
4. Click **Create API Key**. Name it `SIFRA`.
5. Copy this key and save it somewhere safe. You won't be able to see it again.

### 2. Telegram Bot (Sifra's Chat Interface)
1. Open Telegram and search for `@BotFather`.
2. Send the command `/newbot`.
3. Give it a name (e.g., `Sifra`).
4. Give it a username (e.g., `sifra_companion_bot`). It must end in "bot".
5. BotFather will give you an **HTTP API Token**. Copy this token.
6. Now, search for `@userinfobot` in Telegram and click Start. It will send you your `Id` (a number like `123456789`). This is your `USER_TELEGRAM_ID`. Copy it.
7. Go back to your bot, click its name, and send it a `/start` message just to open the chat history.

### 3. Supabase (Sifra's Memory Database)
1. Go to [supabase.com](https://supabase.com/) and create an account.
2. Click **New Project**. Name it `SifraMind` and create a secure database password. Select a region close to you (e.g., Mumbai if you're in India).
3. Wait for the database to provision (takes about 1-2 minutes).
4. Go to **Project Settings** (the gear icon on the left) -> **API**.
5. Copy the **Project URL** (`SUPABASE_URL`) and the **anon `public` key** (`SUPABASE_KEY`).
6. Go to the **SQL Editor** on the left menu.
7. Click **New Query** and paste the entire SQL block from the `README.md` file (the one that creates the `memories`, `conversations`, `sifra_state`, and `proactive_queue` tables).
8. Click **Run**. You should see "Success".

---

## Phase 2: Local Testing

### Backend Configuration
1. Open the `/backend` folder.
2. Create a file named `.env` and paste your keys like this:
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
TELEGRAM_BOT_TOKEN=123456:YOUR_TELEGRAM_BOT_TOKEN_HERE
USER_TELEGRAM_ID=your_numeric_telegram_id_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=ey_your_supabase_anon_key_here
WEBHOOK_SECRET=my_super_secret_string_123  # Make up a random string
```

### Frontend Configuration
1. Open the `/frontend` folder.
2. Create a file named `.env` and put:
```env
VITE_API_URL=http://localhost:5000
```

---

## Phase 3: Deployment (Vercel)

### 1. GitHub Repository
1. Open a terminal in the `Sifra.ai` folder.
2. Run these commands to push to a private GitHub repo:
```bash
git init
git add .
git commit -m "Initial commit of SIFRA:MIND"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

### 2. Deploying the Backend
1. Go to [vercel.com](https://vercel.com/) and log in with GitHub.
2. Click **Add New** -> **Project**.
3. Import your `Sifra.ai` repository.
4. **Important Framework Settings**:
   - For **Framework Preset**, select **Other**.
   - For **Root Directory**, click "Edit" and choose `backend`.
5. Expand **Environment Variables** and add ALL the variables from your backend `.env` file (GROQ_API_KEY, TELEGRAM_BOT_TOKEN, etc.).
6. Click **Deploy**.
7. Once deployed, copy the Vercel URL (e.g., `https://sifra-backend-abc.vercel.app`).

### 3. Connecting Telegram to the Deployed Backend
You now need to tell Telegram to send messages to your Vercel URL.
1. Open your browser or a terminal.
2. Replace the `<YOUR_TOKEN>`, `<YOUR_VERCEL_URL>`, and `<YOUR_WEBHOOK_SECRET>` in this URL, and visit it in your browser (or run via curl):
```
https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook?url=<YOUR_VERCEL_URL>/webhook/telegram&secret_token=<YOUR_WEBHOOK_SECRET>
```
*Example: `https://api.telegram.org/bot1234:ABCDEF/setWebhook?url=https://sifra-backend.vercel.app/webhook/telegram&secret_token=my_super_secret_string_123`*
3. You should see `{"ok":true,"result":true,"description":"Webhook was set"}`.

### 4. Deploying the Frontend (Dashboard)
1. Go back to Vercel and click **Add New** -> **Project**.
2. Import the SAME `Sifra.ai` repository again.
3. **Important Framework Settings**:
   - For **Framework Preset**, select **Vite**.
   - For **Root Directory**, choose `frontend`.
4. Expand **Environment Variables** and add:
   - Name: `VITE_API_URL`
   - Value: The URL of your deployed backend (e.g., `https://sifra-backend-abc.vercel.app`) - **Do not add a trailing slash**.
5. Click **Deploy**.
6. Once deployed, click the URL! You now have your live neural observation dashboard.

---

## Final Verification
1. Send a message to Sifra on Telegram (e.g., "hi sifra kya chal raha hai?").
2. Check your phone — Sifra should respond within 3-4 seconds!
3. Open your Vercel Dashboard URL on your computer.
4. You should see Sifra's mood shift, the conversation log update, and memory extraction happen automatically in the cards on the left.

Welcome to SIFRA:MIND. System Operational.
