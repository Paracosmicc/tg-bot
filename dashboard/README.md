# Vaidehi Bot — Web Control Panel (Vercel Frontend)

This directory contains the standalone dark-mode Web Control Panel for Vaidehi Bot.

---

## 🚀 How to Deploy to Vercel (1-Click)

### Method 1: Using Vercel CLI
1. Open your terminal in this repository:
   ```bash
   cd dashboard
   npx vercel
   ```
2. Follow the quick prompts to deploy directly.

---

### Method 2: Via Vercel Web Dashboard (GitHub Connected)
1. Go to [Vercel Dashboard](https://vercel.com/new).
2. Import your GitHub repository (`tg-bot` or `tg_bot`).
3. In **Root Directory**, click **Edit** and choose `dashboard`.
4. Click **Deploy**!

---

## ⚙️ Configuration & Features

* **Default Backend URL**: Pre-configured to connect to `https://tg-bot-9ulh.onrender.com`.
* **Password Authentication**: Secured with your `DASHBOARD_PASSWORD` (default: `vaidehi123`, or set in Render `.env`).
* **Photo Manager**: Upload & preview selfies without SSH.
* **Voice Notes Manager**: Upload `.ogg` audio clips & listen live in browser.
* **Broadcast Center**: Live Telegram phone message simulator + audience selector.
* **Direct Messenger**: Send proxy messages as Vaidehi directly to groups or chat IDs.
