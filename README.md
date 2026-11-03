# 🛰️ Telegram IPTV Scout & Auto-Poster Platform

A modern, high-performance automated Telegram platform built with **Python (Telethon MTProto + FastAPI)** and a sleek **Dark-Theme Web Control Dashboard**.

---

## 🌟 Key Capabilities

### 1. 📝 Content Template Manager with Spintax
- Create, edit, and organize multiple marketing templates.
- **Spintax Engine**: Use `{Hello|Hi|Hey}` and `{fast|freeze-free|reliable}` so every post sent by the bot has randomized phrasing, protecting your account from Telegram's repetitive message filters.
- **Dynamic Placeholders**: Automatically inserts `@{username}`, `{time}`, `{date}`, and `{random_id}`.
- **Live Spintax Tester**: Preview randomly generated output before broadcasting.

### 2. ⏱️ Automated Group Scheduler & Broadcaster
- Select one or multiple content templates (rotates between them).
- View all joined Telegram groups/channels and select target groups.
- Set posting intervals: **Seconds**, **Minutes**, or **Hours**.
- **Anti-Ban Safety Engine**: Configurable random delay (e.g., 15–45 seconds) between posts to mimic natural human behavior, with built-in automatic pause handling for Telegram `FloodWait`.
- Real-time campaign controls: Start, Pause, Stop, and Instant Test Post.

### 3. 🎯 IPTV Lead Scout & Keyword Scanner
- Enter public Telegram group links, @handles, or invite links (`t.me/+hash`).
- Deep history scan: Inspect past 100 to 1,000+ messages per group.
- **Pre-configured IPTV Keywords**:
  - `iptv`, `iptv subscription`, `reseller panel`, `rebrand app`
  - `smarters`, `tivimate`, `trial`, `m3u`, `supplier`, `credits`, `mag`, `xtream`
  - Add your own custom keywords on the fly.
- **⚡ Live Background Lead Monitor**: Listens to all incoming messages across joined groups in real-time, instantly capturing leads asking for IPTV.

### 4. 👥 Lead Management & Export
- Interactive table showing prospective buyers: Full name, `@username`, source group, matched keyword, full message snippet, and timestamp.
- 1-click **Direct Message (DM)** link opening Telegram straight to the lead.
- Status tracker: `New`, `Contacted`, `Converted`, `Ignored`.
- **1-Click CSV Export**: Download your full leads database into a spreadsheet for outreach or CRM.

---

## 🚀 How to Run the Platform

### Option 1: 1-Click Windows Launcher (Easiest)
Simply double-click:
```
run.bat
```
This automatically starts the backend server and opens your web browser to **`http://localhost:8000`**.

### Option 2: Run via Command Line
```powershell
C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🔑 Telegram API Setup (Takes 1-2 Minutes)

To allow the bot to post and scout on Telegram:
1. Open [my.telegram.org](https://my.telegram.org) in your browser.
2. Log in using your phone number and the confirmation code Telegram sends to your app.
3. Click on **"API development tools"**.
4. Create an application (App title: `ScoutBot`, Short name: `scoutbot`, Platform: `Desktop`).
5. Copy your **`api_id`** (numbers) and **`api_hash`** (letters and numbers).
6. In the ScoutBot Web Dashboard, go to **"Telegram Setup"**, paste your API credentials, enter your phone number, and click **"Send Login Code"**.
7. Enter the code Telegram sends you, and you're connected!

---

## 🛡️ Best Practices & Anti-Ban Tips
- **Use Spintax**: Never blast the exact same message across 20 groups. Always use `{option1|option2}` variations.
- **Safe Delays**: Keep the delay between groups to at least 15–30 seconds.
- **Warm Up New Accounts**: If using a brand-new Telegram account, join groups gradually and keep broadcasts to a moderate pace for the first few days.
