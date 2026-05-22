"""Skill curator for scanning, lifecycle management, and LLM-based skill consolidation."""

import os
import time
import shutil
import logging
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, List, Dict, Any, Optional

from cyberclaw.utils.def_loader import parse_definition, write_definition

if TYPE_CHECKING:
    from cyberclaw.utils.config import Config
    from cyberclaw.core.agent import AgentSession

logger = logging.getLogger(__name__)


class SkillCurator:
    """Manages custom skill lifecycles (marking stale, archiving, and merging redundant skills)."""

    def __init__(self, config: "Config"):
        self.config = config

    def run_lifecycle_transition(self) -> List[str]:
        """Scan skills directory, archive skills > 90d unmodified, mark stale > 30d unmodified."""
        skills_path = self.config.skills_path
        if not skills_path.exists():
            return []

        archived_dir = self.config.workspace / "archived_skills"
        actions_taken = []

        for def_dir in list(skills_path.iterdir()):
            if not def_dir.is_dir() or def_dir.name.startswith("."):
                continue

            skill_file = def_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                mtime = os.path.getmtime(str(skill_file))
                age_days = (time.time() - mtime) / 86400.0

                # Archive after 90 days of inactivity
                if age_days >= 90:
                    archived_dir.mkdir(parents=True, exist_ok=True)
                    dest = archived_dir / def_dir.name
                    if dest.exists():
                        shutil.rmtree(str(dest))
                    shutil.move(str(def_dir), str(dest))
                    actions_taken.append(f"Archived skill '{def_dir.name}' (unmodified for {int(age_days)} days)")

                # Mark stale after 30 days of inactivity
                elif age_days >= 30:
                    content = skill_file.read_text(encoding="utf-8")

                    def _parse_fm(def_id, frontmatter, body):
                        return frontmatter, body

                    frontmatter, body = parse_definition(content, def_dir.name, _parse_fm)

                    if "name" in frontmatter and not frontmatter["name"].startswith("[stale]"):
                        frontmatter["name"] = f"[stale] {frontmatter['name']}"
                        write_definition(def_dir.name, frontmatter, body, skills_path, "SKILL.md")
                        actions_taken.append(f"Marked skill '{def_dir.name}' as stale")

            except Exception as e:
                logger.warning(f"Failed to curate skill '{def_dir.name}': {e}")

        return actions_taken

    async def run_consolidation(self, session: "AgentSession") -> List[str]:
        """Perform LLM analysis to detect redundant micro-skills and merge them."""
        import json

        skills = session.shared_context.skill_loader.discover_skills()
        # Only scan active non-stale skills for consolidation
        active_skills = [s for s in skills if not s.name.startswith("[stale]")]

        if len(active_skills) < 2:
            return []

        skills_summary = []
        for s in active_skills:
            skills_summary.append({
                "id": s.id,
                "name": s.name,
                "description": s.description
            })

        prompt = f"""You are the CyberClaw Skill Curator. Analyze the following list of active custom skills.
Identify any groups of skills that are redundant or have significant conceptual/semantic overlap (e.g. 'read-xml' and 'parse-xml').
Return a JSON list of consolidation recommendations with group_name (a clean URL-friendly hyphenated name, e.g. 'xml-handling'), skill_ids to merge, and a justification.
If no skills should be merged, return an empty list.

Skills List:
{json.dumps(skills_summary, indent=2)}

Return ONLY a valid JSON array. Do not include markdown code block formatting (like ```json). Just return the raw JSON text.
"""
        try:
            response, _ = await session.agent.llm.chat(
                [{"role": "user", "content": prompt}],
                []
            )

            # Extract raw JSON from possible markdown wrappers
            clean_res = response.strip()
            if clean_res.startswith("```json"):
                clean_res = clean_res[7:]
            if clean_res.endswith("```"):
                clean_res = clean_res[:-3]
            clean_res = clean_res.strip()

            recommendations = json.loads(clean_res)
            if not isinstance(recommendations, list) or not recommendations:
                return []

            actions_taken = []
            archived_dir = self.config.workspace / "archived_skills"
            archived_dir.mkdir(parents=True, exist_ok=True)

            for rec in recommendations:
                group_name = rec.get("group_name")
                skill_ids = rec.get("skill_ids")
                if not group_name or not skill_ids or len(skill_ids) < 2:
                    continue

                matching_skills = [s for s in active_skills if s.id in skill_ids]
                if len(matching_skills) < 2:
                    continue

                skills_details = "\n\n".join([
                    f"Skill ID: {s.id}\nName: {s.name}\nDescription: {s.description}\nInstructions:\n{s.content}"
                    for s in matching_skills
                ])

                merge_prompt = f"""You are consolidating the following overlapping skills:
{skills_details}

Write a single unified and comprehensive instructions body for a new consolidated skill named '{group_name}'.
Combine all guidelines, tips, and code blocks from the source skills into a structured, elegant markdown document.
Return ONLY the markdown body. Do not include any YAML frontmatter or title header.
"""
                merged_content, _ = await session.agent.llm.chat(
                    [{"role": "user", "content": merge_prompt}],
                    []
                )

                frontmatter = {
                    "name": group_name.replace("-", " ").title(),
                    "description": f"Consolidated skill merging: {', '.join(skill_ids)}"
                }

                write_definition(
                    group_name,
                    frontmatter,
                    merged_content.strip(),
                    self.config.skills_path,
                    "SKILL.md"
                )

                # Move merged skills to archive
                for s in matching_skills:
                    src_dir = self.config.skills_path / s.id
                    if src_dir.exists():
                        dest = archived_dir / s.id
                        if dest.exists():
                            shutil.rmtree(str(dest))
                        shutil.move(str(src_dir), str(dest))

                actions_taken.append(f"Merged {skill_ids} into new consolidated skill '{group_name}'")

            return actions_taken

        except Exception as e:
            logger.error(f"Error in skill consolidation pass: {e}")
            return []

    async def curate_skills_async(self, session: "AgentSession") -> None:
        """Helper to run both transitions and LLM consolidation in background."""
        # 1. Age transitions
        logger.info("Running custom skill lifecycle transitions...")
        transitions = self.run_lifecycle_transition()
        if transitions:
            logger.info(f"Skill transitions: {transitions}")

        # 2. Consolidation
        logger.info("Running custom skill semantic consolidation...")
        consolidations = await self.run_consolidation(session)
        if consolidations:
            logger.info(f"Skill consolidations: {consolidations}")
