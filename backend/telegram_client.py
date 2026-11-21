import os
import re
import json
import asyncio
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

from backend.database import (
    get_setting, set_setting, log_activity, add_lead, DB_PATH,
    get_accounts, get_active_account, save_or_update_account, set_active_account, delete_account
)
from backend.spintax import render_template

SESSION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(SESSION_DIR, exist_ok=True)
SESSION_FILE = os.path.join(SESSION_DIR, "scout_user.session")
SESSION_STR_FILE = os.path.join(SESSION_DIR, "session_string.txt")
CREDS_FILE = os.path.join(SESSION_DIR, "credentials_backup.json")

class TelegramManager:
    _instance = None

    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self._auth_client: Optional[TelegramClient] = None
        self.phone_code_hash: Optional[str] = None
        self.temp_phone: Optional[str] = None
        self.is_scanning: bool = False
        self.live_scout_active: bool = False
        self.live_scout_keywords: List[str] = []
        self._cached_user: Optional[Dict[str, Any]] = None
        self._last_user_check: float = 0
        self._is_connecting: bool = False
        self._keep_alive_task: Optional[asyncio.Task] = None
        self._cached_groups: List[Dict[str, Any]] = []
        self._cached_groups_time: float = 0

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TelegramManager()
        return cls._instance

    def get_credentials(self) -> tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
        # Always check active account from SQLite first to guarantee active account is loaded
        try:
            active_acc = get_active_account()
            if active_acc and active_acc.get("session_string"):
                api_id = active_acc.get("api_id") or get_setting("api_id")
                api_hash = active_acc.get("api_hash") or get_setting("api_hash")
                phone = active_acc.get("phone") or get_setting("phone")
                session_str = active_acc.get("session_string")
                try:
                    api_id = int(api_id) if api_id else 21040435
                except (ValueError, TypeError):
                    api_id = 21040435
                api_hash = api_hash or "2d19c05868a10c46c95b6646710f1e73"
                return api_id, api_hash, phone, session_str
        except Exception:
            pass

        api_id = get_setting("api_id")
        api_hash = get_setting("api_hash")
        phone = get_setting("phone")
        session_str = get_setting("session_string")

        # Fallback to local session string file if DB was wiped on restart
        if not session_str and os.path.exists(SESSION_STR_FILE):
            try:
                with open(SESSION_STR_FILE, "r") as f:
                    session_str = f.read().strip()
            except Exception:
                pass

        # Fallback to credentials backup file if DB was wiped on restart
        if (not api_id or not api_hash or not session_str) and os.path.exists(CREDS_FILE):
            try:
                with open(CREDS_FILE, "r") as f:
                    cdata = json.load(f)
                    api_id = api_id or cdata.get("api_id")
                    api_hash = api_hash or cdata.get("api_hash")
                    phone = phone or cdata.get("phone")
                    session_str = session_str or cdata.get("session_string")
            except Exception:
                pass

        try:
            api_id = int(api_id) if api_id else None
        except (ValueError, TypeError):
            api_id = None
        return api_id, api_hash, phone, session_str

    def _save_session_string(self, session_str: str):
        if session_str:
            set_setting("session_string", session_str)
            try:
                with open(SESSION_STR_FILE, "w") as f:
                    f.write(session_str)
            except Exception:
                pass
            self._save_credentials_backup(session_str=session_str)

    def _save_credentials_backup(self, api_id: Optional[int] = None, api_hash: Optional[str] = None, phone: Optional[str] = None, session_str: Optional[str] = None):
        try:
            current = {}
            if os.path.exists(CREDS_FILE):
                try:
                    with open(CREDS_FILE, "r") as f:
                        current = json.load(f)
                except Exception:
                    current = {}

            if api_id: current["api_id"] = api_id
            if api_hash: current["api_hash"] = api_hash
            if phone: current["phone"] = phone
            if session_str: current["session_string"] = session_str

            with open(CREDS_FILE, "w") as f:
                json.dump(current, f)
        except Exception:
            pass

    async def get_client(self) -> Optional[TelegramClient]:
        if self.client:
            if self.client.is_connected():
                return self.client
            try:
                await self.client.connect()
                return self.client
            except Exception as e:
                log_activity("WARNING", "AUTH", f"Telegram reconnecting: {str(e)}")

        if self._is_connecting:
            for _ in range(30):
                await asyncio.sleep(0.2)
                if self.client and self.client.is_connected():
                    return self.client

        self._is_connecting = True
        try:
            api_id, api_hash, _, session_str = self.get_credentials()
            if not api_id or not api_hash:
                return None

            # Prefer StringSession for 100% resilience across server restarts
            if session_str:
                session = StringSession(session_str)
            elif os.path.exists(SESSION_FILE):
                session = SESSION_FILE
            else:
                session = StringSession("")

            self.client = TelegramClient(
                session, 
                api_id, 
                api_hash,
                auto_reconnect=True,
                connection_retries=None,
                retry_delay=2,
                timeout=15
            )
            await self.client.connect()

            # If authorized, persist as StringSession
            if await self.client.is_user_authorized():
                saved_str = self.client.session.save()
                if isinstance(saved_str, str) and saved_str:
                    self._save_session_string(saved_str)

            self._start_keep_alive()
            return self.client
        finally:
            self._is_connecting = False

    def _start_keep_alive(self):
        if self._keep_alive_task is None or self._keep_alive_task.done():
            try:
                loop = asyncio.get_event_loop()
                self._keep_alive_task = loop.create_task(self._telegram_keep_alive_loop())
            except Exception:
                pass

    async def _telegram_keep_alive_loop(self):
        while True:
            try:
                await asyncio.sleep(45)  # Ping Telegram every 45 seconds to keep the socket alive!
                api_id, api_hash, _, session_str = self.get_credentials()
                if not session_str or not api_id or not api_hash:
                    continue
                client = await self.get_client()
                if client and client.is_connected():
                    try:
                        await client.get_input_entity('me')
                    except Exception:
                        pass
                elif client and not client.is_connected():
                    try:
                        await client.connect()
                    except Exception:
                        pass
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def get_status(self) -> Dict[str, Any]:
        api_id, api_hash, phone, session_str = self.get_credentials()
        has_creds = bool(api_id and api_hash)
        
        # Load cached user from persistent settings if memory cache is empty
        if not self._cached_user:
            saved_u = get_setting("user_info")
            if saved_u:
                try:
                    self._cached_user = json.loads(saved_u)
                except Exception:
                    pass

        is_auth = False
        user_info = None

        # If session_str exists, user IS authorized by definition!
        if session_str:
            is_auth = True
            user_info = self._cached_user or {
                "id": 0,
                "first_name": "Telegram User",
                "last_name": "",
                "username": "",
                "phone": phone or "",
                "is_premium": False
            }
            self._start_keep_alive()

        try:
            client = await self.get_client()
            if client and await client.is_user_authorized():
                is_auth = True
                now = time.time()
                # Check get_me only every 10 minutes to avoid hammering Telegram
                if not self._cached_user or (now - self._last_user_check) > 600:
                    me = await client.get_me()
                    if me:
                        user_info = {
                            "id": me.id,
                            "first_name": me.first_name or "",
                            "last_name": me.last_name or "",
                            "username": me.username or "",
                            "phone": me.phone or phone or "",
                            "is_premium": getattr(me, "premium", False)
                        }
                        self._cached_user = user_info
                        self._last_user_check = now
                        set_setting("user_info", json.dumps(user_info))
                        saved_str = client.session.save()
                        if isinstance(saved_str, str) and saved_str:
                            self._save_session_string(saved_str)
                            session_str = saved_str
                else:
                    user_info = self._cached_user
            elif not session_str:
                is_auth = False
                user_info = None
        except errors.SessionRevokedError:
            log_activity("WARNING", "AUTH", "Telegram session revoked by user on official app")
            self._save_session_string("")
            set_setting("user_info", "")
            self._cached_user = None
            is_auth = False
            user_info = None
        except Exception as e:
            # Temporary network hiccup or reconnecting - KEEP user authorized if session_str exists!
            if session_str:
                is_auth = True
                user_info = self._cached_user or user_info

        accounts = get_accounts()
        active_acc = get_active_account()

        # Always guarantee that user_info matches the currently active account
        if active_acc:
            user_info = {
                "id": active_acc.get("user_id", 0),
                "first_name": active_acc.get("first_name", ""),
                "last_name": active_acc.get("last_name", ""),
                "username": active_acc.get("username", ""),
                "phone": active_acc.get("phone", "")
            }
            clean_active_phone = str(active_acc.get("phone", "")).lstrip("+")
            if self._cached_user and str(self._cached_user.get("phone", "")).lstrip("+") == clean_active_phone:
                user_info = self._cached_user
        elif not user_info and self._cached_user:
            user_info = self._cached_user

        return {
            "has_credentials": has_creds,
            "is_authorized": is_auth,
            "user": user_info,
            "api_id": api_id,
            "phone": phone,
            "session_string": session_str or "",
            "accounts": accounts,
            "accounts_count": len(accounts),
            "active_account": active_acc
        }

    async def restore_session(self, session_str: str, api_id: Optional[int] = None, api_hash: Optional[str] = None, phone: Optional[str] = None) -> Dict[str, Any]:
        api_id_val = api_id or get_setting("api_id")
        api_hash_val = api_hash or get_setting("api_hash")
        phone_val = phone or get_setting("phone")

        if api_id_val:
            set_setting("api_id", api_id_val)
        if api_hash_val:
            set_setting("api_hash", api_hash_val)
        if phone_val:
            set_setting("phone", phone_val)

        session_str = session_str.strip()
        self._save_session_string(session_str)
        self._save_credentials_backup(api_id=api_id_val, api_hash=api_hash_val, phone=phone_val, session_str=session_str)

        # Disconnect any old instance
        if self.client and self.client.is_connected():
            try:
                await self.client.disconnect()
            except Exception:
                pass
        self.client = None

        client = await self.get_client()
        self._start_keep_alive()

        if client and await client.is_user_authorized():
            me = await client.get_me()
            self._cached_user = {
                "id": me.id,
                "first_name": me.first_name or "",
                "last_name": me.last_name or "",
                "username": me.username or "",
                "phone": me.phone or phone_val or "",
                "is_premium": getattr(me, "premium", False)
            }
            self._last_user_check = time.time()
            set_setting("user_info", json.dumps(self._cached_user))
            set_setting("is_connected", "1")
            
            # Save or update multi-account registry
            save_or_update_account(
                phone=self._cached_user.get("phone") or phone_val or "account",
                api_id=int(api_id_val or 0),
                api_hash=api_hash_val or "",
                session_string=session_str,
                user=self._cached_user,
                make_active=True
            )
            
            log_activity("SUCCESS", "AUTH", f"Telegram session automatically restored for {me.first_name}!")
            return {"success": True, "user": self._cached_user, "session_string": session_str}
        else:
            # If still connecting, return cached user info so UI remains permanently logged in
            saved_u = get_setting("user_info")
            if saved_u:
                try:
                    self._cached_user = json.loads(saved_u)
                except Exception:
                    pass
            user = self._cached_user or {"first_name": "Telegram User", "username": "", "phone": phone_val or ""}
            return {"success": True, "user": user, "session_string": session_str}

    async def request_code(self, api_id: int, api_hash: str, phone: str) -> Dict[str, Any]:
        try:
            api_id_val = int(api_id) if (api_id and int(api_id) > 0) else 21040435
            api_hash_val = str(api_hash).strip() if (api_hash and str(api_hash).strip()) else "2d19c05868a10c46c95b6646710f1e73"
            phone = phone.strip().replace(" ", "").replace("-", "")
            if not phone.startswith("+"):
                phone = "+" + phone

            if self._auth_client and self._auth_client.is_connected():
                try:
                    await asyncio.wait_for(self._auth_client.disconnect(), timeout=2.0)
                except Exception:
                    pass

            self._auth_client = TelegramClient(StringSession(""), api_id_val, api_hash_val, auto_reconnect=True)
            await asyncio.wait_for(self._auth_client.connect(), timeout=12.0)

            res = await self._auth_client.send_code_request(phone)
            self.phone_code_hash = res.phone_code_hash
            self.temp_phone = phone
            self.temp_api_id = api_id_val
            self.temp_api_hash = api_hash_val
            log_activity("INFO", "AUTH", f"Telegram login OTP requested for {phone}")
            return {"success": True, "message": "Verification code sent to your Telegram account / SMS"}
        except Exception as e:
            log_activity("ERROR", "AUTH", f"Failed to send code: {str(e)}")
            return {"success": False, "error": str(e)}

    async def sign_in_with_code(self, code: str, password: Optional[str] = None) -> Dict[str, Any]:
        if not self._auth_client or not self.temp_phone or not self.phone_code_hash:
            return {"success": False, "error": "No active sign-in request found. Request a new code first."}

        code = code.strip().replace(" ", "")
        try:
            try:
                await self._auth_client.sign_in(self.temp_phone, code=code, phone_code_hash=self.phone_code_hash)
            except errors.SessionPasswordNeededError:
                if not password:
                    return {"success": False, "need_2fa": True, "message": "Two-factor authentication (2FA) password required"}
                await self._auth_client.sign_in(password=password)

            me = await self._auth_client.get_me()
            saved_str = self._auth_client.session.save()
            if isinstance(saved_str, str) and saved_str:
                self._save_session_string(saved_str)

            # Switch active client
            if self.client and self.client.is_connected():
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
            self.client = self._auth_client
            self._auth_client = None

            self._cached_user = {
                "id": me.id,
                "first_name": me.first_name or "",
                "last_name": me.last_name or "",
                "username": me.username or "",
                "phone": me.phone or self.temp_phone or ""
            }
            self._last_user_check = time.time()
            set_setting("user_info", json.dumps(self._cached_user))
            set_setting("is_connected", "1")
            self._start_keep_alive()

            # Save to multi-account registry
            api_id_val = int(getattr(self, "temp_api_id", 0) or get_setting("api_id") or 21040435)
            api_hash_val = getattr(self, "temp_api_hash", "") or get_setting("api_hash") or "2d19c05868a10c46c95b6646710f1e73"
            save_or_update_account(
                phone=self._cached_user.get("phone") or self.temp_phone,
                api_id=api_id_val,
                api_hash=api_hash_val,
                session_string=saved_str,
                user=self._cached_user,
                make_active=True
            )

            log_activity("SUCCESS", "AUTH", f"Successfully logged into Telegram as {me.first_name} (@{me.username})")
            return {
                "success": True,
                "user": self._cached_user,
                "session_string": saved_str
            }
        except Exception as e:
            log_activity("ERROR", "AUTH", f"Sign in failed: {str(e)}")
            return {"success": False, "error": str(e)}

    async def request_qr_code(self, api_id: int, api_hash: str) -> Dict[str, Any]:
        DEFAULT_API_ID = 21040435
        DEFAULT_API_HASH = "2d19c05868a10c46c95b6646710f1e73"

        api_id_val = int(api_id) if (api_id and int(api_id) > 0) else DEFAULT_API_ID
        api_hash_val = str(api_hash).strip() if (api_hash and str(api_hash).strip()) else DEFAULT_API_HASH

        # Always start with the verified Telegram pair if custom is mismatched or default
        attempts = []
        if (api_id_val, api_hash_val) != (DEFAULT_API_ID, DEFAULT_API_HASH):
            attempts.append((DEFAULT_API_ID, DEFAULT_API_HASH))
            attempts.append((api_id_val, api_hash_val))
        else:
            attempts.append((DEFAULT_API_ID, DEFAULT_API_HASH))

        last_error = None
        for attempt_id, attempt_hash in attempts:
            try:
                if hasattr(self, "_qr_task") and self._qr_task and not self._qr_task.done():
                    self._qr_task.cancel()
                    try:
                        await asyncio.wait_for(self._qr_task, timeout=1.0)
                    except Exception:
                        pass
                
                if self._auth_client and self._auth_client.is_connected():
                    try:
                        await asyncio.wait_for(self._auth_client.disconnect(), timeout=2.0)
                    except Exception:
                        pass

                self.temp_api_id = attempt_id
                self.temp_api_hash = attempt_hash
                self._auth_client = TelegramClient(StringSession(""), attempt_id, attempt_hash, auto_reconnect=True)
                await asyncio.wait_for(self._auth_client.connect(), timeout=12.0)
                self.qr_instance = await self._auth_client.qr_login()
                self.qr_url = self.qr_instance.url
                self.qr_done = False
                self.qr_need_2fa = False
                self.qr_error = None
                self.qr_user = None

                self._qr_task = asyncio.create_task(self._qr_worker())
                log_activity("INFO", "AUTH", "Started continuous Telegram QR login listener task")
                return {
                    "success": True,
                    "url": self.qr_instance.url,
                    "expires": self.qr_instance.expires.isoformat() if getattr(self.qr_instance, "expires", None) else None
                }
            except errors.ApiIdInvalidError as api_err:
                last_error = api_err
                log_activity("WARN", "AUTH", f"App credentials invalid for QR login, attempting verified Telegram pair...")
                continue
            except Exception as e:
                last_error = e
                continue

        log_activity("ERROR", "AUTH", f"Failed to start QR login: {str(last_error)}")
        return {"success": False, "error": f"Failed to connect to Telegram: {str(last_error)}"}

    async def _qr_worker(self):
        while not self.qr_done and getattr(self, "qr_instance", None) and self._auth_client:
            try:
                # Wait for the full lifetime of the token (Telethon handles duration automatically)
                user = await self.qr_instance.wait()
                self.qr_user = user
                self.qr_done = True
                
                saved_str = self._auth_client.session.save()
                me = await self._auth_client.get_me()
                user_phone = me.phone or getattr(user, 'phone', None) or ""

                # Disconnect old main client and replace with the authorized client
                if self.client and self.client.is_connected():
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                self.client = self._auth_client
                self._auth_client = None

                self._cached_user = {
                    "id": me.id,
                    "first_name": me.first_name or "",
                    "last_name": me.last_name or "",
                    "username": me.username or "",
                    "phone": user_phone
                }
                self._last_user_check = time.time()
                set_setting("user_info", json.dumps(self._cached_user))
                set_setting("is_connected", "1")
                self._start_keep_alive()

                api_id_val = int(getattr(self, "temp_api_id", 0) or get_setting("api_id") or 21040435)
                api_hash_val = getattr(self, "temp_api_hash", "") or get_setting("api_hash") or "2d19c05868a10c46c95b6646710f1e73"
                phone_identifier = user_phone or f"user_{me.id}"
                save_or_update_account(
                    phone=phone_identifier,
                    api_id=api_id_val,
                    api_hash=api_hash_val,
                    session_string=saved_str,
                    user=self._cached_user,
                    make_active=True
                )
                log_activity("SUCCESS", "AUTH", f"Successfully logged into Telegram via QR Code as {me.first_name}!")
                break
            except errors.SessionPasswordNeededError:
                self.qr_need_2fa = True
                log_activity("WARN", "AUTH", "Telegram QR login requires 2FA password")
                break
            except (errors.AuthTokenExpiredError, asyncio.TimeoutError):
                # Token expired naturally: renew immediately and keep waiting seamlessly
                try:
                    await self.qr_instance.recreate()
                    self.qr_url = self.qr_instance.url
                    log_activity("INFO", "AUTH", "Telegram QR code refreshed — ready for scan")
                    continue
                except Exception as rec_err:
                    self.qr_error = str(rec_err)
                    log_activity("ERROR", "AUTH", f"Telegram QR recreate failed: {rec_err}")
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                err_msg = str(e).lower()
                # Catch token expiration or DC migration re-scan requests
                if "expired" in err_msg or "token" in err_msg or "rescan" in err_msg or "re-scanned" in err_msg:
                    try:
                        await self.qr_instance.recreate()
                        self.qr_url = self.qr_instance.url
                        log_activity("INFO", "AUTH", "Telegram DC token refreshed — ready for scan")
                        continue
                    except Exception as rec_err:
                        self.qr_error = str(rec_err)
                        break
                self.qr_error = str(e)
                log_activity("ERROR", "AUTH", f"Telegram QR worker error: {str(e)}")
                break

    async def check_qr_login(self, password: Optional[str] = None) -> Dict[str, Any]:
        if not hasattr(self, "qr_instance") or not self.qr_instance:
            return {"success": False, "error": "No QR login session active"}
        
        if getattr(self, "qr_error", None):
            return {"success": False, "error": self.qr_error}
        
        if getattr(self, "qr_need_2fa", False):
            if not password:
                return {"success": False, "need_2fa": True, "message": "Two-factor authentication (2FA) password required"}
            try:
                auth_cl = self._auth_client or self.client
                if not auth_cl:
                    return {"success": False, "error": "Auth client missing for 2FA"}
                user = await auth_cl.sign_in(password=password)
                saved_str = auth_cl.session.save()
                me = await auth_cl.get_me()

                if self.client and self.client != auth_cl and self.client.is_connected():
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                self.client = auth_cl
                self._auth_client = None

                user_phone = me.phone or getattr(user, 'phone', None) or ""
                self._cached_user = {
                    "id": me.id,
                    "first_name": me.first_name or "",
                    "last_name": me.last_name or "",
                    "username": me.username or "",
                    "phone": user_phone
                }
                self._last_user_check = time.time()
                set_setting("user_info", json.dumps(self._cached_user))
                set_setting("is_connected", "1")
                self._start_keep_alive()

                api_id_val = int(getattr(self, "temp_api_id", 0) or get_setting("api_id") or 21040435)
                api_hash_val = getattr(self, "temp_api_hash", "") or get_setting("api_hash") or "2d19c05868a10c46c95b6646710f1e73"
                phone_identifier = user_phone or f"user_{me.id}"
                save_or_update_account(
                    phone=phone_identifier,
                    api_id=api_id_val,
                    api_hash=api_hash_val,
                    session_string=saved_str,
                    user=self._cached_user,
                    make_active=True
                )
                self.qr_done = True
                self.qr_need_2fa = False
                return {"success": True, "user": self._cached_user, "session_string": saved_str}
            except Exception as e:
                return {"success": False, "error": f"2FA verification failed: {str(e)}"}

        if getattr(self, "qr_done", False):
            return {
                "success": True,
                "user": getattr(self, "_cached_user", None),
                "session_string": self.client.session.save() if self.client else ""
            }

        return {
            "success": False,
            "waiting": True,
            "url": getattr(self, "qr_url", None)
        }

    async def switch_account(self, identifier: Any) -> Dict[str, Any]:
        acc = set_active_account(identifier)
        if not acc:
            return {"success": False, "error": "Account not found"}

        # Disconnect old client cleanly in background
        old_client = self.client
        self.client = None
        self._cached_user = {
            "id": acc.get("user_id", 0),
            "first_name": acc.get("first_name", ""),
            "last_name": acc.get("last_name", ""),
            "username": acc.get("username", ""),
            "phone": acc.get("phone", "")
        }
        self._last_user_check = 0
        self._cached_groups = []
        self._cached_groups_time = 0
        set_setting("cached_groups_count", "0")

        # Synchronize active credentials immediately into settings and disk
        if acc.get("session_string"):
            set_setting("session_string", acc["session_string"])
            self._save_session_string(acc["session_string"])
        if acc.get("phone"):
            set_setting("phone", str(acc["phone"]))
        if acc.get("api_id"):
            set_setting("api_id", str(acc["api_id"]))
        if acc.get("api_hash"):
            set_setting("api_hash", str(acc["api_hash"]))
        set_setting("user_info", json.dumps(self._cached_user))

        self._save_credentials_backup(
            api_id=int(acc.get("api_id") or 21040435),
            api_hash=acc.get("api_hash") or "2d19c05868a10c46c95b6646710f1e73",
            phone=str(acc.get("phone") or ""),
            session_str=acc.get("session_string")
        )

        # Connect in background so API responds in 5ms
        async def _connect_switched():
            if old_client:
                try:
                    if old_client.is_connected():
                        await old_client.disconnect()
                except Exception:
                    pass
            client = await self.get_client()
            if client and await client.is_user_authorized():
                try:
                    me = await client.get_me()
                    if me:
                        fresh_user = {
                            "id": me.id,
                            "first_name": me.first_name or "",
                            "last_name": me.last_name or "",
                            "username": me.username or "",
                            "phone": me.phone or acc.get("phone", ""),
                            "is_premium": getattr(me, "premium", False)
                        }
                        self._cached_user = fresh_user
                        self._last_user_check = time.time()
                        set_setting("user_info", json.dumps(fresh_user))
                        save_or_update_account(
                            phone=fresh_user["phone"] or acc.get("phone"),
                            api_id=int(acc.get("api_id") or 21040435),
                            api_hash=acc.get("api_hash") or "2d19c05868a10c46c95b6646710f1e73",
                            session_string=acc.get("session_string"),
                            user=fresh_user,
                            make_active=True
                        )
                except Exception as e:
                    log_activity("WARN", "AUTH", f"Switched client get_me notice: {e}")
            self._start_keep_alive()
            await self.get_dialogs_and_groups(force_refresh=True)

        asyncio.create_task(_connect_switched())

        user_display = acc.get("first_name", "")
        if acc.get("username"):
            user_display += f" (@{acc.get('username')})"
        phone_display = f"+{acc.get('phone')}" if acc.get("phone") else ""

        log_activity("SUCCESS", "AUTH", f"Switched working Telegram account to {user_display} {phone_display}")

        return {
            "success": True,
            "active_account": acc,
            "user": self._cached_user
        }

    async def logout(self) -> Dict[str, Any]:
        try:
            if self.client and self.client.is_connected():
                try:
                    await self.client.log_out()
                except Exception:
                    pass
                await self.client.disconnect()
            
            self.client = None
            self._cached_user = None
            self._last_user_check = 0
            if self._keep_alive_task:
                self._keep_alive_task.cancel()
                self._keep_alive_task = None

            # Clear session strings and user info
            set_setting("session_string", "")
            set_setting("user_info", "")
            set_setting("is_connected", "0")
            if os.path.exists(SESSION_STR_FILE):
                try:
                    os.remove(SESSION_STR_FILE)
                except Exception:
                    pass

            # Remove session files
            for ext in ["", "-journal"]:
                fpath = SESSION_FILE + ext
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass

            log_activity("INFO", "AUTH", "User logged out of Telegram")
            return {"success": True, "message": "Logged out successfully"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_dialogs_and_groups(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        # Fast cache check (valid for 30 seconds unless force_refresh is requested)
        if not force_refresh and self._cached_groups and (time.time() - self._cached_groups_time < 30):
            return self._cached_groups

        client = await self.get_client()
        if not client or not await client.is_user_authorized():
            return self._cached_groups or []

        groups = []
        try:
            # Iterate through all dialogs on the user's account without limit
            async for dialog in client.iter_dialogs(limit=None):
                entity = dialog.entity
                
                # Check whether entity is a broadcast channel
                is_broadcast = getattr(entity, 'broadcast', False)
                # Check whether entity is a group, supergroup, or gigagroup
                is_megagroup = getattr(entity, 'megagroup', False)
                is_gigagroup = getattr(entity, 'gigagroup', False)
                is_real_group = bool(dialog.is_group or is_megagroup or is_gigagroup)

                # STRICT RULE: GROUPS ONLY, NEVER BROADCAST CHANNELS
                if is_real_group and not is_broadcast:
                    # Check whether regular members are banned from sending messages in this group
                    posting_restricted = False
                    if hasattr(entity, 'default_banned_rights') and entity.default_banned_rights:
                        if getattr(entity.default_banned_rights, 'send_messages', False):
                            if not getattr(entity, 'admin_rights', None) and not getattr(entity, 'creator', False):
                                posting_restricted = True

                    if not posting_restricted:
                        member_count = getattr(entity, 'participants_count', 0)
                        groups.append({
                            "id": dialog.id,
                            "title": dialog.name or "Untitled Group",
                            "username": getattr(entity, 'username', None),
                            "is_group": True,
                            "is_channel": False,
                            "unread_count": dialog.unread_count,
                            "member_count": member_count
                        })

            if groups:
                self._cached_groups = groups
                self._cached_groups_time = time.time()
                set_setting("cached_groups_count", str(len(groups)))
        except Exception as e:
            log_activity("ERROR", "TELEGRAM", f"Error fetching groups: {str(e)}")
            if self._cached_groups:
                return self._cached_groups

        return groups or self._cached_groups

    async def send_post(self, group_id_or_username: Any, template_text: str) -> Dict[str, Any]:
        client = await self.get_client()
        if not client or not await client.is_user_authorized():
            return {"success": False, "error": "Telegram client is not authorized"}

        try:
            entity = await client.get_entity(group_id_or_username)
            entity_name = getattr(entity, 'title', str(group_id_or_username))

            # Strictly avoid channels - groups only!
            if getattr(entity, 'broadcast', False):
                log_activity("INFO", "POSTER", f"Skipped broadcast channel '{entity_name}' (groups-only policy)")
                return {"success": False, "error": "Skipped: channel not group"}

            me = await client.get_me()
            rendered_text = render_template(template_text, {
                "username": me.username or me.first_name or "Me",
                "first_name": me.first_name or "",
            })
            
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

    async def scout_target(self, link_or_username: str, keywords: List[str], scan_depth: int = 500) -> Dict[str, Any]:
        client = await self.get_client()
        if not client or not await client.is_user_authorized():
            return {"success": False, "error": "Telegram client is not authorized"}

        target_clean = link_or_username.strip()
        if target_clean.startswith("https://t.me/"):
            target_clean = target_clean.replace("https://t.me/", "")
        elif target_clean.startswith("t.me/"):
            target_clean = target_clean.replace("t.me/", "")

        log_activity("INFO", "SCOUT", f"Starting deep scout scan on '{target_clean}' for IPTV discussions...")
        
        try:
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

            kw_clean = [k.strip().lower() for k in keywords if k.strip()]
            if not kw_clean:
                kw_clean = [
                    "iptv", "m3u", "reseller", "smarters", "tivimate", "trial", 
                    "mag", "xtream", "credits", "supplier", "panel", "subscription", 
                    "rebrand", "provider", "freeze", "stream"
                ]

            leads_found = 0
            scanned_msg_ids = set()
            new_leads = []

            # 1. Server-side keyword search across group history
            for kw in kw_clean:
                try:
                    async for message in client.iter_messages(entity, search=kw, limit=100):
                        if not message or message.id in scanned_msg_ids:
                            continue
                        scanned_msg_ids.add(message.id)
                        if not message.text:
                            continue

                        sender = await message.get_sender()
                        if not sender or getattr(sender, 'bot', False):
                            continue

                        lead_dict = {
                            "user_id": sender.id,
                            "username": getattr(sender, 'username', None),
                            "first_name": getattr(sender, 'first_name', '') or "",
                            "last_name": getattr(sender, 'last_name', '') or "",
                            "group_id": group_id,
                            "group_title": group_title,
                            "message_id": message.id,
                            "message_text": message.text[:800],
                            "matched_keyword": kw,
                            "detected_at": message.date.strftime("%Y-%m-%d %H:%M:%S") if message.date else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "new"
                        }

                        if add_lead(lead_dict):
                            leads_found += 1
                            new_leads.append(lead_dict)
                except Exception:
                    pass

            # 2. Sequential recent message scan
            try:
                async for message in client.iter_messages(entity, limit=min(scan_depth, 500)):
                    if not message or message.id in scanned_msg_ids:
                        continue
                    scanned_msg_ids.add(message.id)
                    if not message.text:
                        continue

                    sender = await message.get_sender()
                    if not sender or getattr(sender, 'bot', False):
                        continue

                    msg_text_lower = message.text.lower()
                    matched_kw = None
                    for kw in kw_clean:
                        if re.search(r'\b' + re.escape(kw) + r'\b', msg_text_lower) or kw in msg_text_lower:
                            matched_kw = kw
                            break

                    if matched_kw:
                        lead_dict = {
                            "user_id": sender.id,
                            "username": getattr(sender, 'username', None),
                            "first_name": getattr(sender, 'first_name', '') or "",
                            "last_name": getattr(sender, 'last_name', '') or "",
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
            except Exception:
                pass

            log_activity("SUCCESS", "SCOUT", f"Finished scouting '{group_title}'. Found {leads_found} members talking about IPTV ({len(scanned_msg_ids)} messages inspected)!")
            return {
                "success": True,
                "group_title": group_title,
                "scanned_count": len(scanned_msg_ids),
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
