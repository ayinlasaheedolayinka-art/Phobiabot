import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "scout_bot.db")
TEMPLATES_JSON_PATH = os.path.join(DATA_DIR, "templates.json")
CAMPAIGNS_JSON_PATH = os.path.join(DATA_DIR, "campaigns.json")
SETTINGS_JSON_PATH = os.path.join(DATA_DIR, "settings.json")
ACCOUNTS_JSON_PATH = os.path.join(DATA_DIR, "telegram_accounts.json")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def _restore_templates_internal(cursor) -> int:
    if not os.path.exists(TEMPLATES_JSON_PATH):
        return 0
    try:
        with open(TEMPLATES_JSON_PATH, "r", encoding="utf-8") as f:
            items = json.load(f)
        if not items or not isinstance(items, list):
            return 0
        restored = 0
        now = datetime.now().isoformat()
        for item in items:
            name = (item.get("name") or "").strip()
            content = (item.get("content") or "").strip()
            if not name or not content:
                continue
            cursor.execute("SELECT id FROM templates WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                cursor.execute("UPDATE templates SET content = ?, updated_at = ? WHERE id = ?", (content, now, row["id"]))
            else:
                cursor.execute(
                    "INSERT INTO templates (name, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (name, content, item.get("created_at", now), item.get("updated_at", now))
                )
            restored += 1
        return restored
    except Exception as e:
        print(f"Error restoring templates: {e}")
        return 0

def _export_templates_internal(cursor):
    try:
        cursor.execute("SELECT * FROM templates ORDER BY id DESC")
        rows = [dict(r) for r in cursor.fetchall()]
        with open(TEMPLATES_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error exporting templates: {e}")

def _restore_campaigns_internal(cursor) -> int:
    if not os.path.exists(CAMPAIGNS_JSON_PATH):
        return 0
    try:
        with open(CAMPAIGNS_JSON_PATH, "r", encoding="utf-8") as f:
            items = json.load(f)
        if not items or not isinstance(items, list):
            return 0
        restored = 0
        now = datetime.now().isoformat()
        for item in items:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            cursor.execute("SELECT id FROM campaigns WHERE name = ?", (name,))
            if not cursor.fetchone():
                t_ids = item.get("template_ids", [])
                g_ids = item.get("target_group_ids", [])
                t_str = json.dumps(t_ids) if isinstance(t_ids, list) else str(t_ids)
                g_str = json.dumps(g_ids) if isinstance(g_ids, list) else str(g_ids)
                cursor.execute("""
                INSERT INTO campaigns (name, template_ids, target_group_ids, interval_val, interval_unit, delay_min, delay_max, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    t_str,
                    g_str,
                    int(item.get("interval_val", 30)),
                    item.get("interval_unit", "minutes"),
                    int(item.get("delay_min", 15)),
                    int(item.get("delay_max", 45)),
                    item.get("status", "stopped"),
                    item.get("created_at", now)
                ))
                restored += 1
        return restored
    except Exception as e:
        print(f"Error restoring campaigns: {e}")
        return 0

def _export_campaigns_internal(cursor):
    try:
        cursor.execute("SELECT * FROM campaigns ORDER BY id DESC")
        rows = [dict(r) for r in cursor.fetchall()]
        with open(CAMPAIGNS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error exporting campaigns: {e}")

def _restore_settings_internal(cursor) -> int:
    if not os.path.exists(SETTINGS_JSON_PATH):
        return 0
    try:
        with open(SETTINGS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return 0
        count = 0
        for k, v in data.items():
            if v is not None and str(v).strip():
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
                count += 1
        return count
    except Exception as e:
        print(f"Error restoring settings: {e}")
        return 0

def _export_settings_internal(cursor):
    try:
        cursor.execute("SELECT key, value FROM settings")
        data = {r["key"]: r["value"] for r in cursor.fetchall()}
        with open(SETTINGS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error exporting settings: {e}")

def _restore_accounts_internal(cursor) -> int:
    if not os.path.exists(ACCOUNTS_JSON_PATH):
        return 0
    try:
        with open(ACCOUNTS_JSON_PATH, "r", encoding="utf-8") as f:
            items = json.load(f)
        if not items or not isinstance(items, list):
            return 0
        restored = 0
        now = datetime.now().isoformat()
        for item in items:
            phone = (item.get("phone") or "").strip()
            session_str = (item.get("session_string") or "").strip()
            if not phone or not session_str:
                continue
            cursor.execute("SELECT id FROM telegram_accounts WHERE phone = ?", (phone,))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                UPDATE telegram_accounts 
                SET api_id = ?, api_hash = ?, session_string = ?, user_id = ?, first_name = ?, last_name = ?, username = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """, (
                    item.get("api_id"),
                    item.get("api_hash"),
                    session_str,
                    item.get("user_id"),
                    item.get("first_name", ""),
                    item.get("last_name", ""),
                    item.get("username", ""),
                    item.get("is_active", 0),
                    item.get("updated_at", now),
                    row["id"]
                ))
            else:
                cursor.execute("""
                INSERT INTO telegram_accounts (phone, api_id, api_hash, session_string, user_id, first_name, last_name, username, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    phone,
                    item.get("api_id"),
                    item.get("api_hash"),
                    session_str,
                    item.get("user_id"),
                    item.get("first_name", ""),
                    item.get("last_name", ""),
                    item.get("username", ""),
                    item.get("is_active", 0),
                    item.get("created_at", now),
                    item.get("updated_at", now)
                ))
            restored += 1
        return restored
    except Exception as e:
        print(f"Error restoring accounts: {e}")
        return 0

def _export_accounts_internal(cursor):
    try:
        cursor.execute("SELECT * FROM telegram_accounts ORDER BY id ASC")
        rows = [dict(r) for r in cursor.fetchall()]
        with open(ACCOUNTS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error exporting accounts: {e}")

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

    # Telegram Accounts Table (Multi-Account Support)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telegram_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL UNIQUE,
        api_id INTEGER,
        api_hash TEXT,
        session_string TEXT NOT NULL,
        user_id INTEGER,
        first_name TEXT,
        last_name TEXT,
        username TEXT,
        is_active INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # Migration for stop_after_finish on campaigns table
    try:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN stop_after_finish INTEGER DEFAULT 1")
    except Exception:
        pass

    conn.commit()

    # Pre-populate or restore templates from persistent file storage
    cursor.execute("SELECT COUNT(*) as count FROM templates")
    if cursor.fetchone()["count"] == 0:
        restored = _restore_templates_internal(cursor)
        if restored == 0:
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
            _export_templates_internal(cursor)

    # Restore campaigns from file if empty
    cursor.execute("SELECT COUNT(*) as count FROM campaigns")
    if cursor.fetchone()["count"] == 0:
        _restore_campaigns_internal(cursor)
        conn.commit()

    # Restore settings from persistent file
    _restore_settings_internal(cursor)
    conn.commit()

    # Restore telegram accounts from persistent file storage
    _restore_accounts_internal(cursor)
    conn.commit()

    # If no accounts exist in table, check if settings or credentials backup has an existing logged-in session
    cursor.execute("SELECT COUNT(*) as count FROM telegram_accounts")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("SELECT value FROM settings WHERE key = 'session_string'")
        sess_row = cursor.fetchone()
        sess_val = (sess_row["value"] if sess_row else "") or ""
        
        cursor.execute("SELECT value FROM settings WHERE key = 'phone'")
        phone_row = cursor.fetchone()
        phone_val = (phone_row["value"] if phone_row else "") or ""
        
        cursor.execute("SELECT value FROM settings WHERE key = 'api_id'")
        api_id_row = cursor.fetchone()
        api_id_val = int(api_id_row["value"]) if (api_id_row and api_id_row["value"] and str(api_id_row["value"]).isdigit()) else None

        cursor.execute("SELECT value FROM settings WHERE key = 'api_hash'")
        api_hash_row = cursor.fetchone()
        api_hash_val = (api_hash_row["value"] if api_hash_row else "") or ""

        cursor.execute("SELECT value FROM settings WHERE key = 'user_info'")
        user_row = cursor.fetchone()
        u_info = {}
        if user_row and user_row["value"]:
            try:
                u_info = json.loads(user_row["value"])
            except Exception:
                u_info = {}

        if sess_val and (phone_val or u_info.get("phone")):
            now = datetime.now().isoformat()
            p_val = phone_val or u_info.get("phone") or "Account_1"
            cursor.execute("""
            INSERT INTO telegram_accounts (phone, api_id, api_hash, session_string, user_id, first_name, last_name, username, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (
                p_val, api_id_val, api_hash_val, sess_val,
                u_info.get("id"), u_info.get("first_name", "Telegram User"), u_info.get("last_name", ""), u_info.get("username", ""),
                now, now
            ))
            conn.commit()
            _export_accounts_internal(cursor)

    # Ensure exactly one account is marked active if accounts exist
    cursor.execute("SELECT COUNT(*) as count FROM telegram_accounts WHERE is_active = 1")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("UPDATE telegram_accounts SET is_active = 1 WHERE id = (SELECT id FROM telegram_accounts ORDER BY id ASC LIMIT 1)")
        conn.commit()
        _export_accounts_internal(cursor)

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
    _export_templates_internal(cursor)
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
    _export_templates_internal(cursor)
    conn.close()
    log_activity("INFO", "TEMPLATE", f"Updated template (ID: {template_id})")
    return affected

def delete_template(template_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    conn.commit()
    affected = cursor.rowcount > 0
    _export_templates_internal(cursor)
    conn.close()
    log_activity("INFO", "TEMPLATE", f"Deleted template (ID: {template_id})")
    return affected

def export_templates_to_file():
    conn = get_connection()
    cursor = conn.cursor()
    _export_templates_internal(cursor)
    conn.close()

def restore_templates_from_file() -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cnt = _restore_templates_internal(cursor)
    conn.commit()
    conn.close()
    return cnt

def sync_templates_bulk(templates_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    for item in templates_list:
        name = (item.get("name") or "").strip()
        content = (item.get("content") or "").strip()
        if not name or not content:
            continue
        cursor.execute("SELECT id FROM templates WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE templates SET content = ?, updated_at = ? WHERE id = ?", (content, now, row["id"]))
        else:
            cursor.execute(
                "INSERT INTO templates (name, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (name, content, item.get("created_at", now), item.get("updated_at", now))
            )
    conn.commit()
    _export_templates_internal(cursor)
    conn.close()
    log_activity("INFO", "TEMPLATE", f"Auto-synced {len(templates_list)} templates with cloud storage")
    return get_templates()

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
    _export_settings_internal(cursor)
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
    stop_after = int(data.get("stop_after_finish", 1))
    cursor.execute("""
    INSERT INTO campaigns (name, template_ids, target_group_ids, interval_val, interval_unit, delay_min, delay_max, status, stop_after_finish, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'stopped', ?, ?)
    """, (
        data.get("name", "Auto Post Campaign"),
        json.dumps(data.get("template_ids", [])),
        json.dumps(data.get("target_group_ids", [])),
        int(data.get("interval_val", 30)),
        data.get("interval_unit", "minutes"),
        int(data.get("delay_min", 15)),
        int(data.get("delay_max", 45)),
        stop_after,
        now
    ))
    conn.commit()
    new_id = cursor.lastrowid
    _export_campaigns_internal(cursor)
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
    _export_campaigns_internal(cursor)
    conn.close()

def increment_campaign_posts(campaign_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE campaigns SET posts_sent = posts_sent + 1 WHERE id = ?", (campaign_id,))
    conn.commit()
    conn.close()

def export_campaigns_to_file():
    conn = get_connection()
    cursor = conn.cursor()
    _export_campaigns_internal(cursor)
    conn.close()

def restore_campaigns_from_file() -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cnt = _restore_campaigns_internal(cursor)
    conn.commit()
    conn.close()
    return cnt

def sync_campaigns_bulk(campaigns_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    for item in campaigns_list:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        cursor.execute("SELECT id FROM campaigns WHERE name = ?", (name,))
        row = cursor.fetchone()
        t_ids = item.get("template_ids", [])
        g_ids = item.get("target_group_ids", [])
        t_str = json.dumps(t_ids) if isinstance(t_ids, list) else str(t_ids)
        g_str = json.dumps(g_ids) if isinstance(g_ids, list) else str(g_ids)
        if row:
            cursor.execute("""
            UPDATE campaigns SET template_ids = ?, target_group_ids = ?, interval_val = ?, interval_unit = ?, delay_min = ?, delay_max = ? WHERE id = ?
            """, (t_str, g_str, int(item.get("interval_val", 30)), item.get("interval_unit", "minutes"), int(item.get("delay_min", 15)), int(item.get("delay_max", 45)), row["id"]))
        else:
            cursor.execute("""
            INSERT INTO campaigns (name, template_ids, target_group_ids, interval_val, interval_unit, delay_min, delay_max, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                t_str,
                g_str,
                int(item.get("interval_val", 30)),
                item.get("interval_unit", "minutes"),
                int(item.get("delay_min", 15)),
                int(item.get("delay_max", 45)),
                item.get("status", "stopped"),
                item.get("created_at", now)
            ))
    conn.commit()
    _export_campaigns_internal(cursor)
    conn.close()
    return get_campaigns()

# Telegram Account Management (Multi-Account Support)
def get_accounts() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, phone, api_id, user_id, first_name, last_name, username, is_active, created_at, updated_at FROM telegram_accounts ORDER BY is_active DESC, id ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_active_account() -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM telegram_accounts WHERE is_active = 1 LIMIT 1")
    row = cursor.fetchone()
    if not row:
        cursor.execute("SELECT * FROM telegram_accounts ORDER BY id ASC LIMIT 1")
        row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_account(account_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM telegram_accounts WHERE id = ?", (account_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def save_or_update_account(phone: str, api_id: int, api_hash: str, session_string: str, user: dict = None, make_active: bool = True) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    phone_clean = phone.strip().replace(" ", "").replace("-", "")
    
    user_id = user.get("id") if user else None
    first_name = (user.get("first_name") or "").strip() if user else ""
    last_name = (user.get("last_name") or "").strip() if user else ""
    username = (user.get("username") or "").strip() if user else ""

    if make_active:
        cursor.execute("UPDATE telegram_accounts SET is_active = 0")

    cursor.execute("SELECT id FROM telegram_accounts WHERE phone = ?", (phone_clean,))
    row = cursor.fetchone()
    if row:
        acc_id = row["id"]
        cursor.execute("""
        UPDATE telegram_accounts 
        SET api_id = ?, api_hash = ?, session_string = ?, user_id = ?, first_name = ?, last_name = ?, username = ?, is_active = ?, updated_at = ?
        WHERE id = ?
        """, (
            api_id, api_hash, session_string, user_id, first_name, last_name, username,
            1 if make_active else 0, now, acc_id
        ))
    else:
        cursor.execute("""
        INSERT INTO telegram_accounts (phone, api_id, api_hash, session_string, user_id, first_name, last_name, username, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            phone_clean, api_id, api_hash, session_string, user_id, first_name, last_name, username,
            1 if make_active else 0, now, now
        ))
        acc_id = cursor.lastrowid

    conn.commit()
    _export_accounts_internal(cursor)

    if make_active:
        # Sync active account to settings
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('api_id', ?)", (str(api_id),))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('api_hash', ?)", (api_hash,))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('phone', ?)", (phone_clean,))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('session_string', ?)", (session_string,))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_info', ?)", (json.dumps({
            "id": user_id,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "phone": phone_clean
        }),))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('is_connected', '1')")
        conn.commit()

    conn.close()
    return acc_id

def set_active_account(account_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM telegram_accounts WHERE id = ?", (account_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    acc = dict(row)
    cursor.execute("UPDATE telegram_accounts SET is_active = 0")
    cursor.execute("UPDATE telegram_accounts SET is_active = 1 WHERE id = ?", (account_id,))
    
    # Sync to settings
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('api_id', ?)", (str(acc["api_id"]),))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('api_hash', ?)", (acc["api_hash"],))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('phone', ?)", (acc["phone"],))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('session_string', ?)", (acc["session_string"],))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_info', ?)", (json.dumps({
        "id": acc["user_id"],
        "first_name": acc["first_name"],
        "last_name": acc["last_name"],
        "username": acc["username"],
        "phone": acc["phone"]
    }),))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('is_connected', '1')")
    
    conn.commit()
    _export_accounts_internal(cursor)
    conn.close()
    return acc

def delete_account(account_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM telegram_accounts WHERE id = ?", (account_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    
    was_active = bool(row["is_active"])
    cursor.execute("DELETE FROM telegram_accounts WHERE id = ?", (account_id,))
    conn.commit()

    if was_active:
        cursor.execute("SELECT id FROM telegram_accounts ORDER BY id ASC LIMIT 1")
        next_row = cursor.fetchone()
        if next_row:
            next_id = next_row["id"]
            conn.close()
            set_active_account(next_id)
            return True
        else:
            # No accounts left
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('session_string', '')")
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_info', '')")
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('is_connected', '0')")
            conn.commit()
            
    _export_accounts_internal(cursor)
    conn.close()
    return True
