---
name: brainstorming
description: Use when you have a feature request or complex change, before writing an implementation plan
---

# Socratic Brainstorming for CyberClaw

## Overview

Brainstorming is a collaborative process to refine feature requirements and designs before writing an implementation plan or modifying code.
**Core principle:** Step back, tease out a clear spec, validate it in readable chunks with the user, and lock down requirements first.

## The Workflow

1. **Step Back**: When the user requests a new feature or complex refactor, do not start coding immediately. Announce that you are using the brainstorming skill to align on requirements.
2. **Socratic Questions**: Ask 2-3 focused clarifying questions about:
   - Target audience and exact use case.
   - Intended user interface or command-line behavior.
   - Edge cases, error handling preferences, or performance concerns.
3. **Draft a Sectioned Spec**: Present the proposed specification in short, digestible chunks (e.g. Core Features, Interface Design, Data Structure). Ask the user to validate each chunk.
4. **Iterate and Finalize**: Refine the design based on user feedback. Once the user signs off, write it down as a specification document (e.g., in a markdown file or artifact).
5. **Proceed to Planning**: Only after the spec is approved should you proceed to drafting a detailed step-by-step implementation plan.

## Red Flags - STOP and Brainstorm
- You are not 100% sure what the user wants but start writing code anyway.
- The requirements are underspecified or leave major architectural decisions unresolved.
- You are adding speculative features (scope creep) that the user did not explicitly request.
- You write code first and "explain the design" later.
