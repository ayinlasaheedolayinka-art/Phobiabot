import os
import re
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from telethon import TelegramClient, events, errors
from telethon.tl.types import Channel, Chat, User
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

from backend.database import (
    get_setting, set_setting, log_activity, add_lead, DB_PATH
)
from backend.spintax import render_template

SESSION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(SESSION_DIR, exist_ok=True)
SESSION_FILE = os.path.join(SESSION_DIR, "scout_user.session")

class TelegramManager:
    _instance = None

    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.phone_code_hash: Optional[str] = None
        self.temp_phone: Optional[str] = None
        self.is_scanning: bool = False
        self.live_scout_active: bool = False
        self.live_scout_keywords: List[str] = []
        self.event_subscribers = [] # WebSocket callbacks

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TelegramManager()
        return cls._instance

    def get_credentials(self) -> tuple[Optional[int], Optional[str], Optional[str]]:
        api_id = get_setting("api_id")
        api_hash = get_setting("api_hash")
        phone = get_setting("phone")
        try:
            api_id = int(api_id) if api_id else None
        except (ValueError, TypeError):
            api_id = None
        return api_id, api_hash, phone

    async def get_client(self) -> Optional[TelegramClient]:
        if self.client and self.client.is_connected():
            return self.client

        api_id, api_hash, _ = self.get_credentials()
        if not api_id or not api_hash:
            return None

        # Create telethon client
        self.client = TelegramClient(SESSION_FILE, api_id, api_hash)
        await self.client.connect()
        return self.client

    async def get_status(self) -> Dict[str, Any]:
        api_id, api_hash, phone = self.get_credentials()
        has_creds = bool(api_id and api_hash)
        
        is_auth = False
        user_info = None

        try:
            client = await self.get_client()
            if client and await client.is_user_authorized():
                is_auth = True
                me = await client.get_me()
                user_info = {
                    "id": me.id,
                    "first_name": me.first_name or "",
                    "last_name": me.last_name or "",
                    "username": me.username or "",
                    "phone": me.phone or phone or "",
                    "is_premium": getattr(me, "premium", False)
                }
        except Exception as e:
            log_activity("WARNING", "AUTH", f"Status check error: {str(e)}")

        return {
            "has_credentials": has_creds,
            "is_authorized": is_auth,
            "user": user_info,
            "api_id": api_id,
            "phone": phone
        }

    async def request_code(self, api_id: int, api_hash: str, phone: str) -> Dict[str, Any]:
        phone = phone.strip().replace(" ", "").replace("-", "")
        set_setting("api_id", api_id)
        set_setting("api_hash", api_hash)
        set_setting("phone", phone)

        if self.client and self.client.is_connected():
            await self.client.disconnect()

        self.client = TelegramClient(SESSION_FILE, api_id, api_hash)
        await self.client.connect()

        try:
            res = await self.client.send_code_request(phone)
            self.phone_code_hash = res.phone_code_hash
            self.temp_phone = phone
            log_activity("INFO", "AUTH", f"Telegram login OTP requested for {phone}")
            return {"success": True, "message": "Verification code sent to your Telegram account / SMS"}
        except Exception as e:
            log_activity("ERROR", "AUTH", f"Failed to send code: {str(e)}")
            return {"success": False, "error": str(e)}

    async def sign_in_with_code(self, code: str, password: Optional[str] = None) -> Dict[str, Any]:
        if not self.client or not self.temp_phone or not self.phone_code_hash:
            return {"success": False, "error": "No active sign-in request found. Request a new code first."}

        code = code.strip().replace(" ", "")
        try:
            try:
                await self.client.sign_in(self.temp_phone, code=code, phone_code_hash=self.phone_code_hash)
            except errors.SessionPasswordNeededError:
                if not password:
                    return {"success": False, "need_2fa": True, "message": "Two-factor authentication (2FA) password required"}
                await self.client.sign_in(password=password)

            me = await self.client.get_me()
            set_setting("is_connected", "1")
            log_activity("SUCCESS", "AUTH", f"Successfully logged into Telegram as {me.first_name} (@{me.username})")
            return {
                "success": True,
                "user": {
                    "id": me.id,
                    "first_name": me.first_name,
                    "username": me.username,
                    "phone": me.phone
                }
            }
        except Exception as e:
            log_activity("ERROR", "AUTH", f"Sign in failed: {str(e)}")
            return {"success": False, "error": str(e)}

    async def logout(self) -> Dict[str, Any]:
        try:
            if self.client and self.client.is_connected():
                await self.client.log_out()
                await self.client.disconnect()
            
            # Remove session file
            for ext in ["", "-journal"]:
                fpath = SESSION_FILE + ext
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except:
                        pass

            set_setting("is_connected", "0")
            log_activity("INFO", "AUTH", "User logged out of Telegram")
            return {"success": True, "message": "Logged out successfully"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_dialogs_and_groups(self) -> List[Dict[str, Any]]:
        client = await self.get_client()
        if not client or not await client.is_user_authorized():
            return []

        groups = []
        try:
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                # Filter for groups, supergroups, and broadcast channels
                if dialog.is_group or dialog.is_channel:
                    member_count = getattr(entity, 'participants_count', 0)
                    groups.append({
                        "id": dialog.id,
                        "title": dialog.name or "Untitled Group",
                        "username": getattr(entity, 'username', None),
                        "is_group": dialog.is_group,
                        "is_channel": dialog.is_channel,
                        "unread_count": dialog.unread_count,
                        "member_count": member_count
                    })
        except Exception as e:
            log_activity("ERROR", "TELEGRAM", f"Error fetching groups: {str(e)}")

        return groups

    async def send_post(self, group_id_or_username: Any, template_text: str) -> Dict[str, Any]:
        client = await self.get_client()
        if not client or not await client.is_user_authorized():
            return {"success": False, "error": "Telegram client is not authorized"}

        me = await client.get_me()
        rendered_text = render_template(template_text, {
            "username": me.username or me.first_name or "Me",
            "first_name": me.first_name or "",
        })

        try:
            # Resolve target entity
            entity = await client.get_entity(group_id_or_username)
            entity_name = getattr(entity, 'title', str(group_id_or_username))
            
            msg = await client.send_message(entity, rendered_text)
            log_activity("SUCCESS", "POSTER", f"Posted message to '{entity_name}' (Msg ID: {msg.id})")
            return {"success": True, "message_id": msg.id, "group_title": entity_name}

        except errors.FloodWaitError as e:
            log_activity("WARNING", "POSTER", f"FloodWait: Telegram requires waiting {e.seconds}s. Pausing...")
            return {"success": False, "error": f"FloodWaitError: Wait {e.seconds} seconds", "flood_wait": e.seconds}
        except (errors.ChatWriteForbiddenError, errors.ChatAdminRequiredError):
            log_activity("WARNING", "POSTER", f"Cannot write to group {group_id_or_username}: posting restricted")
            return {"success": False, "error": "Posting restricted in this group/channel"}
        except errors.UserBannedInChannelError:
            log_activity("WARNING", "POSTER", f"User is restricted/banned in group {group_id_or_username}")
            return {"success": False, "error": "User restricted in group"}
        except Exception as e:
            log_activity("ERROR", "POSTER", f"Failed to post to {group_id_or_username}: {str(e)}")
            return {"success": False, "error": str(e)}

    async def scout_target(self, link_or_username: str, keywords: List[str], scan_depth: int = 200) -> Dict[str, Any]:
        client = await self.get_client()
        if not client or not await client.is_user_authorized():
            return {"success": False, "error": "Telegram client is not authorized"}

        target_clean = link_or_username.strip()
        if target_clean.startswith("https://t.me/"):
            target_clean = target_clean.replace("https://t.me/", "")
        elif target_clean.startswith("t.me/"):
            target_clean = target_clean.replace("t.me/", "")

        log_activity("INFO", "SCOUT", f"Starting scout scan on '{target_clean}' (Depth: {scan_depth} messages)...")
        
        try:
            # Check if it's an invite link (starts with + or joinchat/)
            if target_clean.startswith("+") or "joinchat/" in target_clean:
                invite_hash = target_clean.replace("+", "").replace("joinchat/", "")
                try:
                    updates = await client(ImportChatInviteRequest(invite_hash))
                    entity = updates.chats[0]
                except errors.UserAlreadyParticipantError:
                    entity = await client.get_entity(target_clean)
            else:
                entity = await client.get_entity(target_clean)

            group_title = getattr(entity, 'title', target_clean)
            group_id = entity.id

            # Lowercase keywords for case-insensitive matching
            kw_clean = [k.strip().lower() for k in keywords if k.strip()]
            if not kw_clean:
                return {"success": False, "error": "No keywords specified for scouting"}

            leads_found = 0
            scanned_count = 0
            new_leads = []

            async for message in client.iter_messages(entity, limit=scan_depth):
                scanned_count += 1
                if not message.text:
                    continue

                # Ignore messages from bots or channels themselves if desired
                sender = await message.get_sender()
                if not sender or getattr(sender, 'bot', False):
                    continue

                msg_text_lower = message.text.lower()
                
                # Check for keyword matches
                matched_kw = None
                for kw in kw_clean:
                    # Match whole words or substrings
                    if re.search(r'\b' + re.escape(kw) + r'\b', msg_text_lower) or kw in msg_text_lower:
                        matched_kw = kw
                        break

                if matched_kw:
                    sender_username = getattr(sender, 'username', None)
                    sender_first = getattr(sender, 'first_name', '') or ""
                    sender_last = getattr(sender, 'last_name', '') or ""

                    lead_dict = {
                        "user_id": sender.id,
                        "username": sender_username,
                        "first_name": sender_first,
                        "last_name": sender_last,
                        "group_id": group_id,
                        "group_title": group_title,
                        "message_id": message.id,
                        "message_text": message.text[:800],
                        "matched_keyword": matched_kw,
                        "detected_at": message.date.strftime("%Y-%m-%d %H:%M:%S") if message.date else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "new"
                    }

                    if add_lead(lead_dict):
                        leads_found += 1
                        new_leads.append(lead_dict)

            log_activity("SUCCESS", "SCOUT", f"Finished scouting '{group_title}'. Scanned {scanned_count} msgs, discovered {leads_found} IPTV leads!")
            return {
                "success": True,
                "group_title": group_title,
                "scanned_count": scanned_count,
                "leads_found": leads_found,
                "leads": new_leads
            }

        except Exception as e:
            log_activity("ERROR", "SCOUT", f"Failed to scout '{target_clean}': {str(e)}")
            return {"success": False, "error": str(e)}

    async def enable_live_scout(self, keywords: List[str]):
        client = await self.get_client()
        if not client or not await client.is_user_authorized():
            return False

        self.live_scout_keywords = [k.strip().lower() for k in keywords if k.strip()]
        if not self.live_scout_active:
            self.live_scout_active = True

            @client.on(events.NewMessage)
            async def incoming_message_handler(event):
                if not self.live_scout_active or not event.text:
                    return

                sender = await event.get_sender()
                if not sender or getattr(sender, 'bot', False):
                    return

                text_lower = event.text.lower()
                for kw in self.live_scout_keywords:
                    if kw in text_lower:
                        chat = await event.get_chat()
                        lead_dict = {
                            "user_id": sender.id,
                            "username": getattr(sender, "username", None),
                            "first_name": getattr(sender, "first_name", "") or "",
                            "last_name": getattr(sender, "last_name", "") or "",
                            "group_id": event.chat_id,
                            "group_title": getattr(chat, "title", "Direct Chat"),
                            "message_id": event.id,
                            "message_text": event.text[:800],
                            "matched_keyword": kw,
                            "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "new"
                        }
                        if add_lead(lead_dict):
                            log_activity("SUCCESS", "SCOUT", f"⚡ LIVE LEAD DETECTED: @{lead_dict['username'] or lead_dict['first_name']} in '{lead_dict['group_title']}' for '{kw}'")
                        break

            log_activity("INFO", "SCOUT", f"Live Scout Monitor activated on incoming messages for {len(self.live_scout_keywords)} keywords")
        return True

    def disable_live_scout(self):
        self.live_scout_active = False
        log_activity("INFO", "SCOUT", "Live Scout Monitor paused")
        return True
