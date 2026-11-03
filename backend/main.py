import os
import json
import csv
import io
from typing import List, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.database import (
    init_db, get_templates, get_template, create_template, update_template, delete_template,
    get_leads, update_lead_status, delete_lead, clear_leads,
    get_campaigns, create_campaign, update_campaign_status,
    get_logs, log_activity, get_setting, set_setting, get_connection
)
from backend.spintax import render_template
from backend.telegram_client import TelegramManager
from backend.scheduler import CampaignScheduler

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    log_activity("INFO", "SYSTEM", "Scout Bot Platform starting up...")
    scheduler = CampaignScheduler.get_instance()
    scheduler.start_loop()
    yield
    # Shutdown
    scheduler.stop_loop()
    log_activity("INFO", "SYSTEM", "Scout Bot Platform shut down")

app = FastAPI(title="Telegram IPTV Scout & Auto-Poster Bot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Schemas
class SendCodeRequest(BaseModel):
    api_id: int
    api_hash: str
    phone: str

class VerifyCodeRequest(BaseModel):
    code: str
    password: Optional[str] = None

class TemplateCreate(BaseModel):
    name: str
    content: str

class TemplatePreview(BaseModel):
    content: str

class CampaignCreate(BaseModel):
    name: str
    template_ids: List[int]
    target_group_ids: List[int]
    interval_val: int = 30
    interval_unit: str = "minutes"
    delay_min: int = 15
    delay_max: int = 45

class TestPostRequest(BaseModel):
    group_id: int
    template_id: int

class ScoutRequest(BaseModel):
    links: List[str]
    keywords: List[str]
    scan_depth: int = 200

class LeadStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None

class KeywordsUpdate(BaseModel):
    keywords: List[str]

class LiveScoutToggle(BaseModel):
    enabled: bool

# ----------------- AUTH & STATUS ROUTES -----------------
@app.get("/api/status")
async def get_system_status():
    tg = TelegramManager.get_instance()
    tg_status = await tg.get_status()
    keywords_raw = get_setting("scout_keywords", "[]")
    try:
        keywords = json.loads(keywords_raw)
    except:
        keywords = []

    return {
        "telegram": tg_status,
        "live_scout_active": tg.live_scout_active,
        "keywords": keywords
    }

@app.post("/api/auth/send-code")
async def send_code(req: SendCodeRequest):
    tg = TelegramManager.get_instance()
    res = await tg.request_code(req.api_id, req.api_hash, req.phone)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to send code"))
    return res

@app.post("/api/auth/verify-code")
async def verify_code(req: VerifyCodeRequest):
    tg = TelegramManager.get_instance()
    res = await tg.sign_in_with_code(req.code, req.password)
    if not res.get("success"):
        if res.get("need_2fa"):
            return res
        raise HTTPException(status_code=400, detail=res.get("error", "Sign-in failed"))
    return res

@app.post("/api/auth/logout")
async def logout():
    tg = TelegramManager.get_instance()
    return await tg.logout()

# ----------------- TEMPLATES ROUTES -----------------
@app.get("/api/templates")
def list_templates():
    return get_templates()

@app.post("/api/templates")
def add_template(req: TemplateCreate):
    if not req.name.strip() or not req.content.strip():
        raise HTTPException(status_code=400, detail="Name and content are required")
    template_id = create_template(req.name.strip(), req.content.strip())
    return {"success": True, "id": template_id}

@app.put("/api/templates/{template_id}")
def edit_template(template_id: int, req: TemplateCreate):
    ok = update_template(template_id, req.name.strip(), req.content.strip())
    if not ok:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True}

@app.delete("/api/templates/{template_id}")
def remove_template(template_id: int):
    ok = delete_template(template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True}

@app.post("/api/templates/preview")
def preview_template(req: TemplatePreview):
    rendered = render_template(req.content, {"username": "YourUsername", "first_name": "John"})
    return {"rendered": rendered}

# ----------------- GROUPS & DIALOGS ROUTES -----------------
@app.get("/api/groups")
async def get_groups():
    tg = TelegramManager.get_instance()
    groups = await tg.get_dialogs_and_groups()
    return {"groups": groups, "count": len(groups)}

# ----------------- CAMPAIGN / AUTO-POSTER ROUTES -----------------
@app.get("/api/campaigns")
def list_campaigns():
    return get_campaigns()

@app.post("/api/campaigns")
def add_campaign(req: CampaignCreate):
    camp_id = create_campaign(req.dict())
    return {"success": True, "id": camp_id}

@app.post("/api/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: int):
    update_campaign_status(campaign_id, "running")
    log_activity("INFO", "POSTER", f"Started campaign (ID: {campaign_id})")
    return {"success": True, "status": "running"}

@app.post("/api/campaigns/{campaign_id}/pause")
def pause_campaign(campaign_id: int):
    update_campaign_status(campaign_id, "paused")
    log_activity("INFO", "POSTER", f"Paused campaign (ID: {campaign_id})")
    return {"success": True, "status": "paused"}

@app.post("/api/campaigns/{campaign_id}/stop")
def stop_campaign(campaign_id: int):
    update_campaign_status(campaign_id, "stopped", next_run=None)
    log_activity("INFO", "POSTER", f"Stopped campaign (ID: {campaign_id})")
    return {"success": True, "status": "stopped"}

@app.post("/api/poster/test-post")
async def test_post(req: TestPostRequest):
    t = get_template(req.template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    tg = TelegramManager.get_instance()
    res = await tg.send_post(req.group_id, t["content"])
    return res

# ----------------- SCOUT & LEADS ROUTES -----------------
@app.post("/api/scout/scan")
async def scout_scan(req: ScoutRequest):
    tg = TelegramManager.get_instance()
    results = []
    total_leads = 0

    for link in req.links:
        if not link.strip():
            continue
        res = await tg.scout_target(link.strip(), req.keywords, scan_depth=req.scan_depth)
        results.append(res)
        if res.get("success"):
            total_leads += res.get("leads_found", 0)

    return {
        "success": True,
        "total_leads_found": total_leads,
        "details": results
    }

@app.get("/api/scout/leads")
def list_leads(keyword: Optional[str] = None, status: Optional[str] = None, limit: int = 500):
    return get_leads(keyword=keyword, status=status, limit=limit)

@app.put("/api/scout/leads/{lead_id}")
def update_lead(lead_id: int, req: LeadStatusUpdate):
    ok = update_lead_status(lead_id, req.status, req.notes)
    if not ok:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"success": True}

@app.delete("/api/scout/leads/{lead_id}")
def remove_lead(lead_id: int):
    delete_lead(lead_id)
    return {"success": True}

@app.delete("/api/scout/leads")
def delete_all_leads():
    clear_leads()
    log_activity("INFO", "SCOUT", "Cleared all scouted leads from database")
    return {"success": True}

@app.get("/api/scout/export-csv")
def export_leads_csv():
    leads = get_leads(limit=5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Username", "First Name", "Last Name", "Group Title", "Matched Keyword", "Detected At", "Message Content", "Status", "Notes"])
    
    for l in leads:
        writer.writerow([
            l.get("id"),
            f"@{l.get('username')}" if l.get("username") else "",
            l.get("first_name", ""),
            l.get("last_name", ""),
            l.get("group_title", ""),
            l.get("matched_keyword", ""),
            l.get("detected_at", ""),
            l.get("message_text", "").replace("\n", " "),
            l.get("status", "new"),
            l.get("notes", "")
        ])

    output.seek(0)
    filename = f"iptv_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/scout/keywords")
def get_keywords():
    raw = get_setting("scout_keywords", "[]")
    try:
        return json.loads(raw)
    except:
        return []

@app.post("/api/scout/keywords")
def save_keywords(req: KeywordsUpdate):
    set_setting("scout_keywords", json.dumps(req.keywords))
    log_activity("INFO", "SCOUT", f"Updated scout keywords list ({len(req.keywords)} keywords)")
    return {"success": True, "keywords": req.keywords}

@app.post("/api/scout/live-toggle")
async def toggle_live_scout(req: LiveScoutToggle):
    tg = TelegramManager.get_instance()
    if req.enabled:
        raw = get_setting("scout_keywords", "[]")
        try:
            kw = json.loads(raw)
        except:
            kw = ["iptv", "subscription", "reseller panel", "rebrand app"]
        ok = await tg.enable_live_scout(kw)
        return {"success": ok, "live_scout_active": True}
    else:
        tg.disable_live_scout()
        return {"success": True, "live_scout_active": False}

# ----------------- STATS & LOGS -----------------
@app.get("/api/stats")
def get_dashboard_stats():
    conn = get_connection()
    leads_count = conn.execute("SELECT COUNT(*) as c FROM leads").fetchone()["c"]
    templates_count = conn.execute("SELECT COUNT(*) as c FROM templates").fetchone()["c"]
    campaigns_count = conn.execute("SELECT COUNT(*) as c FROM campaigns").fetchone()["c"]
    active_campaigns = conn.execute("SELECT COUNT(*) as c FROM campaigns WHERE status = 'running'").fetchone()["c"]
    posts_sent = conn.execute("SELECT COALESCE(SUM(posts_sent), 0) as c FROM campaigns").fetchone()["c"]
    conn.close()

    return {
        "leads_count": leads_count,
        "templates_count": templates_count,
        "campaigns_count": campaigns_count,
        "active_campaigns": active_campaigns,
        "posts_sent": posts_sent
    }

@app.get("/api/logs")
def fetch_logs(limit: int = 100):
    return get_logs(limit=limit)

# Serve Frontend Static Assets
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Telegram Scout Bot Backend running. Frontend index.html not found yet."}
