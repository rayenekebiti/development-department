#!/usr/bin/env python3
"""Improve one team agent's prompt with GEPA, scored on sample tasks with known answers.

Design follows hermes-agent-self-evolution (eval set -> GEPA -> constraint gates -> human-reviewed
PR); the code is our own. Every model call goes through the `claude` CLI (your Claude Code login,
no API key). Nothing is installed: the result is a proposed agent file plus a report for review.

  .venv/bin/python improve/gepa_agent.py codebase-scout --budget 18
"""
import argparse
import datetime as dt
import difflib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gepa
from gepa.core.adapter import EvaluationBatch

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CLAUDE = ["claude", "-p", "--no-session-persistence", "--setting-sources", "project",
          "--strict-mcp-config"]
# Candidate prompts are model-written, so the agent under test gets read-only built-in tools only:
# no Bash at all (find -exec, git aliases and the like could run commands).
READ_TOOLS = ["Read", "Grep", "Glob"]


def split_agent(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        sys.exit("agent file has no frontmatter")
    return m.group(1), m.group(2)


def run_claude(args, prompt, cwd, timeout):
    try:
        r = subprocess.run(CLAUDE + args + [prompt], cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
        return r.stdout.strip() or r.stderr.strip()
    except subprocess.TimeoutExpired:
        return "(timed out)"


# ---- constraint gates (hermes style): an invalid candidate scores 0 with the reason as feedback ----
def size_limit(baseline):
    return int(max(1.5 * len(baseline), 6000))  # hermes caps skills at a fixed size; we allow 6 KB or 1.5x


def reflection_template(baseline):
    headings = ", ".join(re.findall(r"^## .+$", baseline, re.M)) or "(none)"
    return (
        "I gave an assistant these instructions (a Claude Code subagent's system prompt):\n```\n<curr_param>\n```\n\n"
        "Here are task inputs, the assistant's responses, and feedback from an automatic scorer:\n```\n<side_info>\n```\n\n"
        "Write improved instructions that fix the failures in the feedback while keeping what works. "
        "Give general guidance, not answers to these particular tasks. Hard rules, or the new "
        f"instructions are rejected: keep every one of these Markdown section headings: {headings}; stay "
        f"under {size_limit(baseline)} characters; keep every 'never' rule from the current instructions.\n\n"
        "Provide the new instructions within ``` blocks."
    )


def gate(body, baseline):
    problems = []
    if not body.strip():
        problems.append("the prompt is empty")
    limit = size_limit(baseline)
    if len(body) > limit:
        problems.append(f"the prompt is {len(body)} chars (limit {limit})")
    for heading in re.findall(r"^## .+$", baseline, re.M):
        if heading not in body:
            problems.append(f"the section heading '{heading}' was removed")
    if re.search(r"\b(Edit|Write)\b tool", body) and "never" not in body.lower():
        problems.append("the read-only rule was dropped")
    return problems


def score_output(output, expected):
    found, missed = [], []
    for options in expected:
        hit = next((o for o in options if re.search(re.escape(o.split("shop/", 1)[-1]) + r"(?!\d)", output)), None)
        (found if hit else missed).append(hit or " or ".join(options))
    return len(found) / len(expected), found, missed


class AgentAdapter:
    def __init__(self, baseline, model, repo_dir, timeout, workers):
        self.baseline, self.model, self.repo_dir = baseline, model, repo_dir
        self.timeout, self.workers = timeout, workers

    def _one(self, body, task):
        problems = gate(body, self.baseline)
        if problems:
            return "", 0.0, "Rejected by constraint gates: " + "; ".join(problems)
        out = run_claude(["--model", self.model, "--system-prompt", body,
                          "--allowedTools", *READ_TOOLS, "--disallowedTools", "Bash", "Edit", "Write",
                          "NotebookEdit", "WebFetch", "WebSearch", "--"], task["question"], self.repo_dir, self.timeout)
        s, found, missed = score_output(out, task["expected"])
        fb = f"Score {s:.2f}. Found: {', '.join(found) or 'none'}. Missed: {', '.join(missed) or 'none'}."
        return out, s, fb

    def evaluate(self, batch, candidate, capture_traces=False):
        with ThreadPoolExecutor(self.workers) as ex:
            res = list(ex.map(lambda t: self._one(candidate["body"], t), batch))
        outputs = [r[0] for r in res]
        scores = [r[1] for r in res]
        traces = [{"task": t, "output": r[0], "feedback": r[2]} for t, r in zip(batch, res)]
        return EvaluationBatch(outputs=outputs, scores=scores,
                               trajectories=traces if capture_traces else None)

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        rows = [{"Inputs": tr["task"]["question"],
                 "Generated Outputs": tr["output"][:3000],
                 "Feedback": tr["feedback"]} for tr in eval_batch.trajectories]
        return {c: rows for c in components_to_update}

    propose_new_texts = None


def make_reflection_lm(model, timeout):
    def lm(prompt):
        return run_claude(["--model", model, "--tools", "", "--"], prompt, str(HERE), timeout)
    return lm


def main():
    p = argparse.ArgumentParser()
    p.add_argument("agent")
    p.add_argument("--budget", type=int, default=18, help="max agent runs (GEPA metric calls)")
    p.add_argument("--task-model", default="haiku")
    p.add_argument("--reflection-model", default="sonnet")
    p.add_argument("--timeout", type=int, default=240)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--seed-file", help="start from this agent file instead (self-test of the optimizer)")
    a = p.parse_args()

    spec = json.loads((HERE / "tasks" / f"{a.agent}.json").read_text())
    agent_path = Path(a.seed_file) if a.seed_file else REPO / "agents" / f"{a.agent}.md"
    front, body = split_agent(agent_path.read_text())
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = HERE / "runs" / f"{a.agent}-{stamp}"
    out_dir.mkdir(parents=True)

    adapter = AgentAdapter(body, a.task_model, str(HERE / spec["repo"]), a.timeout, a.workers)
    result = gepa.optimize(
        seed_candidate={"body": body}, trainset=spec["train"], valset=spec["val"], adapter=adapter,
        reflection_lm=make_reflection_lm(a.reflection_model, a.timeout),
        max_metric_calls=a.budget, reflection_minibatch_size=len(spec["train"]),
        reflection_prompt_template=reflection_template(body),
        run_dir=str(out_dir / "gepa"), raise_on_exception=False, seed=0)

    scores = list(result.val_aggregate_scores)
    best_i = result.best_idx
    best = result.candidates[best_i]["body"]
    baseline_score, best_score = scores[0], scores[best_i]
    improved = best_i != 0 and best_score > baseline_score and not gate(best, body)

    if improved:
        (out_dir / f"{a.agent}.md").write_text(f"---\n{front}\n---\n{best}")
    diff = "".join(difflib.unified_diff(body.splitlines(True), best.splitlines(True),
                                        "current", "proposed"))
    (out_dir / "proposal.diff").write_text(diff)
    report = {
        "agent": a.agent, "budget": a.budget, "task_model": a.task_model,
        "reflection_model": a.reflection_model, "candidates": len(result.candidates),
        "val_scores": scores, "baseline_val": baseline_score, "best_val": best_score,
        "best_index": best_i, "proposal": f"{a.agent}.md" if improved else None,
        "verdict": "improved: review proposal.diff, then open a PR" if improved
                   else "no candidate beat the current prompt; nothing proposed",
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\nRun folder: {out_dir}")


if __name__ == "__main__":
    main()
