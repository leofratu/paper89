# Historical paper bundle

Frozen snapshot from the initial commit `b478a47`; maintain the
[root pipeline](../docs/RESEARCH_WORKFLOW.md) for new work.

```text
Initial commit b478a47
  ├── root benchmark/          → maintained pipeline (5 model labels)
  └── paper_bundle/            → preserved snapshot (3 Gemini entries)
        ├── 13 identical files at cleanup baseline
        ├── benchmark/config.json   distinct model list and labels
        └── benchmark/analyze.py    distinct summaries and report layout
```

| Contents | Role |
| --- | --- |
| [Config](benchmark/config.json) | Gemini 2.5 Pro, Gemini 3 Pro preview, Gemini 3 Flash preview; original labels |
| [Analysis](benchmark/analyze.py) | Older report with condition/task/model breakdowns; no distance grouping |
| [Runner](benchmark/run.py) · [Tasks](benchmark/tasks/) · [Appendix](PAPER_APPENDIX.md) | Original copies, retained for reproducibility |
| [Single-file harness](bench.py) | Provider-placeholder scaffold |

No original bundle file changed between `b478a47` and cleanup baseline
`03e73e2`. Its intended release/publication status is not recorded in the
repository; this directory is treated as a historical snapshot based on that
history. It contains neither the archived runs nor package installation metadata.

**Do not synchronize or edit these copies.** Root changes need not be mirrored
here. The [integrity check](../scripts/check_artifacts.py) pins all 15 original
bundle files independently, including both differing files. See
[the workflow guide](../docs/RESEARCH_WORKFLOW.md#historical-bundle) for analysis
commands and path rules.
