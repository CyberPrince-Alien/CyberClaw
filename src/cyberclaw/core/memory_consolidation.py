"""Two-Phase Memory Consolidation engine for CyberClaw."""

import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cyberclaw.core.agent import AgentSession

logger = logging.getLogger(__name__)


async def consolidate_session_memories(session: "AgentSession") -> None:
    """Consolidate current conversation session memories in two phases.
    
    Phase 1: Rollout facts extraction using the active LLM, stashing into SQLite fact store.
    Phase 2: Sync to local git repository, compile MEMORY.md and skills templates, commit.
    """
    messages = session.state.messages
    if not messages:
        logger.info("No messages in session to consolidate.")
        return

    # 1. Format conversation transcript
    transcript = ""
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if content:
            transcript += f"{role.upper()}: {content}\n\n"

    if not transcript.strip():
        return

    # 2. Extract facts via LLM (Phase 1)
    prompt = (
        "Analyze the following conversation transcript between a user and an AI assistant. "
        "Extract key facts, learnings, configuration parameters, user preferences, project details, code heuristics, and other information that would be useful for future sessions.\n"
        "Format the output as a valid JSON array of objects. Do not include any markdown fences or explanation. Only output the JSON array.\n"
        "Each object in the array must have the following fields:\n"
        "- 'content': the textual content of the fact (e.g., 'User prefers Python for data science scripts', 'The project codebase uses FastAPI for its backend').\n"
        "- 'category': the category classification (e.g., 'general', 'git', 'project', 'user').\n"
        "- 'tags': comma-separated tags (e.g., 'python,fastapi,backend').\n"
        "- 'trust_score': a float value between 0.0 and 1.0 indicating your confidence in the fact.\n"
        "- 'entities': a list of key strings representing entities, code variables, or technologies associated with the fact.\n\n"
        "If no new facts are found, return an empty array `[]`.\n\n"
        f"Transcript:\n{transcript}"
    )

    try:
        res_content, _ = await session.agent.llm.chat([{"role": "user", "content": prompt}])
        res_content = res_content.strip()
        
        # Clean up markdown code fences if present
        if res_content.startswith("```"):
            lines = res_content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            res_content = "\n".join(lines).strip()

        facts = json.loads(res_content)
        if not isinstance(facts, list):
            logger.warning("LLM fact extraction did not return a list.")
            facts = []
    except Exception as e:
        logger.error(f"Error during Phase 1 memory extraction: {e}")
        facts = []

    # 3. Insert facts into SQLite facts store
    from cyberclaw.core.holographic.store import HolographicStore
    db_path = session.shared_context.config.memories_path / "holographic_memory.db"
    store = HolographicStore(db_path)

    for fact in facts:
        if not isinstance(fact, dict) or "content" not in fact:
            continue
        try:
            store.add_fact(
                content=fact["content"],
                category=fact.get("category", "general") or "general",
                tags=fact.get("tags", "") or "",
                trust_score=float(fact.get("trust_score", 0.5)),
                entities=fact.get("entities", None)
            )
        except Exception as e:
            logger.error(f"Failed to add stashed memory fact: {e}")

    # 4. Deduplicate database facts
    try:
        conn = store._conn
        cursor = conn.cursor()
        cursor.execute("SELECT fact_id, content, trust_score FROM facts")
        rows = cursor.fetchall()
        
        seen = {}
        for r in rows:
            c = r["content"].strip().lower()
            fid = r["fact_id"]
            trust = r["trust_score"]
            if c in seen:
                old_fid, old_trust = seen[c]
                if trust > old_trust:
                    cursor.execute("DELETE FROM facts WHERE fact_id = ?", (old_fid,))
                    seen[c] = (fid, trust)
                else:
                    cursor.execute("DELETE FROM facts WHERE fact_id = ?", (fid,))
            else:
                seen[c] = (fid, trust)
        conn.commit()
    except Exception as e:
        logger.error(f"Facts database deduplication error: {e}")

    # 5. Git consolidation (Phase 2)
    try:
        memories_git_dir = Path.home() / ".cyberclaw" / "memories"
        memories_git_dir.mkdir(parents=True, exist_ok=True)

        if not (memories_git_dir / ".git").exists():
            subprocess.run(["git", "init"], cwd=memories_git_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.name", "CyberClaw Memory Consolidator"], cwd=memories_git_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "memory@cyberclaw.ai"], cwd=memories_git_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Retrieve all facts from store
        cursor = store._conn.cursor()
        cursor.execute("SELECT content, category, tags, trust_score FROM facts ORDER BY category, created_at DESC")
        all_facts = cursor.fetchall()

        # Write MEMORY.md
        memory_md_content = "# CyberClaw Holographic Memory\n\n"
        memory_md_content += f"Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"

        facts_by_cat = defaultdict(list)
        for f in all_facts:
            facts_by_cat[f["category"]].append(f)

        for cat, items in sorted(facts_by_cat.items()):
            memory_md_content += f"## {cat.capitalize()}\n"
            for item in items:
                tags_str = f" [tags: {item['tags']}]" if item['tags'] else ""
                memory_md_content += f"- {item['content']}{tags_str} (trust: {item['trust_score']})\n"
            memory_md_content += "\n"

        (memories_git_dir / "MEMORY.md").write_text(memory_md_content, encoding="utf-8")

        # Compile reusable slash-command skills
        skills_dir = memories_git_dir / "skills"
        skills_dir.mkdir(exist_ok=True)

        # Clean existing skills to update them
        for existing in skills_dir.glob("*.md"):
            try:
                existing.unlink()
            except Exception:
                pass

        for cat, items in facts_by_cat.items():
            skill_file = skills_dir / f"{cat}.md"
            skill_content = f"# System Heuristics for: {cat.capitalize()}\n\n"
            skill_content += f"Below are the consolidated facts and user preferences for context category '{cat}':\n\n"
            for item in items:
                skill_content += f"- {item['content']}\n"
            skill_content += "\nUse these guidelines during interaction when the topic is related to this category.\n"
            skill_file.write_text(skill_content, encoding="utf-8")

        # Commit to Git
        subprocess.run(["git", "add", "."], cwd=memories_git_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=memories_git_dir)
        if diff_res.returncode != 0:
            commit_msg = f"Consolidate memory at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=memories_git_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Holographic memory committed to local git repository successfully.")
    except Exception as e:
        logger.error(f"Error during Phase 2 Git consolidation: {e}")
    finally:
        store.close()
