#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
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

Use relative paths from the repo root. For edits, provide a unified diff (diff --git
is optional). Do not include code fences. Example:
{"action":"edit","input":{"patch":"diff --git a/src/file.ts b/src/file.ts\n--- a/src/file.ts\n+++ b/src/file.ts\n@@\n-old\n+new\n"}}

Do not return "final" until tests pass. If tests fail, keep working.
""".strip()


@dataclass
class Budgets:
    tool_calls: int
    wall_clock_minutes: int


@dataclass
class RunnerConfig:
    search_limit: int
    open_max_lines: int
    tool_timeout_sec: int
    min_interval_sec: float


@dataclass
class GenerationConfig:
    temperature: float
    max_output_tokens: int


@dataclass
class ModelConfig:
    name: str
    label: str


@dataclass
class TaskConfig:
    id: str
    repo: str
    spec_files: List[Dict[str, str]]
    test_files: List[Dict[str, str]]
    needles: List[str]
    run_tests: str
    run_all: str
    issue_matched: str
    issue_mismatched: str
    metadata: Dict[str, Any]
    task_dir: Path


class GeminiClient:
    def __init__(self, api_key: str, generation: GenerationConfig, min_interval_sec: float):
        self.api_key = api_key
        self.generation = generation
        self._last_request_time = 0.0
        self._min_interval_sec = min_interval_sec

    def generate(self, model: str, system: str, messages: List[Dict[str, str]]) -> str:
        import ssl
        import urllib.error
        import urllib.request
        import time as time_module

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={self.api_key}"
        )
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {
                "temperature": self.generation.temperature,
                "maxOutputTokens": self.generation.max_output_tokens,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            import certifi

            context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            context = ssl._create_unverified_context()

        last_error = None
        for attempt in range(6):
            try:
                now = time_module.time()
                wait = self._min_interval_sec - (now - self._last_request_time)
                if wait > 0:
                    time_module.sleep(wait)
                self._last_request_time = time_module.time()
                with urllib.request.urlopen(req, timeout=60, context=context) as resp:
                    raw = resp.read().decode("utf-8")
                self._last_request_time = time_module.time()
                last_error = None
                break
            except urllib.error.HTTPError as exc:
                error_body = ""
                try:
                    error_body = exc.read().decode("utf-8")
                except Exception:
                    error_body = ""
                last_error = RuntimeError(f"HTTP {exc.code}: {error_body[:1000]}")
                if exc.code in (429, 500, 502, 503):
                    retry_after = exc.headers.get("Retry-After") if hasattr(exc, "headers") else None
                    if not retry_after and error_body:
                        try:
                            parsed = json.loads(error_body)
                            details = parsed.get("error", {}).get("details", [])
                            for detail in details:
                                if detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                                    retry_after = detail.get("retryDelay")
                                    break
                        except Exception:
                            retry_after = None
                    if not retry_after and error_body:
                        match = re.search(r"retry in ([0-9\\.]+)s", error_body, re.IGNORECASE)
                        if match:
                            retry_after = match.group(1)
                    if retry_after:
                        try:
                            delay = float(str(retry_after).replace("s", ""))
                            time_module.sleep(delay)
                        except ValueError:
                            time_module.sleep(2 ** attempt)
                    else:
                        time_module.sleep(2 ** attempt)
                    continue
                raise
            except urllib.error.URLError as exc:
                last_error = exc
                time_module.sleep(2 ** attempt)
                continue

        if last_error is not None:
            raise last_error
        parsed = json.loads(raw)
        candidates = parsed.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"No candidates in response: {raw[:200]}")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        return text


def load_api_key(keys_env_path: Path) -> Tuple[str, str]:
    text = keys_env_path.read_text(errors="ignore")
    match = re.search(r"geminienv=([A-Za-z0-9_\-]+)", text)
    if match:
        return match.group(1), "keys.env:geminienv"
    env_key = os.environ.get("geminienv") or os.environ.get("GEMINIENV") or os.environ.get("GEMINI_API_KEY")
    if env_key:
        return env_key, "env"
    match = re.search(r"geminiapikey=([A-Za-z0-9_\-]+)", text)
    if match:
        return match.group(1), "keys.env:geminiapikey"
    raise RuntimeError("geminienv or geminiapikey not found in keys.env or environment")


def load_config(config_path: Path) -> Tuple[List[ModelConfig], Budgets, GenerationConfig, RunnerConfig, Path]:
    config = json.loads(config_path.read_text())
    models = [ModelConfig(**m) for m in config["models"]]
    budgets = Budgets(**config["budgets"])
    generation = GenerationConfig(**config["generation"])
    runner = RunnerConfig(**config["runner"])
    keys_env_path = (config_path.parent / config["keys_env_path"]).resolve()
    return models, budgets, generation, runner, keys_env_path


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
                spec_files=data.get("spec_files", []),
                test_files=data.get("test_files", []),
                needles=data.get("needles", []),
                run_tests=data["run_tests"],
                run_all=data["run_all"],
                issue_matched=data["issue"]["matched"],
                issue_mismatched=data["issue"]["mismatched"],
                metadata=data.get("metadata", {}),
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
        try:
            proc = subprocess.run(
                ["patch", f"-p{strip_level}", "-i", str(patch_file)],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as exc:
            return False, f"patch error: {exc}"
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


def parse_action(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def run_task(
    task: TaskConfig,
    model: ModelConfig,
    condition: str,
    api_key: str,
    api_key_source: str,
    budgets: Budgets,
    generation: GenerationConfig,
    runner: RunnerConfig,
    root: Path,
    output_dir: Path,
    workspaces_dir: Path,
) -> Path:
    run_id = f"{task.id}__{model.label.replace(' ', '_')}__{condition}__{uuid.uuid4().hex[:8]}"
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    workspace = workspaces_dir / run_id

    repo_src = root / task.repo
    copy_repo(repo_src, workspace)

    for spec in task.spec_files:
        src = task.task_dir / spec["source"]
        dest = workspace / spec["dest"]
        ensure_parent(dest)
        shutil.copyfile(src, dest)

    for test in task.test_files:
        src = task.task_dir / test["source"]
        dest = workspace / test["dest"]
        ensure_parent(dest)
        shutil.copyfile(src, dest)

    issue_text = task.issue_matched if condition != "mismatched" else task.issue_mismatched

    client = GeminiClient(api_key, generation, runner.min_interval_sec)
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
    edits_made = False
    tests_passed = False

    error_message = None
    while tool_calls < budgets.tool_calls:
        elapsed_minutes = (time.time() - start_time) / 60.0
        if elapsed_minutes > budgets.wall_clock_minutes:
            break

        try:
            response = client.generate(model.name, SYSTEM_PROMPT, messages)
        except Exception as exc:
            error_message = str(exc)
            events.append(
                {
                    "t": round((time.time() - start_time) / 60.0, 4),
                    "tool": "model_error",
                    "input": {},
                    "output": {"text": error_message},
                    "needle_hit": False,
                    "files_accessed": [],
                    "tests": None,
                }
            )
            break
        try:
            action = parse_action(response)
        except Exception:
            messages.append(
                {
                    "role": "user",
                    "content": "Your response was not valid JSON. Reply with ONLY a JSON object.",
                }
            )
            continue

        act = action.get("action")
        payload = action.get("input", {})
        if act == "final":
            if not edits_made:
                messages.append(
                    {
                        "role": "user",
                        "content": "You must attempt at least one edit before finishing. Use the edit tool.",
                    }
                )
                tool_calls += 1
                continue
            if not tests_passed:
                messages.append(
                    {
                        "role": "user",
                        "content": "Tests are still failing. Continue working and re-run tests.",
                    }
                )
                tool_calls += 1
                continue
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
                query = payload.get("q", "")
                output_text, files_accessed = rg_search(workspace, query, runner.search_limit)
        elif act == "open":
            if condition == "restricted_files" and files_opened_count >= 8:
                output_text = "Error: maximum file access limit (8) reached."
            else:
                output_text, files_accessed = open_file(
                    workspace,
                    payload.get("path", ""),
                    payload.get("start_line"),
                    payload.get("end_line"),
                    runner.open_max_lines,
                )
                if files_accessed:
                    files_opened_count += 1
        elif act == "edit":
            patch_text = payload.get("patch", "")
            ok, output_text = apply_patch(workspace, patch_text)
            files_accessed = extract_files_from_patch(patch_text)
            output_text = ("applied" if ok else "failed") + "\n" + output_text
            if ok:
                edits_made = True
        elif act == "run_tests" or act == "run_all":
            if condition == "no_tests_until_end" and tool_calls < budgets.tool_calls - 1:
                output_text = "Error: test execution is only permitted at the end of the session."
            else:
                cmd = task.run_tests if act == "run_tests" else task.run_all
                code, output_text = run_command(workspace, cmd, runner.tool_timeout_sec)
                tests_info = {"exit_code": code}
                if code == 0:
                    tests_passed = True
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

        tool_result = (
            f"TOOL RESULT ({act}):\n" + output_text[:4000] + ("\n[truncated]" if len(output_text) > 4000 else "")
        )
        messages.append({"role": "model", "content": response})
        messages.append({"role": "user", "content": tool_result})

    success = False
    for event in events[::-1]:
        if event["tool"] == "run_all":
            success = event.get("tests", {}).get("exit_code") == 0
            break

    trace = {
        "run_id": run_id,
        "task_id": task.id,
        "model": model.label,
        "condition": condition,
        "metadata": task.metadata,
        "api_key_source": api_key_source,
        "budgets": {"tool_calls": budgets.tool_calls, "wall_clock_minutes": budgets.wall_clock_minutes},
        "events": events,
        "summary": {
            "success": success,
            "needle_hit": discovered,
            "time_to_first_needle_tool_call": first_hit_call,
            "time_to_first_needle_minutes": first_hit_time,
            "tool_calls_used": tool_calls,
            "error": error_message,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{run_id}.json"
    out_path.write_text(json.dumps(trace, indent=2))
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="benchmark/config.json")
    parser.add_argument("--tasks", default="benchmark/tasks")
    parser.add_argument("--output", default="runs")
    parser.add_argument("--workspaces", default="workspaces")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--models", default=None, help="comma-separated model labels to run")
    parser.add_argument("--conditions", default="matched,mismatched")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--task-ids", default=None, help="comma-separated task ids to run")
    parser.add_argument("--parallel", type=int, default=40, help="max concurrent runs")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    config_path = root / args.config
    tasks_dir = root / args.tasks
    output_dir = root / args.output
    workspaces_dir = root / args.workspaces

    models, budgets, generation, runner, keys_env_path = load_config(config_path)
    api_key, api_key_source = load_api_key(keys_env_path)
    tasks = load_tasks(tasks_dir)
    if args.task_ids:
        allowed_tasks = {t.strip() for t in args.task_ids.split(",") if t.strip()}
        tasks = [t for t in tasks if t.id in allowed_tasks]

    if args.models:
        allowed = {m.strip() for m in args.models.split(",")}
        models = [m for m in models if m.label in allowed or m.name in allowed]

    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]

    runs = []
    for task in tasks:
        for model in models:
            for condition in conditions:
                for _ in range(args.repeat):
                    runs.append((task, model, condition))

    if args.limit:
        runs = runs[: args.limit]

    def submit_run(task: TaskConfig, model: ModelConfig, condition: str) -> Path:
        return run_task(
            task,
            model,
            condition,
            api_key,
            api_key_source,
            budgets,
            generation,
            runner,
            root,
            output_dir,
            workspaces_dir,
        )

    if args.parallel <= 1:
        for task, model, condition in runs:
            submit_run(task, model, condition)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(submit_run, task, model, condition): (task, model, condition)
                for task, model, condition in runs
            }
            for future in concurrent.futures.as_completed(futures):
                task, model, condition = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    print(
                        f"run failed: {task.id} {model.label} {condition}: {exc}",
                        file=sys.stderr,
                    )


if __name__ == "__main__":
    main()
