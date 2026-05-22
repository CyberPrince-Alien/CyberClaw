"""FastAPI application with WebSocket, SSE streaming, and control-plane endpoints."""

import json
import time
import mimetypes
from typing import AsyncIterator

# Explicitly register standard MIME types to fix Windows Registry lookup errors
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

from fastapi import FastAPI, HTTPException, WebSocket, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field

from cyberclaw.core.agent import Agent
from cyberclaw.core.context import SharedContext
from cyberclaw.core.events import WebSocketEventSource
from cyberclaw.core.streaming import ChunkType


class ChatRequest(BaseModel):
    """Request body for direct API chat."""

    message: str = Field(..., min_length=1)
    agent_id: str | None = None
    session_id: str | None = None
    source: str = "api"
    stream: bool = False


class SessionSendRequest(BaseModel):
    """Send a message to an existing session."""
    message: str = Field(..., min_length=1)


class SessionSpawnRequest(BaseModel):
    """Create a new session."""
    agent_id: str | None = None
    source: str = "api"


class PairingApproveRequest(BaseModel):
    """Approve a pairing code."""
    channel: str
    code: str


class ConfigSetRequest(BaseModel):
    """Set a config value."""
    key: str
    value: str


class ProviderUpdateRequest(BaseModel):
    """Request body to update a specific provider."""
    provider_id: str
    api_key: str | None = None
    model: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    is_default: bool | None = None
    api_base: str | None = None



def _redact_config(value):
    """Return a JSON-serializable config snapshot with secrets redacted."""
    if isinstance(value, dict):
        redacted = {}
        for key, child in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("key", "token", "secret", "password")):
                redacted[key] = "***REDACTED***" if child else child
            else:
                redacted[key] = _redact_config(child)
        return redacted
    if isinstance(value, list):
        return [_redact_config(item) for item in value]
    return value


def create_app(context: SharedContext) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="CyberClaw Gateway",
        description="CyberClaw personal AI assistant — Gateway API",
        version="0.2.0",
    )
    app.state.context = context

    # Enable CORS for web clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health & Status ────────────────────────────────────────────
    @app.get("/health")
    async def health():
        """Return gateway health and basic runtime status."""
        return {
            "status": "ok",
            "version": "0.2.0",
            "uptime": time.time(),
            "default_agent": context.config.default_agent,
            "providers": [
                provider.id for provider in context.config.llm.providers if provider.enabled
            ],
            "channels_enabled": context.config.channels.enabled,
            "channels": [channel.platform_name for channel in context.channels],
            "sessions": len(context.history_store.list_sessions()),
            "plugins": getattr(context, 'plugin_registry', {}).loaded if hasattr(context, 'plugin_registry') else [],
        }

    @app.get("/metrics")
    async def metrics_prometheus():
        """Prometheus-compatible metrics endpoint."""
        from cyberclaw.core.metrics import get_metrics
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            get_metrics().to_prometheus(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/metrics/json")
    async def metrics_json():
        """JSON metrics endpoint."""
        from cyberclaw.core.metrics import get_metrics
        return get_metrics().to_dict()

    @app.get("/config")
    async def config_snapshot():
        """Return redacted runtime configuration."""
        return _redact_config(context.config.model_dump(mode="json"))

    @app.post("/config/set")
    async def config_set(request: ConfigSetRequest):
        """Update a config value via API."""
        import yaml
        try:
            parsed_value = yaml.safe_load(request.value)
            context.config.set_user(request.key, parsed_value)
            context.config.reload()
            return {"status": "ok", "key": request.key}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/config/update_provider")
    async def update_provider(request: ProviderUpdateRequest):
        """Update a specific provider's API key, model name, enabled status, priority, default flag, and API base URL."""
        import yaml
        config_path = context.config.workspace / "config.user.yaml"
        try:
            if not config_path.exists():
                data = {}
            else:
                with open(config_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}

            llm_data = data.setdefault("llm", {})
            providers = llm_data.setdefault("providers", [])

            # Find provider
            provider_entry = None
            for p in providers:
                if p.get("id") == request.provider_id:
                    provider_entry = p
                    break

            if not provider_entry:
                provider_entry = {
                    "id": request.provider_id,
                    "provider": "nvidia_nim" if request.provider_id == "nvidia" else request.provider_id,
                    "model": request.model or "gpt-4",
                    "api_key": request.api_key or ("ollama" if request.provider_id == "ollama" else ""),
                    "priority": request.priority or 1,
                    "enabled": request.enabled if request.enabled is not None else False
                }
                providers.append(provider_entry)

            # Update fields
            if request.model is not None:
                provider_entry["model"] = request.model
            if request.api_key is not None and request.api_key != "***REDACTED***" and request.api_key.strip() != "":
                provider_entry["api_key"] = request.api_key
            if request.enabled is not None:
                provider_entry["enabled"] = request.enabled
            if request.priority is not None:
                provider_entry["priority"] = request.priority
            if request.api_base is not None:
                if request.api_base.strip() == "":
                    provider_entry.pop("api_base", None)
                else:
                    provider_entry["api_base"] = request.api_base.strip()

            # If is_default is true, update default_provider
            if request.is_default:
                llm_data["default_provider"] = request.provider_id

            # Write back to yaml
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f)

            # Reload config
            context.config.reload()

            return {"status": "ok", "provider_id": request.provider_id}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


    # ── Channels ───────────────────────────────────────────────────
    @app.get("/channels")
    async def channels_snapshot():
        """Return configured channel status."""
        return {
            "enabled": context.config.channels.enabled,
            "active": [channel.platform_name for channel in context.channels],
        }

    # ── Sessions ───────────────────────────────────────────────────
    @app.get("/sessions")
    async def sessions():
        """Return known sessions."""
        return [session.model_dump() for session in context.history_store.list_sessions()]

    @app.get("/sessions/{session_id}/messages")
    async def session_messages(session_id: str):
        """Return messages for one session."""
        session = context.history_store.get_session_info(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return [
            message.model_dump()
            for message in context.history_store.get_messages(session_id)
        ]

    @app.post("/sessions/{session_id}/send")
    async def session_send(session_id: str, request: SessionSendRequest):
        """Send a message to an existing session."""
        session_info = context.history_store.get_session_info(session_id)
        if not session_info:
            raise HTTPException(status_code=404, detail="Session not found")

        agent_def = context.agent_loader.load(session_info.agent_id)
        agent = Agent(agent_def, context)
        session = agent.resume_session(session_id)
        response = await session.chat(request.message)
        return {"session_id": session_id, "response": response}

    @app.post("/sessions/spawn")
    async def session_spawn(request: SessionSpawnRequest):
        """Create a new session."""
        agent_id = request.agent_id or context.config.default_agent
        try:
            agent_def = context.agent_loader.load(agent_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))
        agent = Agent(agent_def, context)
        source = WebSocketEventSource(user_id=request.source)
        session = agent.new_session(source)
        return {"session_id": session.session_id, "agent_id": agent_id}

    # ── Chat (batch + streaming) ───────────────────────────────────
    @app.post("/chat")
    async def chat(request: ChatRequest):
        """Run a direct API chat turn. Set stream=true for SSE."""
        agent_id = request.agent_id or context.config.default_agent
        try:
            agent_def = context.agent_loader.load(agent_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e))

        source = WebSocketEventSource(user_id=request.source)
        agent = Agent(agent_def, context)

        if request.session_id:
            try:
                session = agent.resume_session(request.session_id)
            except ValueError:
                session = agent.new_session(source, session_id=request.session_id)
        else:
            session = agent.new_session(source)

        if request.stream:
            async def sse_generator() -> AsyncIterator[str]:
                async for chunk in session.chat_stream(request.message):
                    yield chunk.to_sse()

            return StreamingResponse(
                sse_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        response = await session.chat(request.message)
        return {
            "session_id": session.session_id,
            "agent_id": agent_id,
            "response": response,
        }

    # ── Pairing ────────────────────────────────────────────────────
    @app.get("/pairing/pending")
    async def pairing_pending():
        """List pending pairing codes."""
        if hasattr(context, 'pairing_store') and context.pairing_store:
            return context.pairing_store.list_pending()
        return []

    @app.post("/pairing/approve")
    async def pairing_approve(request: PairingApproveRequest):
        """Approve a pairing code."""
        if not hasattr(context, 'pairing_store') or not context.pairing_store:
            raise HTTPException(status_code=501, detail="Pairing not configured")
        result = context.pairing_store.approve(request.channel, request.code)
        if result:
            return {"status": "approved", "sender_id": result}
        raise HTTPException(status_code=404, detail="Pairing code not found")

    # ── Memory ─────────────────────────────────────────────────────
    @app.get("/memory/search")
    async def memory_search(q: str = ""):
        """Search through vault memories."""
        memories_path = context.config.memories_path
        if not memories_path.exists():
            return {"results": []}

        results = []
        for fpath in memories_path.rglob("*.md"):
            try:
                content = fpath.read_text(encoding="utf-8")
                if q.lower() in content.lower():
                    results.append({
                        "path": str(fpath.relative_to(memories_path)),
                        "preview": content[:300],
                    })
            except Exception:
                continue
        return {"query": q, "results": results[:20]}

    # ── WebSocket ──────────────────────────────────────────────────
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time event streaming and chat."""
        await websocket.accept()
        if context.websocket_worker is None:
            await websocket.close(code=1013, reason="WebSocket not available")
            return
        await context.websocket_worker.handle_connection(websocket)

    # ── Model Catalog ──────────────────────────────────────────────
    @app.get("/models")
    async def list_models():
        """List all models in the catalog."""
        from cyberclaw.core.model_catalog import get_catalog
        cat = get_catalog()
        return {
            "models": cat.to_dict(),
            "providers": cat.list_providers(),
            "total": len(cat.list_models()),
        }

    @app.get("/models/{provider}/{model}")
    async def get_model(provider: str, model: str):
        """Get details for a specific model."""
        from cyberclaw.core.model_catalog import get_catalog
        entry = get_catalog().get(provider, model)
        if not entry:
            raise HTTPException(404, "Model not found")
        return entry.to_dict()

    @app.get("/models/cheapest")
    async def cheapest_model(vision: bool = False, reasoning: bool = False):
        """Find the cheapest model matching requirements."""
        from cyberclaw.core.model_catalog import get_catalog
        entry = get_catalog().find_cheapest(needs_vision=vision, needs_reasoning=reasoning)
        return entry.to_dict() if entry else {"error": "No matching model"}

    # ── Tasks API ──────────────────────────────────────────────────
    @app.get("/tasks")
    async def list_tasks(status: str | None = None):
        """List background tasks."""
        from cyberclaw.core.tasks import TaskStore, TaskStatus as TS
        db_path = context.config.workspace / ".tasks" / "tasks.db"
        if not db_path.exists():
            return {"tasks": []}
        store = TaskStore(db_path)
        st = TS(status) if status else None
        tasks = store.list_tasks(st)
        store.close()
        return {"tasks": [t.to_dict() for t in tasks]}

    # ── Web UI (static files) ──────────────────────────────────────
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, RedirectResponse

    ui_dir = Path(__file__).parent / "ui"

    @app.get("/")
    async def redirect_root_to_ui():
        """Redirect root path to the Web UI."""
        return RedirectResponse(url="/ui")

    @app.get("/ui")
    async def serve_ui():
        """Serve the CyberClaw Web UI."""
        return FileResponse(ui_dir / "index.html", media_type="text/html")

    # Mount static assets
    if ui_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(ui_dir)), name="ui-static")

    return app

