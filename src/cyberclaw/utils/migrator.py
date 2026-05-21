"""Migrator helper for importing database and settings from OpenClaw."""

import logging
import sqlite3
import yaml
from pathlib import Path
from typing import Any

from rich.console import Console

from cyberclaw.utils.config import Config
from cyberclaw.core.history_sqlite import SQLiteHistoryStore

logger = logging.getLogger(__name__)
console = Console()


class OpenClawMigrator:
    """Migrates configurations and history files from OpenClaw to CyberClaw."""

    def __init__(self, config: Config):
        self.config = config

    def migrate(self, source_path: Path) -> None:
        """Examines type of source_path and triggers corresponding migration."""
        source_path = Path(source_path)
        if not source_path.exists():
            console.print(f"[red]Source path does not exist:[/red] {source_path}")
            return

        if source_path.suffix in (".yaml", ".yml"):
            self.migrate_config(source_path)
        elif source_path.suffix in (".db", ".sqlite", ".sqlite3"):
            self.migrate_history_db(source_path)
        else:
            console.print("[red]Unsupported file format. Please provide a YAML config or SQLite database.[/red]")

    def migrate_config(self, config_path: Path) -> None:
        """Parses OpenClaw config files and merges keys into config.user.yaml."""
        console.print(f"Reading OpenClaw configuration: [cyan]{config_path}[/cyan]")
        try:
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}

            # Map OpenClaw LLM keys
            llm_section = data.get("llm", {})
            api_key = llm_section.get("api_key") or data.get("api_key")
            provider = llm_section.get("provider") or data.get("provider")
            model = llm_section.get("model") or data.get("model")

            if api_key:
                # Store in CyberClaw user configuration
                dest_path = self.config.workspace / "config.user.yaml"
                current_data = {}
                if dest_path.exists():
                    with open(dest_path) as f:
                        current_data = yaml.safe_load(f) or {}

                # Create provider entry
                prov_id = provider or "openai"
                provider_entry = {
                    "id": prov_id,
                    "provider": prov_id,
                    "model": model or "gpt-4o",
                    "api_key": api_key,
                    "enabled": True,
                }

                if "llm" not in current_data:
                    current_data["llm"] = {}
                if "providers" not in current_data["llm"]:
                    current_data["llm"]["providers"] = []

                # Avoid duplicates
                exists = False
                for p in current_data["llm"]["providers"]:
                    if p.get("id") == prov_id:
                        p["api_key"] = api_key
                        p["model"] = model or p.get("model", "gpt-4o")
                        exists = True
                        break

                if not exists:
                    current_data["llm"]["providers"].append(provider_entry)

                with open(dest_path, "w") as f:
                    yaml.safe_dump(current_data, f, sort_keys=False)

                console.print(f"[green]Successfully migrated LLM settings to config.user.yaml![/green]")
            else:
                console.print("[yellow]No API key found in the configuration file.[/yellow]")

        except Exception as e:
            console.print(f"[red]Failed to migrate config file:[/red] {e}")

    def migrate_history_db(self, db_path: Path) -> None:
        """Migrates conversation logs/sessions from OpenClaw sqlite file."""
        console.print(f"Reading OpenClaw SQLite history database: [cyan]{db_path}[/cyan]")
        
        # Connect to target SQLite history database of CyberClaw
        dest_store = SQLiteHistoryStore.from_config(self.config)
        
        try:
            src_conn = sqlite3.connect(db_path)
            src_cursor = src_conn.cursor()

            # Attempt to query messages/history from typical tables
            # Let's inspect source database tables
            src_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [t[0] for t in src_cursor.fetchall()]

            if "history" in tables or "messages" in tables:
                table_name = "history" if "history" in tables else "messages"
                src_cursor.execute(f"SELECT * FROM {table_name}")
                rows = src_cursor.fetchall()
                
                # Fetch column headers
                cols = [c[0] for c in src_cursor.description]
                
                # Insert records dynamically
                count = 0
                for row in rows:
                    row_dict = dict(zip(cols, row))
                    session_id = row_dict.get("session_id") or row_dict.get("conversation_id") or "migrated-session"
                    role = row_dict.get("role") or "user"
                    content = row_dict.get("content") or ""
                    timestamp = row_dict.get("timestamp") or row_dict.get("created_at") or 0.0

                    if content:
                        # Append session message to CyberClaw history
                        dest_store.append_message(
                            session_id=session_id,
                            role=role,
                            content=content,
                            # Timestamp and extra metadata can be injected if supported
                        )
                        count += 1
                
                console.print(f"[green]Successfully migrated {count} message history records to CyberClaw history database![/green]")
            else:
                console.print(f"[red]No recognized history or message tables found. Available tables: {tables}[/red]")
            
            src_conn.close()
        except Exception as e:
            console.print(f"[red]Failed to migrate database history:[/red] {e}")
        finally:
            dest_store.close()
