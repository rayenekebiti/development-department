#!/usr/bin/env python3
"""PostToolUse(Edit|Write|MultiEdit) hook: format the edited file with the formatter the project
already uses. Never downloads a tool and never formats a project that hasn't opted in.

- JS/TS/CSS/HTML/JSON/MD/YAML: the project's own node_modules/.bin/prettier, only if installed there.
- Python: ruff from the project's .venv or PATH, only if the project configures ruff.
- Go: gofmt. Rust: rustfmt (only inside a Cargo project).
"""
import json
import os
import shutil
import subprocess
import sys

PRETTIER_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".scss", ".html", ".json",
                 ".md", ".mdx", ".yaml", ".yml", ".vue", ".svelte"}


def find_up(start, names):
    d = start
    while True:
        for n in names:
            if os.path.exists(os.path.join(d, n)):
                return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def ruff_configured(root):
    if os.path.exists(os.path.join(root, "ruff.toml")) or os.path.exists(os.path.join(root, ".ruff.toml")):
        return True
    try:
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
            return "[tool.ruff" in f.read()
    except OSError:
        return False


def command_for(path):
    ext = os.path.splitext(path)[1].lower()
    here = os.path.dirname(path)
    if ext in PRETTIER_EXTS:
        root = find_up(here, ["node_modules"])
        if root:
            bin_ = os.path.join(root, "node_modules", ".bin", "prettier")
            if os.path.exists(bin_):
                return [bin_, "--write", "--log-level", "warn", path], root
    if ext in (".py", ".pyi"):
        root = find_up(here, ["pyproject.toml", "ruff.toml", ".ruff.toml"])
        if root and ruff_configured(root):
            venv_ruff = os.path.join(root, ".venv", "bin", "ruff")
            ruff = venv_ruff if os.path.exists(venv_ruff) else shutil.which("ruff")
            if ruff:
                return [ruff, "format", "--quiet", path], root
    if ext == ".go" and shutil.which("gofmt"):
        return ["gofmt", "-w", path], here
    if ext == ".rs" and shutil.which("rustfmt"):
        root = find_up(here, ["Cargo.toml"])
        if root:
            return ["rustfmt", "--edition", "2021", path], root
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    path = (event.get("tool_input") or {}).get("file_path")
    if not path:
        return 0
    if not os.path.isabs(path):
        path = os.path.join(event.get("cwd") or os.getcwd(), path)
    if not os.path.isfile(path):
        return 0
    found = command_for(path)
    if not found:
        return 0
    cmd, cwd = found
    try:
        subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=30)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
