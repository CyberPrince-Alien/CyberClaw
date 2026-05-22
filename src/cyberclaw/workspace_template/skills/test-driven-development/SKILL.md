---
name: test-driven-development
description: Use when implementing any feature or bugfix, before writing implementation code
---

# Test-Driven Development (TDD) for CyberClaw

## Overview

Write the test first. Watch it fail. Write minimal code to pass.
**Core principle:** If you didn't watch the test fail, you don't know if it tests the right thing.

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Write code before the test? Delete it. Start over.
No exceptions:
- Don't keep it as "reference"
- Don't "adapt" it while writing tests
- Delete means delete. Implement fresh from tests. Period.

## The Red-Green-Refactor Cycle

1. **RED - Write Failing Test**
   - Write one minimal test showing what should happen.
   - Clear name, tests real behavior, focuses on one thing.
   - Use real code (no mocks unless absolutely unavoidable).

2. **Verify RED - Watch It Fail**
   - Run the test suite and watch the test fail.
   - Confirm it fails because the feature is missing (not due to syntax/typo errors).
   - If it passes immediately, your test is invalid. Fix it.

3. **GREEN - Minimal Code**
   - Write the simplest possible code to make the test pass.
   - Do not add extra features, do not "improve" or over-engineer beyond the test.
   - YAGNI (You Aren't Gonna Need It).

4. **Verify GREEN - Watch It Pass**
   - Run the test suite and ensure it passes successfully.
   - Confirm other tests still pass without regressions.

5. **REFACTOR - Clean Up**
   - After the tests are green, remove duplication, improve variable/function names, and extract helpers.
   - Keep tests green.

## Common Rationalizations to Avoid
- *"Too simple to test"* -> Simple code breaks too. Test takes 30 seconds.
- *"I'll test after"* -> Tests passing immediately prove nothing.
- *"TDD will slow me down"* -> TDD is much faster than debugging after commits.
- *"Already manually tested"* -> Manual testing is ad-hoc, has no record, and cannot be re-run easily.

## Verification Checklist
Before marking work complete:
- [ ] Every new function/method has a test.
- [ ] Watched each test fail before implementing.
- [ ] Each test failed for the expected reason.
- [ ] Wrote the minimal code to pass.
- [ ] All tests pass cleanly without errors or warnings.
