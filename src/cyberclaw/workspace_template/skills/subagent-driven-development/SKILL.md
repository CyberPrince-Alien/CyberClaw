---
name: subagent-driven-development
description: Use when executing implementation plans with independent tasks using subagents
---

# Subagent-Driven Development for CyberClaw

## Overview

Execute complex implementation plans by dispatching a fresh, specialized subagent per task, with a two-stage quality gate after completion: a spec compliance review first, followed by a code quality review.

**Why subagents:** You delegate work to specialized agents with isolated context. This preserves your own coordinator history and context, prevents LLM context pollution, and ensures high-focus execution.

## The Operational Protocol

For each task in the implementation plan, follow this loop:

### Step 1: Dispatch Implementer Subagent
- Select the appropriate agent definition (e.g. standard developer or standard agent).
- Provide the exact task description, file paths, and required code snippets.
- Answer any clarifying questions the implementer subagent asks before letting it proceed.

### Step 2: Spec Compliance Review (Gate 1)
- Once the implementer is done, dispatch a specialized `spec-reviewer` or verification agent.
- The reviewer must confirm:
  - All spec requirements for this task are met.
  - No speculative features or scope creep were added.
- If there are gaps, dispatch the implementer again to fix them.

### Step 3: Code Quality Review (Gate 2)
- Once the spec is approved, dispatch a specialized `quality-reviewer` or architect agent.
- The reviewer evaluates code aesthetics, readability, helper abstraction, and Magic numbers.
- If issues are found, the implementer fixes them.

### Step 4: Mark Complete
- Only after both reviews pass, mark the task as complete in `task.md` and proceed to the next task.

## Red Flags
- Skipping reviews (spec compliance or code quality) to save time.
- Proceeding to the next task while either review gate has open issues.
- Letting the implementer self-review replace independent review gates.
- Making the subagent read the entire plan file (provide the specific task text instead).
