"""WhatsApp channel integration (both local linked-device and cloud webhook mode)."""

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Callable, Awaitable, Any

from cyberclaw.channel.base import Channel
from cyberclaw.core.events import EventSource

logger = logging.getLogger(__name__)


class WhatsAppEventSource(EventSource):
    _namespace = "platform-whatsapp"

    def __init__(self, phone_number: str, display_name: str = "", is_self: bool = False):
        self.phone_number = phone_number
        self.display_name = display_name
        self.is_self = is_self

    def __str__(self) -> str:
        return f"platform-whatsapp:{self.phone_number}"

    @classmethod
    def from_string(cls, s: str) -> "WhatsAppEventSource":
        parts = s.split(":", 1)
        return cls(phone_number=parts[1] if len(parts) > 1 else "")

    @property
    def platform_name(self) -> str:
        return "whatsapp"


class WhatsAppChannel(Channel[WhatsAppEventSource]):
    """WhatsApp platform support via local linked-device (Baileys) or Business Cloud API."""

    def __init__(self, config: Any):
        self.config = config
        self.mode: str = getattr(config, "mode", "local")
        
        # Cloud API settings
        self.phone_number_id: str = getattr(config, "phone_number_id", "")
        self.access_token: str = getattr(config, "access_token", "")
        self.verify_token: str = getattr(config, "verify_token", "cyberclaw-verify")
        
        # Shared settings
        self.allow_from: list[str] = getattr(config, "allow_from", [])
        self.dm_policy: str = getattr(config, "dm_policy", "pairing")
        
        self.linked_phone: str | None = None
        self._stop_event = asyncio.Event()
        self._on_message = None
        
        # Local mode process states
        self._process: asyncio.subprocess.Process | None = None
        self._listener_task: asyncio.Task | None = None

    @property
    def platform_name(self) -> str:
        return "whatsapp"

    def is_allowed(self, source: WhatsAppEventSource) -> bool:
        if getattr(source, "is_self", False):
            return True
        if not self.allow_from:
            return True
        if "*" in self.allow_from:
            return True
        return source.phone_number in self.allow_from

    def _ensure_dependencies(self) -> None:
        """Make sure Node.js dependencies are installed in the bridge directory."""
        bridge_dir = Path(__file__).parent / "whatsapp_bridge"
        node_modules = bridge_dir / "node_modules"
        if not node_modules.exists():
            logger.info("WhatsApp bridge dependencies not found. Installing via npm...")
            try:
                subprocess.run(
                    ["npm", "install", "--no-audit", "--no-fund"],
                    cwd=str(bridge_dir),
                    shell=True,
                    check=True,
                    capture_output=True,
                    text=True
                )
                logger.info("WhatsApp bridge dependencies installed successfully.")
            except Exception as e:
                logger.error(f"Failed to install WhatsApp bridge dependencies: {e}")
                raise RuntimeError("Could not initialize WhatsApp bridge. Ensure Node.js is installed.")

    async def run(self, on_message: Callable[[str, WhatsAppEventSource], Awaitable[None]]) -> None:
        """Run WhatsApp channel handler."""
        self._on_message = on_message
        
        if self.mode == "cloud":
            logger.info("WhatsApp channel ready (webhook mode — register webhook at /webhook/whatsapp)")
            await self._stop_event.wait()
            return

        # Local mode: link device via Baileys bridge
        logger.info("Starting WhatsApp channel in local linked-device mode...")
        self._ensure_dependencies()
        
        auth_dir = Path.home() / ".cyberclaw" / "whatsapp_auth"
        auth_dir.mkdir(parents=True, exist_ok=True)
        
        bridge_script = Path(__file__).parent / "whatsapp_bridge" / "bridge.js"
        
        try:
            self._process = await asyncio.create_subprocess_exec(
                "node",
                str(bridge_script),
                str(auth_dir),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=None
            )
            
            self._listener_task = asyncio.create_task(self._read_stdout())
            await self._stop_event.wait()
            
        except Exception as e:
            logger.error(f"Failed to start WhatsApp bridge process: {e}")
            raise

    async def _read_stdout(self) -> None:
        """Read stdout from the Node.js bridge process."""
        if not self._process or not self._process.stdout:
            return
            
        while True:
            line_bytes = await self._process.stdout.readline()
            if not line_bytes:
                break
                
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue
                
            try:
                data = json.loads(line)
                msg_type = data.get("type")
                
                if msg_type == "connection":
                    status = data.get("status")
                    if status == "open":
                        self.linked_phone = data.get("phone")
                        logger.info(f"WhatsApp channel connected successfully! Linked number: {self.linked_phone}")
                    elif status == "close":
                        logger.warning(f"WhatsApp connection closed. Reason: {data.get('reason')}")
                        
                elif msg_type == "qr":
                    logger.warning("\n" + "="*70 + "\n"
                                   "[WARNING] WhatsApp linked device session is inactive.\n"
                                   "Please run in your terminal: \n"
                                   "   cyberclaw channels login --channel whatsapp\n"
                                   "to scan the pairing QR code and activate WhatsApp!\n" +
                                   "="*70 + "\n")
                                   
                elif msg_type == "message":
                    from_num = data.get("from")
                    body = data.get("body")
                    display_name = data.get("name", "")
                    
                    logger.info(f"Received WhatsApp message from {from_num}: {body[:30]}")
                    
                    is_self = False
                    if self.linked_phone and from_num == self.linked_phone:
                        is_self = True
                        
                    source = WhatsAppEventSource(
                        phone_number=from_num,
                        display_name=display_name,
                        is_self=is_self
                    )
                    
                    if self._on_message and self.is_allowed(source):
                        await self._on_message(body, source)
                        
            except json.JSONDecodeError:
                # Log non-JSON output (e.g. Baileys internals) at debug level
                logger.debug(f"[Node Bridge] {line}")
            except Exception as e:
                logger.error(f"Error handling WhatsApp bridge output: {e}")

    async def handle_webhook(self, payload: dict[str, Any]) -> None:
        """Process an incoming WhatsApp webhook payload (for cloud mode)."""
        if self.mode != "cloud" or not self._on_message:
            return

        entry = payload.get("entry", [])
        for e in entry:
            changes = e.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                for msg in messages:
                    if msg.get("type") == "text":
                        text = msg.get("text", {}).get("body", "")
                        from_number = msg.get("from", "")
                        contact = value.get("contacts", [{}])[0]
                        display_name = contact.get("profile", {}).get("name", "")

                        source = WhatsAppEventSource(
                            phone_number=from_number,
                            display_name=display_name,
                        )
                        if text and self.is_allowed(source):
                            await self._on_message(text, source)

    async def reply(self, content: str, source: WhatsAppEventSource) -> None:
        """Send a reply via WhatsApp (local bridge or Cloud API)."""
        if self.mode == "local":
            if not self._process or not self._process.stdin:
                logger.error("WhatsApp bridge process not running; cannot send reply.")
                return
                
            cmd = {
                "type": "send",
                "to": source.phone_number,
                "body": content
            }
            try:
                cmd_line = json.dumps(cmd) + "\n"
                self._process.stdin.write(cmd_line.encode("utf-8"))
                await self._process.stdin.drain()
                logger.debug(f"Outbound WhatsApp message written to bridge: {source.phone_number}")
            except Exception as e:
                logger.error(f"Failed to write to WhatsApp bridge: {e}")
            return

        # Cloud API Mode
        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed")
            return

        url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        body = {
            "messaging_product": "whatsapp",
            "to": source.phone_number,
            "type": "text",
            "text": {"body": content},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.error("WhatsApp send failed: %s", resp.text)

    async def stop(self) -> None:
        """Stop the WhatsApp channel and clean up subprocess."""
        self._stop_event.set()
        
        if self._process:
            try:
                # Terminate and wait for exit
                self._process.terminate()
                await self._process.wait()
            except Exception as e:
                logger.warning(f"Error terminating WhatsApp bridge: {e}")
            finally:
                self._process = None
                
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None
