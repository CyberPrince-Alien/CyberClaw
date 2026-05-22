---
name: using-superpowers
description: Use when starting any conversation - establishes how to find and use skills, requiring Skill check before any complex response or action
---

<SUBAGENT-STOP>
If you were dispatched as a subagent to execute a specific task, skip this skill.
</SUBAGENT-STOP>

<EXTREMELY-IMPORTANT>
If you think there is even a 1% chance a skill might apply to what you are doing, you ABSOLUTELY MUST invoke and follow the skill.
IF A SKILL APPLIES TO YOUR TASK, YOU DO NOT HAVE A CHOICE. YOU MUST USE IT.
This is not negotiable. This is not optional.
</EXTREMELY-IMPORTANT>

## Instruction Priority

Superpowers skills override default agent prompt behavior, but **user instructions always take precedence**:

1. **User's explicit instructions** (CLAUDE.md, direct requests) — highest priority
2. **Superpowers skills** — override default system behavior where they conflict
3. **Default system prompt** — lowest priority

If the user says "don't use TDD" and a skill says "always use TDD," follow the user's instructions. The user is in control.

## How to Access Skills in CyberClaw

Skills are stored as Markdown directories in your workspace `skills/` directory. Check for relevant skills before starting a new task (e.g. brainstorming a spec, debugging, writing implementation plans, or executing tests).

# Using Skills

## The Rule

**Invoke relevant or requested skills BEFORE any response or action.** Even a 1% chance a skill might apply means that you should invoke the skill to check.

## Red Flags

These thoughts mean STOP—you're rationalizing and skipping discipline:
- "This is just a simple question" -> Questions are tasks. Check for skills.
- "I need more context first" -> Skill check comes BEFORE clarifying questions.
- "Let me explore the codebase first" -> Skills tell you HOW to explore.
- "I'll just do this one thing first" -> Check BEFORE doing anything.

## Skill Priority

When multiple skills could apply, use this order:
1. **Process skills first** (brainstorming, debugging) - these determine HOW to approach the task
2. **Implementation skills second** (TDD, subagent-driven-development) - these guide execution

**Related skills:**
- `brainstorming` - Use before writing code or drafting an implementation plan
- `test-driven-development` - Use during all code implementations and refactors
- `systematic-debugging` - Use whenever a bug, error, or test failure occurs
- `subagent-driven-development` - Use when executing complex multi-task plans
