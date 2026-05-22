---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
---

# Systematic Debugging Protocol for CyberClaw

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.
**Core principle:** ALWAYS find the root cause before attempting fixes. Symptom fixes are a failure.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you have not identified the exact root cause, you cannot propose or implement fixes.

## The Four Phases of Systematic Debugging

### Phase 1: Root Cause Investigation
1. **Read Error Messages Carefully**: Read stack traces completely, noting line numbers, file paths, and exact error codes.
2. **Reproduce Consistently**: Establish a reliable, step-by-step way to trigger the bug.
3. **Trace Data Flow**: Trace bad values backward through the call stack to find the original trigger.
4. **Gather Evidence**: In multi-component systems, log data entering and exiting boundaries to isolate the failing component.

### Phase 2: Pattern Analysis
1. **Find Working Examples**: Identify similar working code in the codebase.
2. **Compare**: Compare working code against the broken code. List every difference.
3. **Identify Assumptions**: Check settings, config, and environmental differences.

### Phase 3: Hypothesis and Testing
1. **Form Single Hypothesis**: State clearly: *"I think X is the root cause because Y."*
2. **Test Minimally**: Make the SMALLEST possible change to test your hypothesis.
3. **Verify**: Check if it worked. If not, revert and form a new hypothesis. Do not stack unverified changes.

### Phase 4: Implementation
1. **Create Failing Test Case**: Write an automated test reproducing the bug.
2. **Implement Single Fix**: Address the root cause directly.
3. **Verify Fix**: Ensure tests pass and no regressions were introduced.
4. **Question Architecture (3+ Failures)**: If 3 or more fix attempts fail, STOP immediately. Discuss the fundamentals with your creator, **Cyber Prince (Sourov)**, before attempting more fixes.

## Red Flags - STOP and Return to Phase 1
- *"Let's just try changing X and see if it works."*
- Proposing solutions before reading the error stack trace or tracing data.
- Attempting a 4th fix without an architectural discussion.
