import asyncio
import json
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from backend.database import (
    get_connection, get_campaigns, update_campaign_status, 
    increment_campaign_posts, get_template, log_activity
)
from backend.telegram_client import TelegramManager

class CampaignScheduler:
    _instance = None

    def __init__(self):
        self.running: bool = False
        self._task: Optional[asyncio.Task] = None
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
            log_activity("INFO", "SCHEDULER", "Campaign scheduler background loop started")

    def stop_loop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        log_activity("INFO", "SCHEDULER", "Campaign scheduler background loop stopped")

    def calculate_next_run(self, interval_val: int, interval_unit: str) -> datetime:
        now = datetime.now()
        unit = interval_unit.lower()
        if "sec" in unit:
            return now + timedelta(seconds=interval_val)
        elif "hour" in unit:
            return now + timedelta(hours=interval_val)
        else: # default minutes
            return now + timedelta(minutes=interval_val)

    async def _scheduler_loop(self):
        tg = TelegramManager.get_instance()
        while self.running:
            try:
                campaigns = get_campaigns()
                now = datetime.now()

                for camp in campaigns:
                    if camp["status"] != "running":
                        continue

                    next_run_str = camp["next_run"]
                    should_run = False
                    if not next_run_str:
                        should_run = True
                    else:
                        try:
                            next_run_dt = datetime.fromisoformat(next_run_str)
                            if now >= next_run_dt:
                                should_run = True
                        except:
                            should_run = True

                    if should_run:
                        await self._execute_campaign(camp, tg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_activity("ERROR", "SCHEDULER", f"Error in scheduler loop: {str(e)}")

            await asyncio.sleep(5) # Check every 5 seconds

    async def _execute_campaign(self, campaign: dict, tg: TelegramManager):
        camp_id = campaign["id"]
        camp_name = campaign["name"]

        try:
            template_ids = json.loads(campaign["template_ids"])
            group_ids = json.loads(campaign["target_group_ids"])
        except Exception:
            template_ids = []
            group_ids = []

        if not template_ids or not group_ids:
            log_activity("WARNING", "POSTER", f"Campaign '{camp_name}' has no templates or target groups. Stopping.")
            update_campaign_status(camp_id, "stopped")
            return

        # Check client authorization
        status = await tg.get_status()
        if not status["is_authorized"]:
            log_activity("WARNING", "POSTER", f"Telegram not logged in. Cannot run campaign '{camp_name}'.")
            return

        now_str = datetime.now().isoformat()
        next_dt = self.calculate_next_run(campaign["interval_val"], campaign["interval_unit"])
        update_campaign_status(camp_id, "running", last_run=now_str, next_run=next_dt.isoformat())

        log_activity("INFO", "POSTER", f"Starting broadcasting round for campaign '{camp_name}' ({len(group_ids)} groups)...")

        delay_min = max(5, int(campaign.get("delay_min", 15)))
        delay_max = max(delay_min + 5, int(campaign.get("delay_max", 45)))

        for idx, group_id in enumerate(group_ids):
            # Check if campaign was paused or stopped mid-way
            conn = get_connection()
            c_check = conn.execute("SELECT status FROM campaigns WHERE id = ?", (camp_id,)).fetchone()
            conn.close()
            if not c_check or c_check["status"] != "running":
                log_activity("INFO", "POSTER", f"Campaign '{camp_name}' was paused/stopped by user during broadcasting.")
                break

            # Pick template (rotate or pick random)
            t_id = random.choice(template_ids)
            template = get_template(t_id)
            if not template:
                continue

            content = template["content"]
            result = await tg.send_post(group_id, content)

            if result.get("success"):
                increment_campaign_posts(camp_id)
            elif result.get("flood_wait"):
                wait_sec = result["flood_wait"] + 5
                log_activity("WARNING", "POSTER", f"Pausing campaign '{camp_name}' for {wait_sec}s due to Telegram FloodWait")
                await asyncio.sleep(wait_sec)

            # Random anti-spam delay between group posts (skip delay on last group)
            if idx < len(group_ids) - 1:
                safe_wait = random.randint(delay_min, delay_max)
                await asyncio.sleep(safe_wait)

        log_activity("SUCCESS", "POSTER", f"Completed round for '{camp_name}'. Next round scheduled at {next_dt.strftime('%H:%M:%S')}")
