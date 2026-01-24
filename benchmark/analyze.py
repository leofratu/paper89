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
    by_distance: Dict[str, List[Dict[str, Any]]] = {}
    
    for run in runs:
        by_condition.setdefault(run["condition"], []).append(run)
        by_task.setdefault(run["task_id"], []).append(run)
        by_model.setdefault(run["model"], []).append(run)
        by_model_condition.setdefault(f"{run['model']}|{run['condition']}", []).append(run)
        
        distance = run.get("metadata", {}).get("distance_bucket", "unknown")
        by_distance.setdefault(distance, []).append(run)

    summary = {
        "overall": summarize_group(runs),
        "errors_excluded": len(error_runs) if not args.include_errors else 0,
        "by_condition": {k: summarize_group(v) for k, v in by_condition.items()},
        "by_task": {k: summarize_group(v) for k, v in by_task.items()},
        "by_model": {k: summarize_group(v) for k, v in by_model.items()},
        "by_model_condition": {k: summarize_group(v) for k, v in by_model_condition.items()},
        "by_distance": {k: summarize_group(v) for k, v in by_distance.items()},
        "baseline_matched": summarize_group(by_condition.get("matched", [])),
        "baseline_mismatched": summarize_group(by_condition.get("mismatched", [])),
    }

    (root / args.output).write_text(json.dumps(summary, indent=2))

    lines = []
    lines.append("# Needle Benchmark: Empirical Results\n")
    lines.append("\n")
    lines.append("## Overall Performance (Table 3)\n")
    lines.append("\n")
    lines.append("| Model | Success (%) | Needle hit (%) | Median T_first (calls) | Median T_first (min) |\n")
    lines.append("| :--- | :---: | :---: | :---: | :---: |\n")
    
    # Force order to match paper
    paper_order = ["Gemini 3 Flash", "Gemini 3 Pro", "GLM 4.7", "Opus 4.5", "Codex 5.2 High"]
    for m in paper_order:
        if m in summary["by_model"]:
            s = summary["by_model"][m]
            lines.append(f"| {m} | {s['success_rate']*100:.1f} | {s['needle_hit_rate']*100:.1f} | {s['median_first_hit_tool_call']} | {s['median_first_hit_minutes']} |\n")

    lines.append("\n")
    lines.append("## Impact of Needle Distance (Table 4)\n")
    lines.append("\n")
    lines.append("| Distance | Success (%) | Needle hit (%) | Missed-needle failure (%) |\n")
    lines.append("| :--- | :---: | :---: | :---: |\n")
    for d in ["near", "mid", "far"]:
        if d in summary["by_distance"]:
            s = summary["by_distance"][d]
            lines.append(f"| {d.capitalize()} | {s['success_rate']*100:.0f} | {s['needle_hit_rate']*100:.0f} | {s['missed_needle_rate']*100:.0f} |\n")

    lines.append("\n")
    lines.append("## Notes\n")
    lines.append("Needle hit rate reflects whether the agent accessed the annotated spec file. Success is measured by passing the hashed test suite within 40 tool calls.\n")

    (root / args.report).write_text("".join(lines))



if __name__ == "__main__":
    main()
