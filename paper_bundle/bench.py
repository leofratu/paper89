#!/usr/bin/env python3
"""
Public replication harness (single-file) for process-aware needle benchmarks.

Trace schema (simplified):
{
  "run_id": "string",
  "task_id": "string",
  "model": "string",
  "condition": "matched|mismatched",
  "budgets": {"tool_calls": 40, "wall_clock_minutes": 20},
  "events": [
    {
      "t": 12.34,
      "tool": "search|open|edit|run_tests|run_all",
      "input": {"q": "...", "path": "..."},
      "output": {"text": "..."},
      "needle_hit": true,
      "files_accessed": ["..."],
      "tests": {"exit_code": 0}
    }
  ],
  "summary": {
    "success": false,
    "needle_hit": true,
    "time_to_first_needle_tool_call": 5,
    "time_to_first_needle_minutes": 1.2,
    "tool_calls_used": 18
  }
}

Provider placeholders:
- Codex: CODEX_API_KEY
- Opus: OPUS_API_KEY
- Gemini: GEMINI_API_KEY
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SYSTEM_PROMPT = """
You are a software engineering agent. You must use the provided tools to search,
open files, edit code, and run tests. Respond ONLY with a single JSON object.

Actions:
- search: {"action":"search","input":{"q":"..."}}
- open: {"action":"open","input":{"path":"...","start_line":1,"end_line":200}}
- edit: {"action":"edit","input":{"patch":"<unified diff>"}}
- run_tests: {"action":"run_tests","input":{}}
- run_all: {"action":"run_all","input":{}}
- final: {"action":"final","input":{"summary":"..."}}
""".strip()


@dataclass
class Budgets:
    tool_calls: int
    wall_clock_minutes: int


@dataclass
class TaskConfig:
    id: str
    repo: str
    needles: List[str]
    run_tests: str
    run_all: str
    issue_matched: str
    issue_mismatched: str
    task_dir: Path


class BaseClient:
    def generate(self, model: str, system: str, messages: List[Dict[str, str]]) -> str:
        raise NotImplementedError


class CodexClient(BaseClient):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def generate(self, model: str, system: str, messages: List[Dict[str, str]]) -> str:
        raise NotImplementedError("Insert Codex API call here (provider/model-specific).")


class OpusClient(BaseClient):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def generate(self, model: str, system: str, messages: List[Dict[str, str]]) -> str:
        raise NotImplementedError("Insert Opus API call here (provider/model-specific).")


class GeminiClient(BaseClient):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def generate(self, model: str, system: str, messages: List[Dict[str, str]]) -> str:
        raise NotImplementedError("Insert Gemini API call here (provider/model-specific).")


CLIENTS = {
    "codex": CodexClient,
    "opus": OpusClient,
    "gemini": GeminiClient,
}


def load_tasks(tasks_dir: Path) -> List[TaskConfig]:
    tasks = []
    for task_dir in sorted(tasks_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        task_file = task_dir / "task.json"
        if not task_file.exists():
            continue
        data = json.loads(task_file.read_text())
        tasks.append(
            TaskConfig(
                id=data["id"],
                repo=data["repo"],
                needles=data.get("needles", []),
                run_tests=data["run_tests"],
                run_all=data["run_all"],
                issue_matched=data["issue"]["matched"],
                issue_mismatched=data["issue"]["mismatched"],
                task_dir=task_dir,
            )
        )
    return tasks


def copy_repo(repo_src: Path, workspace: Path) -> None:
    def ignore(path: str, names: List[str]) -> List[str]:
        ignored = []
        if ".git" in names:
            ignored.append(".git")
        if "node_modules" in names:
            ignored.append("node_modules")
        return ignored

    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(repo_src, workspace, ignore=ignore)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def apply_patch(workspace: Path, patch_text: str) -> Tuple[bool, str]:
    patch_file = workspace / "__bench_patch.diff"
    patch_file.write_text(patch_text)
    for strip_level in (0, 1):
        proc = subprocess.run(
            ["patch", f"-p{strip_level}", "-i", str(patch_file)],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return True, proc.stdout + proc.stderr
    return False, proc.stdout + proc.stderr


def rg_search(workspace: Path, query: str, limit: int) -> Tuple[str, List[str]]:
    cmd = [
        "rg",
        "-n",
        "--max-count",
        str(limit),
        "--glob",
        "!**/.git/**",
        "--glob",
        "!**/node_modules/**",
        query,
        ".",
    ]
    proc = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True)
    output = proc.stdout + proc.stderr
    files = []
    for line in output.splitlines():
        parts = line.split(":", 2)
        if len(parts) >= 2:
            files.append(parts[0])
    return output.strip(), list(sorted(set(files)))


def open_file(workspace: Path, path: str, start_line: Optional[int], end_line: Optional[int], max_lines: int) -> Tuple[str, List[str]]:
    target = workspace / path
    if not target.exists() or not target.is_file():
        return f"file not found: {path}", []
    lines = target.read_text(errors="ignore").splitlines()
    total = len(lines)
    start = max(1, start_line or 1)
    if start > total:
        return f"{path} ({start}-{start} of {total})", [path]
    end = end_line or min(total, start + max_lines - 1)
    end = min(end, start + max_lines - 1, total)
    snippet = []
    for idx in range(start - 1, end):
        snippet.append(f"{idx + 1}: {lines[idx]}")
    header = f"{path} ({start}-{end} of {total})"
    return header + "\n" + "\n".join(snippet), [path]


def run_command(workspace: Path, command: str, timeout: int) -> Tuple[int, str]:
    proc = subprocess.run(command, cwd=workspace, shell=True, capture_output=True, text=True, timeout=timeout)
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode, output


def parse_action(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def needle_hit(files_accessed: List[str], needle_paths: List[str]) -> bool:
    needle_set = [normalize_path(p) for p in needle_paths]
    for f in files_accessed:
        f_norm = normalize_path(f)
        for needle in needle_set:
            if f_norm.endswith(needle):
                return True
    return False


def extract_files_from_patch(patch_text: str) -> List[str]:
    files = []
    for line in patch_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            files.append(path)
        elif line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                path = parts[3]
                if path.startswith("b/"):
                    path = path[2:]
                files.append(path)
    return list(sorted(set(files)))


def run_task(
    task: TaskConfig,
    client: BaseClient,
    model: str,
    condition: str, # matched, mismatched, no_search, restricted_files, no_tests_until_end
    budgets: Budgets,
    search_limit: int,
    open_max_lines: int,
    tool_timeout_sec: int,
    root: Path,
    output_dir: Path,
    workspaces_dir: Path,
) -> Path:
    run_id = f"{task.id}__{model.replace(' ', '_')}__{condition}__{uuid.uuid4().hex[:8]}"
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    workspace = workspaces_dir / run_id

    repo_src = root / task.repo
    copy_repo(repo_src, workspace)

    issue_text = task.issue_matched if condition != "mismatched" else task.issue_mismatched
    # Paper uses high noise for "noisy descriptions" but we'll stick to mismatched issue
    
    messages: List[Dict[str, str]] = [
        {
            "role": "user",
            "content": (
                f"Task: Fix the failing tests with a minimal patch. Avoid overfitting.\n"
                f"Budgets: max {budgets.tool_calls} tool calls, max {budgets.wall_clock_minutes} minutes wall-clock.\n"
                f"Issue: {issue_text}\n"
                f"Failing test: run the provided test command.\n"
            ),
        }
    ]

    events = []
    start_time = time.time()
    tool_calls = 0
    discovered = False
    first_hit_call = None
    first_hit_time = None
    files_opened_count = 0

    while tool_calls < budgets.tool_calls:
        elapsed_minutes = (time.time() - start_time) / 60.0
        if elapsed_minutes > budgets.wall_clock_minutes:
            break

        response = client.generate(model, SYSTEM_PROMPT, messages)
        action = parse_action(response)
        act = action.get("action")
        payload = action.get("input", {})
        if act == "final":
            break

        tool_calls += 1
        event_time = (time.time() - start_time) / 60.0
        files_accessed: List[str] = []
        output_text = ""
        tests_info = None

        if act == "search":
            if condition == "no_search":
                output_text = "Error: search tool is disabled in this environment."
            else:
                output_text, files_accessed = rg_search(workspace, payload.get("q", ""), search_limit)
        elif act == "open":
            if condition == "restricted_files" and files_opened_count >= 8:
                output_text = "Error: maximum file access limit (8) reached."
            else:
                output_text, files_accessed = open_file(
                    workspace,
                    payload.get("path", ""),
                    payload.get("start_line"),
                    payload.get("end_line"),
                    open_max_lines,
                )
                if files_accessed:
                    files_opened_count += 1
        elif act == "edit":
            ok, output_text = apply_patch(workspace, payload.get("patch", ""))
            files_accessed = extract_files_from_patch(payload.get("patch", ""))
            output_text = ("applied" if ok else "failed") + "\n" + output_text
        elif act == "run_tests" or act == "run_all":
            if condition == "no_tests_until_end" and tool_calls < budgets.tool_calls - 1:
                output_text = "Error: test execution is only permitted at the end of the session."
            else:
                cmd = task.run_tests if act == "run_tests" else task.run_all
                code, output_text = run_command(workspace, cmd, tool_timeout_sec)
                tests_info = {"exit_code": code}
        else:
            output_text = f"unknown action: {act}"

        hit = needle_hit(files_accessed, task.needles)
        if hit and not discovered:
            discovered = True
            first_hit_call = tool_calls
            first_hit_time = event_time

        events.append(
            {
                "t": round(event_time, 4),
                "tool": act,
                "input": payload,
                "output": {"text": output_text[:4000]},
                "needle_hit": hit,
                "files_accessed": files_accessed,
                "tests": tests_info,
            }
        )

        messages.append({"role": "model", "content": response})
        messages.append({"role": "user", "content": f"TOOL RESULT ({act}):\n{output_text[:4000]}"})

    success = False
    for event in events[::-1]:
        if event["tool"] == "run_all":
            success = event.get("tests", {}).get("exit_code") == 0
            break

    trace = {
        "run_id": run_id,
        "task_id": task.id,
        "model": model,
        "condition": condition,
        "budgets": {"tool_calls": budgets.tool_calls, "wall_clock_minutes": budgets.wall_clock_minutes},
        "events": events,
        "summary": {
            "success": success,
            "needle_hit": discovered,
            "time_to_first_needle_tool_call": first_hit_call,
            "time_to_first_needle_minutes": first_hit_time,
            "tool_calls_used": tool_calls,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{run_id}.json"
    out_path.write_text(json.dumps(trace, indent=2))
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, choices=sorted(CLIENTS.keys()))
    parser.add_argument("--model", required=True)
    parser.add_argument("--conditions", default="matched,mismatched")
    parser.add_argument("--tasks", default="benchmark/tasks")
    parser.add_argument("--output", default="runs")
    parser.add_argument("--workspaces", default="workspaces")
    parser.add_argument("--tool-calls", type=int, default=40)
    parser.add_argument("--wall-clock-minutes", type=int, default=20)
    parser.add_argument("--search-limit", type=int, default=200)
    parser.add_argument("--open-max-lines", type=int, default=200)
    parser.add_argument("--tool-timeout-sec", type=int, default=60)
    args = parser.parse_args()

    if args.provider == "codex":
        api_key = os.environ.get("CODEX_API_KEY")
        env_name = "CODEX_API_KEY"
    elif args.provider == "opus":
        api_key = os.environ.get("OPUS_API_KEY")
        env_name = "OPUS_API_KEY"
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        env_name = "GEMINI_API_KEY"
    if not api_key:
        raise SystemExit(f"Missing API key env var: {env_name}.")
    client = CLIENTS[args.provider](api_key)

    root = Path(__file__).resolve().parent
    tasks_dir = root / args.tasks
    output_dir = root / args.output
    workspaces_dir = root / args.workspaces
    tasks = load_tasks(tasks_dir)

    budgets = Budgets(tool_calls=args.tool_calls, wall_clock_minutes=args.wall_clock_minutes)
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]

    for task in tasks:
        for condition in conditions:
            run_task(
                task,
                client,
                args.model,
                condition,
                budgets,
                args.search_limit,
                args.open_max_lines,
                args.tool_timeout_sec,
                root,
                output_dir,
                workspaces_dir,
            )


if __name__ == "__main__":
    main()
