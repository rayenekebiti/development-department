#!/usr/bin/env python3
"""SubagentStop hook for the agents that change code.

If the agent's final report shows no sign that tests, checks or a browser verification ran, send it
back once to run them and paste the result. No model call. `stop_hook_active` guarantees one retry
at most, so it can never loop.
"""
import json
import re
import sys

EVIDENCE = re.compile(
    r"\b(\d+\s+(tests?|specs?|examples?|checks?)\s+(passed|passing|failed|ok)"
    r"|(passed|failed|passing|failing)\b.*\b(tests?|specs?)"
    r"|tests?\s+(pass|passed|fail|failed|ok|green|red)"
    r"|exit(ed)?\s+(code\s+)?\d|PASS\b|FAIL\b|✓|✔|✗|❌"
    r"|pytest|jest|vitest|mocha|playwright\s+test|cargo\s+test|go\s+test|npm\s+(run\s+)?test|pnpm\s+test"
    r"|yarn\s+test|bun\s+test|rspec|phpunit|dotnet\s+test|mvn\s+test|gradle\s+test|ctest"
    r"|tsc\b|eslint|ruff|mypy|pyright|clippy|typecheck|type[- ]check|build\s+(passed|succeeded|ok)"
    r"|screenshots?\s+(at|of|taken)|\b(375|768|1440)\s?px)",
    re.IGNORECASE,
)
# The agent stopped on purpose and said why (blocked, question, nothing to run).
EXPLAINED = re.compile(
    r"\b(couldn'?t|could not|can'?t|cannot|unable to)\s+(run|execute)|no tests? (exist|found|to run)"
    r"|not run|didn'?t run|did not run|blocked|need(s)? (your|a) (decision|answer)|question",
    re.IGNORECASE,
)


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    if event.get("stop_hook_active"):
        return 0
    msg = event.get("last_assistant_message") or ""
    if isinstance(msg, (list, dict)):
        msg = json.dumps(msg)
    if EVIDENCE.search(msg) or EXPLAINED.search(msg):
        return 0
    print(json.dumps({
        "decision": "block",
        "reason": "Your report shows no verification. Run the tests (and type checker/linter, or the "
                  "browser check for UI work) for what you changed, then end with the commands and their "
                  "pass/fail summary. If you couldn't run them, say why in one line and stop.",
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
