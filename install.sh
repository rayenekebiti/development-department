#!/usr/bin/env bash
# Installs the development-department agent team for Claude Code, at user scope (~/.claude).
#
#   ./install.sh               agents + hooks + settings + plugins
#   ./install.sh --no-plugins  agents + hooks + settings only
#
# Safe to re-run. Anything it replaces is backed up to ~/.claude/backups/development-department-<time>/.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$CLAUDE_DIR/backups/development-department-$STAMP"
WITH_PLUGINS=1

for arg in "$@"; do
  case "$arg" in
    --no-plugins) WITH_PLUGINS=0 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

command -v python3 >/dev/null || { echo "python3 is required (the hooks are Python 3, stdlib only)." >&2; exit 1; }
if [ "$WITH_PLUGINS" = 1 ] && ! command -v claude >/dev/null; then
  echo "The claude CLI is not on PATH. Install Claude Code, or re-run with --no-plugins." >&2
  exit 1
fi

backup() { # backup <file>: copy an existing file into the backup folder, keeping its path
  [ -e "$1" ] || return 0
  mkdir -p "$BACKUP/$(dirname "${1#"$CLAUDE_DIR"/}")"
  cp -p "$1" "$BACKUP/${1#"$CLAUDE_DIR"/}"
}

install_file() { # install_file <src> <dest>
  if [ -e "$2" ] && ! cmp -s "$1" "$2"; then backup "$2"; fi
  mkdir -p "$(dirname "$2")"
  cp "$1" "$2"
}

echo "1/5 Agents -> $CLAUDE_DIR/agents/"
for f in "$HERE"/agents/*.md; do install_file "$f" "$CLAUDE_DIR/agents/$(basename "$f")"; done

echo "2/5 Hooks -> $CLAUDE_DIR/hooks/team/"
for f in "$HERE"/hooks/*.py; do install_file "$f" "$CLAUDE_DIR/hooks/team/$(basename "$f")"; done
chmod +x "$CLAUDE_DIR"/hooks/team/*.py

echo "3/5 Hook entries -> $CLAUDE_DIR/settings.json"
backup "$CLAUDE_DIR/settings.json"
python3 -I - "$HERE/settings/settings-snippet.json" "$CLAUDE_DIR/settings.json" <<'PY'
import json, os, re, sys
snippet_path, settings_path = sys.argv[1], sys.argv[2]
with open(snippet_path) as f:
    snippet = json.load(f)["hooks"]
settings = {}
if os.path.exists(settings_path):
    with open(settings_path) as f:
        settings = json.load(f)

def key(cmd):  # "team_loop.py stop" -> same entry whatever the install path
    m = re.search(r"/\.claude/hooks/team/(\S+\.py)\"?(.*)", cmd)
    return (m.group(1), m.group(2).strip()) if m else (cmd, "")

hooks = settings.setdefault("hooks", {})
added = 0
for event, groups in snippet.items():
    existing = {key(h.get("command", "")) for g in hooks.get(event, []) for h in g.get("hooks", [])}
    for group in groups:
        if all(key(h["command"]) in existing for h in group["hooks"]):
            continue
        hooks.setdefault(event, []).append(group)
        added += 1
os.makedirs(os.path.dirname(settings_path), exist_ok=True)
with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print(f"    added {added} hook group(s); existing ones left as they were")
PY

echo "4/5 Ponytail off by default (feature-builder still preloads it)"
python3 -I - "$HOME/.config/ponytail/config.json" <<'PY'
import json, os, sys
path = sys.argv[1]
cfg = {}
if os.path.exists(path):
    with open(path) as f:
        cfg = json.load(f)
if cfg.get("defaultMode") != "off":
    cfg["defaultMode"] = "off"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
PY
CG="$(command -v codegraph || true)"
[ -z "$CG" ] && [ -x "$HOME/.local/bin/codegraph" ] && CG="$HOME/.local/bin/codegraph"
if [ -n "$CG" ]; then
  if DO_NOT_TRACK=1 "$CG" telemetry off >/dev/null 2>&1; then echo "    CodeGraph telemetry: off"; fi
fi

if [ "$WITH_PLUGINS" = 0 ]; then
  echo "5/5 Plugins skipped (--no-plugins). See README.md for the list."
else
  echo "5/5 Plugin marketplaces and plugins"
  for m in anthropics/claude-plugins-official trailofbits/skills DietrichGebert/ponytail karanb192/claude-code-hooks; do
    claude plugin marketplace add "$m" >/dev/null 2>&1 || true   # already added is fine
  done
  PLUGINS=(
    superpowers@claude-plugins-official
    frontend-design@claude-plugins-official
    playwright@claude-plugins-official
    context7@claude-plugins-official
    pr-review-toolkit@claude-plugins-official
    stripe@claude-plugins-official
    claude-security@claude-plugins-official
    security-guidance@claude-plugins-official
    static-analysis@trailofbits
    audit-context-building@trailofbits
    differential-review@trailofbits
    insecure-defaults@trailofbits
    supply-chain-risk-auditor@trailofbits
    variant-analysis@trailofbits
    property-based-testing@trailofbits
    ponytail@ponytail
    guard-pack@claude-code-hooks
    protect-tests@claude-code-hooks
  )
  failed=()
  for p in "${PLUGINS[@]}"; do
    if claude plugin install "$p" >/dev/null 2>&1; then echo "    ok  $p"; else echo "    !!  $p"; failed+=("$p"); fi
  done

  # webapp-testing skill (frontend-ux, test-writer) from anthropics/skills.
  if [ ! -d "$CLAUDE_DIR/skills/webapp-testing" ] && command -v git >/dev/null; then
    tmp="$(mktemp -d)"
    if git clone --quiet --depth 1 https://github.com/anthropics/skills.git "$tmp/skills" 2>/dev/null \
       && [ -d "$tmp/skills/skills/webapp-testing" ]; then
      mkdir -p "$CLAUDE_DIR/skills"
      cp -r "$tmp/skills/skills/webapp-testing" "$CLAUDE_DIR/skills/"
      echo "    ok  webapp-testing skill"
    else
      echo "    !!  webapp-testing skill (copy skills/webapp-testing from github.com/anthropics/skills by hand)"
    fi
    rm -rf "$tmp"
  fi
  if [ "${#failed[@]}" -gt 0 ]; then
    echo "Some plugins did not install. Retry each with: claude plugin install <name@marketplace>"
  fi
fi

echo
[ -d "$BACKUP" ] && echo "Backups of replaced files: $BACKUP"
echo "Done. Restart Claude Code, then run:  claude --agent team-lead"
echo "Sign in to the Context7 and Stripe MCP servers with /mcp (Stripe: a test-mode account)."
