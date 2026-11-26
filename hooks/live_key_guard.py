#!/usr/bin/env python3
"""PreToolUse hook (all sessions and agents): block tool calls that carry a live payment secret.

Keeps payment work in test mode. Matches Stripe live secret and restricted keys. Publishable keys
(pk_live_) are public by design and pass. The key itself is never echoed back.
"""
import json
import re
import sys

LIVE_SECRET = re.compile(r"\b(sk|rk)_live_[0-9A-Za-z]{10,}")


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    blob = json.dumps(event.get("tool_input") or {})
    if LIVE_SECRET.search(blob):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Blocked: this call contains a live Stripe secret key. Use a test-mode "
                                        "key (sk_test_...) and read keys from env vars by name; never write, "
                                        "print or send live secrets.",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
