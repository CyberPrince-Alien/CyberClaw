"""Task System -- background detached agent tasks with SQLite store."""

import asyncio, json, logging, sqlite3, time, uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

class TaskStatus(str, Enum):
    PENDING="pending"; RUNNING="running"; COMPLETED="completed"
    FAILED="failed"; CANCELLED="cancelled"

class TaskPriority(str, Enum):
    LOW="low"; NORMAL="normal"; HIGH="high"; CRITICAL="critical"

@dataclass
class Task:
    id: str; name: str; agent_id: str; instruction: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    result: str = ""; error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0; completed_at: float = 0.0
    timeout_seconds: int = 300; retry_count: int = 0; max_retries: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "agent_id": self.agent_id,
                "status": self.status.value, "priority": self.priority.value,
                "result": self.result[:500], "error": self.error,
                "created_at": self.created_at, "started_at": self.started_at,
                "completed_at": self.completed_at}

class TaskStore:
    """SQLite-backed task persistence."""
    def __init__(self, db_path: Path):
        self.db_path = db_path; db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row; self._init()

    def _init(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, name TEXT, agent_id TEXT, instruction TEXT,
                status TEXT DEFAULT 'pending', priority TEXT DEFAULT 'normal',
                result TEXT DEFAULT '', error TEXT DEFAULT '',
                created_at REAL, started_at REAL DEFAULT 0, completed_at REAL DEFAULT 0,
                timeout_seconds INT DEFAULT 300, retry_count INT DEFAULT 0,
                max_retries INT DEFAULT 1, metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        """); self._conn.commit()

    def save(self, t: Task):
        self._conn.execute(
            "INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (t.id, t.name, t.agent_id, t.instruction, t.status.value, t.priority.value,
             t.result, t.error, t.created_at, t.started_at, t.completed_at,
             t.timeout_seconds, t.retry_count, t.max_retries, json.dumps(t.metadata)))
        self._conn.commit()

    def get(self, task_id: str) -> Task | None:
        r = self._conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._to_task(r) if r else None

    def list_tasks(self, status: TaskStatus | None = None, limit: int = 50) -> list[Task]:
        if status:
            rows = self._conn.execute("SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?", (status.value, limit)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._to_task(r) for r in rows]

    def update_status(self, tid: str, status: TaskStatus, result: str = "", error: str = ""):
        now = time.time()
        sets = ["status=?"]; vals: list = [status.value]
        if status == TaskStatus.RUNNING: sets.append("started_at=?"); vals.append(now)
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            sets.append("completed_at=?"); vals.append(now)
        if result: sets.append("result=?"); vals.append(result)
        if error: sets.append("error=?"); vals.append(error)
        vals.append(tid)
        self._conn.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=?", vals)
        self._conn.commit()

    def cleanup_stale(self, max_age_hours: int = 72) -> int:
        cutoff = time.time() - max_age_hours * 3600
        r = self._conn.execute("DELETE FROM tasks WHERE status IN ('completed','failed','cancelled') AND completed_at<?", (cutoff,))
        self._conn.commit(); return r.rowcount

    @staticmethod
    def _to_task(r) -> Task:
        return Task(id=r["id"], name=r["name"], agent_id=r["agent_id"],
            instruction=r["instruction"], status=TaskStatus(r["status"]),
            priority=TaskPriority(r["priority"]), result=r["result"],
            error=r["error"], created_at=r["created_at"], started_at=r["started_at"],
            completed_at=r["completed_at"], timeout_seconds=r["timeout_seconds"],
            retry_count=r["retry_count"], max_retries=r["max_retries"],
            metadata=json.loads(r["metadata"]) if r["metadata"] else {})

    def close(self): self._conn.close()

class TaskExecutor:
    """Executes tasks with timeout, retry, and concurrency."""
    def __init__(self, store: TaskStore, max_concurrent: int = 3):
        self.store = store; self._sem = asyncio.Semaphore(max_concurrent)
        self._running: dict[str, asyncio.Task] = {}
        self._handlers: dict[str, Callable[[Task], Awaitable[str]]] = {}

    def register_handler(self, agent_id: str, handler: Callable[[Task], Awaitable[str]]):
        self._handlers[agent_id] = handler

    async def submit(self, name: str, agent_id: str, instruction: str,
                     priority: TaskPriority = TaskPriority.NORMAL, timeout: int = 300) -> Task:
        task = Task(id=str(uuid.uuid4())[:8], name=name, agent_id=agent_id,
                    instruction=instruction, priority=priority, timeout_seconds=timeout)
        self.store.save(task)
        self._running[task.id] = asyncio.create_task(self._execute(task))
        return task

    async def _execute(self, task: Task):
        async with self._sem:
            handler = self._handlers.get(task.agent_id)
            if not handler:
                self.store.update_status(task.id, TaskStatus.FAILED, error=f"No handler: {task.agent_id}")
                return
            self.store.update_status(task.id, TaskStatus.RUNNING)
            for attempt in range(task.max_retries + 1):
                try:
                    result = await asyncio.wait_for(handler(task), timeout=task.timeout_seconds)
                    self.store.update_status(task.id, TaskStatus.COMPLETED, result=result)
                    return
                except asyncio.TimeoutError:
                    if attempt >= task.max_retries:
                        self.store.update_status(task.id, TaskStatus.FAILED, error="Timeout")
                except asyncio.CancelledError:
                    self.store.update_status(task.id, TaskStatus.CANCELLED); return
                except Exception as e:
                    if attempt >= task.max_retries:
                        self.store.update_status(task.id, TaskStatus.FAILED, error=str(e))
            self._running.pop(task.id, None)

    def cancel(self, task_id: str) -> bool:
        t = self._running.get(task_id)
        if t and not t.done(): t.cancel(); return True
        return False

TASK_TOOL_SCHEMA = {"type": "function", "function": {
    "name": "spawn_task",
    "description": "Spawn a background task that runs independently.",
    "parameters": {"type": "object", "properties": {
        "name": {"type": "string"}, "instruction": {"type": "string"},
        "priority": {"type": "string", "enum": ["low","normal","high","critical"]},
        "timeout_seconds": {"type": "integer", "default": 300}},
    "required": ["name", "instruction"]}}}
