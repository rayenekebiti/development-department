#!/usr/bin/env python3
"""PreToolUse(Bash) hook for read-only agents: security-reviewer, code-reviewer, codebase-scout.

Denies shell commands that change files, git state or installed packages. Best-effort: it stops
accidental writes, not a determined bypass. Running tests, linters and builds stays allowed.
"""
import json
import re
import sys

WRITE_CMDS = {
    "rm", "rmdir", "mv", "cp", "mkdir", "touch", "chmod", "chown", "ln", "tee", "truncate",
    "dd", "install", "shred", "unlink", "patch", "rsync",
}
GIT_WRITE = re.compile(
    r"^git\s+(?:-C\s+\S+\s+)?(commit|push|pull|checkout|switch|reset|restore|clean|rebase|merge|"
    r"stash|apply|am|cherry-pick|revert|add|rm|mv|tag|init|clone|fetch|gc|prune|worktree|submodule|"
    r"branch\s+.*-[dDmMcC]\b|config\s+(?!--get|-l|--list))"
)
PKG_WRITE = re.compile(
    r"^(npm|pnpm|yarn|bun)\s+(i|install|add|remove|rm|uninstall|update|upgrade|ci|link|publish|dedupe)\b"
    r"|^(pip3?|uv\s+pip|pipx)\s+(install|uninstall)\b|^uv\s+(add|remove|sync|lock)\b"
    r"|^(cargo|go)\s+(install|add|remove|get|mod\s+tidy)\b|^(gem|brew|apt|apt-get|dnf|pacman)\s+"
    r"|^poetry\s+(add|remove|install|update|lock)\b|^composer\s+(require|remove|install|update)\b"
)
INPLACE = re.compile(r"\b(sed|perl|ruby)\b[^|;&]*\s-[a-zA-Z]*i|\s--(fix|write)\b|\s-w\b(?=.*\b(gofmt|black)\b)")
SAFE_REDIRECT = re.compile(r"\d?>>?\s*/dev/null|\d?>&\d|&>\s*/dev/null")
PREFIXES = {"sudo", "doas", "env", "command", "exec", "nohup", "nice", "time", "timeout", "xargs"}


def segments(cmd):
    for part in re.split(r"\|\||&&|[;|\n]|\$\(|`", cmd):
        words = part.strip().split()
        while words and (words[0] in PREFIXES or re.match(r"^\w+=", words[0]) or words[0].startswith("-")):
            words.pop(0)
        if words:
            yield " ".join(words)


def reason_for(cmd):
    stripped = SAFE_REDIRECT.sub("", cmd)
    # Ignore '>' inside quotes (e.g. grep '->' patterns) before checking for file redirects.
    unquoted = re.sub(r"'[^']*'|\"[^\"]*\"", "''", stripped)
    if re.search(r"(?<![=<>-])>{1,2}(?!=)", unquoted):
        return "redirects output into a file"
    if INPLACE.search(" " + cmd):
        return "edits files in place"
    for seg in segments(unquoted):
        first = seg.split()[0].rsplit("/", 1)[-1]
        if first in WRITE_CMDS:
            return f"runs `{first}`, which changes files"
        if GIT_WRITE.search(seg):
            return "changes git state"
        if PKG_WRITE.search(seg):
            return "installs or removes packages"
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (event.get("tool_input") or {}).get("command") or ""
    why = reason_for(cmd)
    if why:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"Read-only agent: this command {why}. Report the change as a "
                                        "suggested fix instead of making it.",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
