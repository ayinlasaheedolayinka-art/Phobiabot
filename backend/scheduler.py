import asyncio
import json
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from backend.database import (
    get_connection, get_campaigns, update_campaign_status, 
    increment_campaign_posts, get_template, get_templates, log_activity
)
from backend.telegram_client import TelegramManager

class CampaignScheduler:
    _instance = None

    def __init__(self):
        self.running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._keep_alive_task: Optional[asyncio.Task] = None
        self.current_execution_info: Dict[str, Any] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = CampaignScheduler()
        return cls._instance

    def start_loop(self):
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self._scheduler_loop())
            self._keep_alive_task = asyncio.create_task(self._keep_alive_loop())
            log_activity("INFO", "SCHEDULER", "Campaign scheduler & keep-alive loop started")

    def stop_loop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            self._keep_alive_task = None
        log_activity("INFO", "SCHEDULER", "Campaign scheduler background loop stopped")

    def calculate_next_run(self, interval_val: int, interval_unit: str) -> datetime:
        now = datetime.now()
        unit = (interval_unit or "minutes").lower()
        if "sec" in unit:
            return now + timedelta(seconds=max(5, int(interval_val)))
        elif "hour" in unit:
            return now + timedelta(hours=max(1, int(interval_val)))
        else: # default minutes
            return now + timedelta(minutes=max(1, int(interval_val)))

    async def _scheduler_loop(self):
        tg = TelegramManager.get_instance()
        while self.running:
            try:
                campaigns = get_campaigns()
                now = datetime.now()

                for camp in campaigns:
                    if camp.get("status") != "running":
                        continue

                    next_run_str = camp.get("next_run")
                    should_run = False
                    if not next_run_str:
                        should_run = True
                    else:
                        try:
                            next_run_dt = datetime.fromisoformat(next_run_str)
                            if now >= next_run_dt:
                                should_run = True
                        except Exception:
                            should_run = True

                    if should_run:
                        await self._execute_campaign(camp, tg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_activity("ERROR", "SCHEDULER", f"Error in scheduler loop: {str(e)}")

            # Render Cloud Keep-Alive: Ping self every 8 minutes to prevent container spin-down
            if now.second == 0 and now.minute % 8 == 0:
                asyncio.create_task(self._ping_keep_alive())

            # Check every second for responsive second-based intervals
            await asyncio.sleep(1)

    async def _keep_alive_loop(self):
        while self.running:
            try:
                await asyncio.sleep(240)  # Every 4 minutes (Render sleeps after 15m idle)
                import urllib.request
                urllib.request.urlopen("https://phobiabot.onrender.com/api/status", timeout=15)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _ping_keep_alive(self):
        try:
            import urllib.request
            urllib.request.urlopen("https://phobiabot.onrender.com/api/status", timeout=10)
        except Exception:
            pass

    async def _execute_campaign(self, campaign: dict, tg: TelegramManager):
        camp_id = campaign["id"]
        camp_name = campaign["name"]

        # Check client authorization
        status = await tg.get_status()
        if not status.get("is_authorized"):
            log_activity("WARNING", "POSTER", f"Telegram not logged in. Cannot run campaign '{camp_name}'.")
            return

        try:
            template_ids = json.loads(campaign.get("template_ids", "[]"))
        except Exception:
            template_ids = []

        try:
            target_groups_raw = json.loads(campaign.get("target_group_ids", "[]"))
        except Exception:
            target_groups_raw = []

        # If templates empty or set to 'all', use all available templates
        if not template_ids or template_ids == ["all"]:
            all_templates = get_templates()
            template_ids = [t["id"] for t in all_templates]

        # If target groups is empty or ["all"], dynamically resolve all joined groups
        is_all_groups = False
        if not target_groups_raw or target_groups_raw == ["all"] or "all" in target_groups_raw:
            is_all_groups = True
            all_groups = await tg.get_dialogs_and_groups()
            group_ids = [g["id"] for g in all_groups]
        else:
            group_ids = [int(gid) for gid in target_groups_raw if str(gid).isdigit() or (isinstance(gid, int))]

        if not template_ids:
            log_activity("WARNING", "POSTER", f"Campaign '{camp_name}' has no templates. Please create at least one content template.")
            update_campaign_status(camp_id, "stopped")
            return

        if not group_ids:
            log_activity("WARNING", "POSTER", f"Campaign '{camp_name}' has no target groups found. Make sure your Telegram account is in at least 1 group.")
            update_campaign_status(camp_id, "stopped")
            return

        now_str = datetime.now().isoformat()
        next_dt = self.calculate_next_run(campaign.get("interval_val", 30), campaign.get("interval_unit", "minutes"))
        update_campaign_status(camp_id, "running", last_run=now_str, next_run=next_dt.isoformat())

        interval_display = f"{campaign.get('interval_val', 30)} {campaign.get('interval_unit', 'minutes')}"
        scope_display = f"ALL {len(group_ids)} joined groups" if is_all_groups else f"{len(group_ids)} selected groups"
        log_activity("INFO", "POSTER", f"🚀 Starting broadcast round for '{camp_name}' to {scope_display}. Interval: every {interval_display}.")

        delay_min = max(3, int(campaign.get("delay_min", 10)))
        delay_max = max(delay_min + 3, int(campaign.get("delay_max", 30)))

        successful_posts = 0

        for idx, group_id in enumerate(group_ids):
            # Check if campaign was paused or stopped mid-way
            conn = get_connection()
            c_check = conn.execute("SELECT status FROM campaigns WHERE id = ?", (camp_id,)).fetchone()
            conn.close()
            if not c_check or c_check["status"] != "running":
                log_activity("INFO", "POSTER", f"Campaign '{camp_name}' was paused or stopped by user during broadcast.")
                break

            # Pick template (rotate or pick random)
            t_id = random.choice(template_ids)
            template = get_template(t_id)
            if not template:
                continue

            content = template["content"]
            result = await tg.send_post(group_id, content)

            if result.get("success"):
                successful_posts += 1
                increment_campaign_posts(camp_id)
            elif result.get("flood_wait"):
                wait_sec = result["flood_wait"] + 5
                log_activity("WARNING", "POSTER", f"Telegram FloodWait encountered. Pausing for {wait_sec}s...")
                await asyncio.sleep(wait_sec)

            # Anti-spam delay between groups (skip on last group)
            if idx < len(group_ids) - 1:
                safe_wait = random.randint(delay_min, delay_max)
                await asyncio.sleep(safe_wait)

        log_activity("SUCCESS", "POSTER", f"✅ Broadcast round finished: {successful_posts}/{len(group_ids)} posts sent. Next round scheduled at {next_dt.strftime('%H:%M:%S')}")
