#!/usr/bin/env python3
"""Auto-continue loop for team-lead, driven by the STATUS line it ends each turn with.

  stop   (Stop hook)              STATUS: IN PROGRESS -> keep working, without waiting for the user.
                                  STATUS: NEEDS YOU / BLOCKED / VERIFIED -> stop and let the user read it.
                                  No STATUS line -> do nothing (every other session is unaffected).
  reset  (UserPromptSubmit hook)  A user message resets the loop's counters.

Safety: stops after TEAM_LOOP_MAX automatic continues in a row (default 40), and when the same
"next:" step comes up 4 times in a row (no progress). No model calls.
"""
import json
import os
import re
import sys

MAX = int(os.environ.get("TEAM_LOOP_MAX", "40"))
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "hooks-state", "team-loop")
STATUS = re.compile(r"STATUS:\s*\**\s*(VERIFIED|IN PROGRESS|NEEDS YOU|BLOCKED)\b[\s\-–—:]*(.*)", re.I)


def state_path(session):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session or "unknown")
    return os.path.join(STATE_DIR, safe + ".json")


def load(session):
    try:
        with open(state_path(session)) as f:
            return json.load(f)
    except Exception:
        return {"count": 0, "last_next": "", "repeats": 0}


def save(session, st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_path(session), "w") as f:
        json.dump(st, f)


def clear(session):
    try:
        os.remove(state_path(session))
    except OSError:
        pass


def last_text_from_transcript(path):
    """Fallback when the event has no last_assistant_message: last assistant text in the JSONL."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-200:]
    except Exception:
        return ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
            if any(t.strip() for t in texts):
                return "\n".join(texts)
    return ""


def on_stop(event):
    session = event.get("session_id", "")
    msg = event.get("last_assistant_message")
    if isinstance(msg, (list, dict)):
        msg = json.dumps(msg)
    if not msg:
        msg = last_text_from_transcript(event.get("transcript_path", ""))
    matches = STATUS.findall(msg or "")
    if not matches:
        return
    status, rest = matches[-1]
    status = status.upper()
    if status != "IN PROGRESS":
        clear(session)
        return

    nxt = re.sub(r"^\s*next\s*:\s*", "", rest.strip(), flags=re.I).strip("* ")[:300]
    st = load(session)
    st["count"] += 1
    st["repeats"] = st["repeats"] + 1 if nxt and nxt == st["last_next"] else 0
    st["last_next"] = nxt

    if st["count"] > MAX:
        clear(session)
        print(json.dumps({"systemMessage": f"Team loop paused after {MAX} automatic continues. "
                                           "Reply to let it keep going."}))
        return
    if st["repeats"] >= 3:
        clear(session)
        print(json.dumps({"systemMessage": "Team loop paused: the same next step came up 4 times in a row "
                                           f"without progress ({nxt[:120]}). Reply to steer it."}))
        return

    save(session, st)
    print(json.dumps({
        "decision": "block",
        "reason": f"Team loop (auto-continue {st['count']}/{MAX}): keep going with: {nxt or 'the next step'}. "
                  "Don't wait for the user. If you need a decision, use AskUserQuestion; if the user must "
                  "act outside the chat, end with STATUS: NEEDS YOU. End every turn with a STATUS line.",
    }))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "stop"
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    if mode == "reset":
        clear(event.get("session_id", ""))
    else:
        on_stop(event)
    return 0


if __name__ == "__main__":
    sys.exit(main())
