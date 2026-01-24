#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any, Dict, List


def load_runs(runs_dir: Path) -> List[Dict[str, Any]]:
    runs = []
    for path in sorted(runs_dir.glob("*.json")):
        runs.append(json.loads(path.read_text()))
    return runs


def summarize_group(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(runs)
    if total == 0:
        return {
            "runs": 0,
            "success": 0,
            "needle_hit": 0,
            "success_rate": 0.0,
            "needle_hit_rate": 0.0,
            "success_given_hit": 0.0,
            "fail_after_hit_rate": 0.0,
            "missed_needle_rate": 0.0,
            "median_first_hit_tool_call": None,
            "median_first_hit_minutes": None,
            "errors": 0,
        }
    successes = [r for r in runs if r["summary"]["success"]]
    hits = [r for r in runs if r["summary"]["needle_hit"]]
    errors = [r for r in runs if r["summary"].get("error")]
    first_tool = [r["summary"]["time_to_first_needle_tool_call"] for r in hits if r["summary"]["time_to_first_needle_tool_call"]]
    first_time = [r["summary"]["time_to_first_needle_minutes"] for r in hits if r["summary"]["time_to_first_needle_minutes"]]
    success_given_hit = (len(successes) / len(hits)) if hits else 0.0
    return {
        "runs": total,
        "success": len(successes),
        "needle_hit": len(hits),
        "success_rate": round(len(successes) / total, 3),
        "needle_hit_rate": round(len(hits) / total, 3),
        "success_given_hit": round(success_given_hit, 3),
        "fail_after_hit_rate": round((1 - success_given_hit) if hits else 0.0, 3),
        "missed_needle_rate": round(1 - (len(hits) / total), 3),
        "median_first_hit_tool_call": median(first_tool) if first_tool else None,
        "median_first_hit_minutes": round(median(first_time), 3) if first_time else None,
        "errors": len(errors),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", default="runs")
    parser.add_argument("--output", default="results.json")
    parser.add_argument("--report", default="report.md")
    parser.add_argument("--include-errors", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    runs_dir = root / args.runs
    runs = load_runs(runs_dir)
    error_runs = [r for r in runs if r["summary"].get("error")]
    if not args.include_errors:
        runs = [r for r in runs if not r["summary"].get("error")]

    by_condition: Dict[str, List[Dict[str, Any]]] = {}
    by_task: Dict[str, List[Dict[str, Any]]] = {}
    by_model: Dict[str, List[Dict[str, Any]]] = {}
    by_model_condition: Dict[str, List[Dict[str, Any]]] = {}
    for run in runs:
        by_condition.setdefault(run["condition"], []).append(run)
        by_task.setdefault(run["task_id"], []).append(run)
        by_model.setdefault(run["model"], []).append(run)
        by_model_condition.setdefault(f"{run['model']}|{run['condition']}", []).append(run)

    summary = {
        "overall": summarize_group(runs),
        "errors_excluded": len(error_runs) if not args.include_errors else 0,
        "by_condition": {k: summarize_group(v) for k, v in by_condition.items()},
        "by_task": {k: summarize_group(v) for k, v in by_task.items()},
        "by_model": {k: summarize_group(v) for k, v in by_model.items()},
        "by_model_condition": {k: summarize_group(v) for k, v in by_model_condition.items()},
        "baseline_matched": summarize_group(by_condition.get("matched", [])),
        "baseline_mismatched": summarize_group(by_condition.get("mismatched", [])),
    }

    (root / args.output).write_text(json.dumps(summary, indent=2))

    lines = []
    lines.append("# Needle Benchmark (Public Replica)\n")
    lines.append("\n")
    lines.append("## Summary\n")
    lines.append("\n")
    lines.append(f"Total runs: {summary['overall']['runs']}\n")
    if summary.get("errors_excluded"):
        lines.append(f"Excluded error runs: {summary['errors_excluded']}\n")
    lines.append(
        f"Success rate: {summary['overall']['success_rate']} | Needle hit rate: {summary['overall']['needle_hit_rate']} | Success given hit: {summary['overall']['success_given_hit']} | Fail-after-hit: {summary['overall']['fail_after_hit_rate']}\n"
    )
    lines.append("\n")
    lines.append("## Baseline (Matched)\n")
    baseline = summary["baseline_matched"]
    lines.append(
        f"success_rate={baseline['success_rate']}, needle_hit_rate={baseline['needle_hit_rate']}, success_given_hit={baseline['success_given_hit']}, fail_after_hit_rate={baseline['fail_after_hit_rate']}\n"
    )
    lines.append("\n")
    lines.append("## By Condition\n")
    for condition, stats in summary["by_condition"].items():
        lines.append(
            f"- {condition}: success_rate={stats['success_rate']}, needle_hit_rate={stats['needle_hit_rate']}, missed_needle_rate={stats['missed_needle_rate']}, success_given_hit={stats['success_given_hit']}, fail_after_hit_rate={stats['fail_after_hit_rate']}"
        )
    lines.append("\n")
    lines.append("## By Model\n")
    for model, stats in summary["by_model"].items():
        lines.append(
            f"- {model}: success_rate={stats['success_rate']}, needle_hit_rate={stats['needle_hit_rate']}, success_given_hit={stats['success_given_hit']}"
        )
    lines.append("\n")
    lines.append("## By Model + Condition\n")
    for key, stats in summary["by_model_condition"].items():
        lines.append(
            f"- {key}: success_rate={stats['success_rate']}, needle_hit_rate={stats['needle_hit_rate']}, success_given_hit={stats['success_given_hit']}"
        )
    lines.append("\n")
    lines.append("## By Task\n")
    for task_id, stats in summary["by_task"].items():
        lines.append(
            f"- {task_id}: success_rate={stats['success_rate']}, needle_hit_rate={stats['needle_hit_rate']}, success_given_hit={stats['success_given_hit']}"
        )
    lines.append("\n")
    lines.append("## Notes\n")
    lines.append("Needle hit rate reflects whether the agent accessed the annotated spec file.\n")

    (root / args.report).write_text("\n".join(lines))


if __name__ == "__main__":
    main()
