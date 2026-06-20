# Implementation Plan: Create a minimal "hello" USR dynamic skill to validate the test_skill/register_skill pipeline.

## Context
USR skills are dynamic capabilities deployed as containers. A minimal skill needs a manifest, entrypoint handler, and test payload. We will keep the scope tiny to validate tooling health.

## Steps
1. Inspect workspace for existing skill templates or conventions.
2. Scaffold a minimal USR skill at skills/hello-test/ with manifest, handler, and test payload.
3. Run test_skill dry-run in the sandbox.
4. If tests pass, optionally register the skill for human review.
5. Report results and any errors encountered.
