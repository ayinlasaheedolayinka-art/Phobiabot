import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "scout_bot.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Templates table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # Campaigns / Scheduler table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        template_ids TEXT NOT NULL, -- JSON list of template IDs
        target_group_ids TEXT NOT NULL, -- JSON list of group IDs
        interval_val INTEGER NOT NULL DEFAULT 30,
        interval_unit TEXT NOT NULL DEFAULT 'minutes', -- 'seconds', 'minutes', 'hours'
        delay_min INTEGER NOT NULL DEFAULT 15,
        delay_max INTEGER NOT NULL DEFAULT 45,
        status TEXT NOT NULL DEFAULT 'stopped', -- 'stopped', 'running', 'paused'
        last_run TEXT,
        next_run TEXT,
        posts_sent INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    # Scouted Leads table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        group_id INTEGER,
        group_title TEXT,
        message_id INTEGER,
        message_text TEXT,
        matched_keyword TEXT,
        detected_at TEXT NOT NULL,
        status TEXT DEFAULT 'new', -- 'new', 'contacted', 'converted', 'ignored'
        notes TEXT DEFAULT '',
        UNIQUE(user_id, group_id, message_id)
    )
    """)

    # Scout Sources table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scout_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link_or_username TEXT NOT NULL UNIQUE,
        title TEXT DEFAULT '',
        scanned_at TEXT,
        leads_found INTEGER DEFAULT 0
    )
    """)

    # App Settings (Key-Value)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Activity & System Logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        category TEXT NOT NULL,
        message TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )
    """)

    conn.commit()

    # Pre-populate some starter IPTV templates if empty
    cursor.execute("SELECT COUNT(*) as count FROM templates")
    if cursor.fetchone()["count"] == 0:
        starter_templates = [
            (
                "IPTV Premium Offer #1",
                "{Hello|Hey|Hi} everyone! 👋\n\nLooking for a {rock-solid|ultra-fast|top-tier} IPTV service?\n🔥 18,000+ Channels & 80,000+ VOD (4K/FHD)\n⚡ Anti-Freeze Tech | No Buffering\n📺 Compatible with Firestick, Smart TV, Android, MAG, Apple TV\n\n👉 Free 24h Trial Available! DM @{username} now to get set up instantly! 🚀",
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ),
            (
                "Reseller & Rebrand Panel Special",
                "{Attention Resellers|Reseller Opportunity|Boost your IPTV business} 💼\n\nLooking to start or scale your own IPTV brand?\n✅ Super Reseller & Master Panels available\n✅ Custom App Rebranding (IBO Player, Smarters Pro, XCIPTV)\n✅ Best credit prices in the market with instant activation\n✅ 24/7 dedicated support & 99.9% uptime server\n\n📩 Message @{username} for panel test and price list!",
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ),
            (
                "Fast Trial & Support",
                "{Tired of freezing streams during live sports?|Looking for the best football and sports streams?} ⚽🥊\n\nTest our ultra-fast server before you buy!\n✅ All Sports & PPV in FHD/4K (60 FPS)\n✅ Full EPG guide included\n✅ 1, 3, 6 & 12 Month plans\n\nDrop a DM to @{username} for your free test link today! 🎯",
                datetime.now().isoformat(),
                datetime.now().isoformat()
            )
        ]
        cursor.executemany("INSERT INTO templates (name, content, created_at, updated_at) VALUES (?, ?, ?, ?)", starter_templates)
        conn.commit()

    # Pre-populate default IPTV keywords if not set
    cursor.execute("SELECT value FROM settings WHERE key = 'scout_keywords'")
    if not cursor.fetchone():
        default_keywords = [
            "iptv", "iptv subscription", "reseller panel", "rebrand app",
            "reseller", "smarters", "tivimate", "trial", "m3u",
            "supplier", "credits", "mag", "xtream", "provider"
        ]
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('scout_keywords', ?)", (json.dumps(default_keywords),))
        conn.commit()

    conn.close()

def log_activity(level: str, category: str, message: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO activity_logs (level, category, message, timestamp) VALUES (?, ?, ?, ?)",
        (level.upper(), category.upper(), message, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def get_logs(limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# Template CRUD
def get_templates() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM templates ORDER BY id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_template(template_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_template(name: str, content: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO templates (name, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (name, content, now, now)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    log_activity("INFO", "TEMPLATE", f"Created template '{name}' (ID: {new_id})")
    return new_id

def update_template(template_id: int, name: str, content: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "UPDATE templates SET name = ?, content = ?, updated_at = ? WHERE id = ?",
        (name, content, now, template_id)
    )
    conn.commit()
    affected = cursor.rowcount > 0
    conn.close()
    log_activity("INFO", "TEMPLATE", f"Updated template (ID: {template_id})")
    return affected

def delete_template(template_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    conn.commit()
    affected = cursor.rowcount > 0
    conn.close()
    log_activity("INFO", "TEMPLATE", f"Deleted template (ID: {template_id})")
    return affected

# Leads CRUD & Query
def add_lead(lead_data: dict) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    now = lead_data.get("detected_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute("""
        INSERT INTO leads (user_id, username, first_name, last_name, group_id, group_title, message_id, message_text, matched_keyword, detected_at, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            lead_data.get("user_id"),
            lead_data.get("username"),
            lead_data.get("first_name"),
            lead_data.get("last_name"),
            lead_data.get("group_id"),
            lead_data.get("group_title"),
            lead_data.get("message_id"),
            lead_data.get("message_text"),
            lead_data.get("matched_keyword"),
            now,
            lead_data.get("status", "new"),
            lead_data.get("notes", "")
        ))
        conn.commit()
        inserted = True
    except sqlite3.IntegrityError:
        inserted = False # duplicate lead ignored
    conn.close()
    return inserted

def get_leads(keyword: str = None, status: str = None, limit: int = 500) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM leads WHERE 1=1"
    params = []
    
    if keyword:
        query += " AND (matched_keyword LIKE ? OR message_text LIKE ?)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if status and status != "all":
        query += " AND status = ?"
        params.append(status)
        
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def update_lead_status(lead_id: int, status: str, notes: str = None) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    if notes is not None:
        cursor.execute("UPDATE leads SET status = ?, notes = ? WHERE id = ?", (status, notes, lead_id))
    else:
        cursor.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
    conn.commit()
    affected = cursor.rowcount > 0
    conn.close()
    return affected

def delete_lead(lead_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()
    return True

def clear_leads() -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leads")
    conn.commit()
    conn.close()
    return True

# Settings helpers
def get_setting(key: str, default: Any = None) -> Any:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key: str, value: Any):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

# Campaign helpers
def get_campaigns() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaigns ORDER BY id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def create_campaign(data: dict) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO campaigns (name, template_ids, target_group_ids, interval_val, interval_unit, delay_min, delay_max, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'stopped', ?)
    """, (
        data.get("name", "Auto Post Campaign"),
        json.dumps(data.get("template_ids", [])),
        json.dumps(data.get("target_group_ids", [])),
        int(data.get("interval_val", 30)),
        data.get("interval_unit", "minutes"),
        int(data.get("delay_min", 15)),
        int(data.get("delay_max", 45)),
        now
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    log_activity("INFO", "POSTER", f"Created campaign '{data.get('name')}' (ID: {new_id})")
    return new_id

def update_campaign_status(campaign_id: int, status: str, last_run: str = None, next_run: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "UPDATE campaigns SET status = ?"
    params = [status]
    if last_run is not None:
        query += ", last_run = ?"
        params.append(last_run)
    if next_run is not None:
        query += ", next_run = ?"
        params.append(next_run)
    query += " WHERE id = ?"
    params.append(campaign_id)
    cursor.execute(query, params)
    conn.commit()
    conn.close()

def increment_campaign_posts(campaign_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE campaigns SET posts_sent = posts_sent + 1 WHERE id = ?", (campaign_id,))
    conn.commit()
    conn.close()
