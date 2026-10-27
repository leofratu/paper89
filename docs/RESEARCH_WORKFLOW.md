# Research workflow and artifact boundaries

## Canonical pipeline

Maintain `benchmark/run.py`, `benchmark/config.json`, `benchmark/tasks/`, and
`benchmark/analyze.py` at the repository root. These are the paths used by the
original README's execution commands. The root config has five model labels;
the root analyzer includes distance grouping and the paper-style tables.

| Component | Implemented behavior |
| --- | --- |
| `benchmark/run.py` | Copies a source checkout, installs the task's spec/test fixtures into that workspace, calls the Gemini REST API, logs actions and a summary |
| `benchmark/config.json` | Five labels: Gemini 3 Flash, Gemini 3 Pro, GLM 4.7, Opus 4.5, Codex 5.2 High; 40 calls, 20 minutes |
| `benchmark/tasks/` | Two public task fixtures for BigInt stringification and directory formatting, including real/decoy specs and hashed assertions |
| `benchmark/analyze.py` | Aggregates summary fields by condition, task, model, model/condition, and distance; excludes `summary.error` records by default |
| `bench.py` | Separate single-file scaffold; **all three provider clients raise `NotImplementedError`** |

The runner constructs `GeminiClient` for **every** configured model. GLM, Opus,
and Codex labels do not imply working provider integrations; the extra key
placeholders in `keys.env.example` are not consumed by this runner. Use an
explicit Gemini model selection for new public runs. Model identifiers are
historical configuration, not a claim of current API availability.

Root maintenance does not require copying edits into `paper_bundle/` or changing
the frozen results. This cleanup leaves all existing harness, analysis, config,
task, appendix, and research-data bytes unchanged.

## Offline inspection and analysis

Python 3 and its standard library suffice; no API calls, Node installation, or
external source checkouts are needed for this path. From the repository root:

```bash
python3 scripts/check_artifacts.py
mkdir -p analysis
python3 benchmark/analyze.py --runs runs --output analysis/results.json --report analysis/report.md
```

The analyzer's relative paths resolve against the directory above its
`benchmark/` directory, **not the shell's current directory**. Output parent
directories must already exist. Its defaults overwrite root `results.json` and
`report.md`; always pass separate output paths. `analysis/` is ignored for local
derived outputs. The original ignored-but-tracked `runs/`, `results.json`, and
`report.md` remain versioned.

On the cleanup baseline, the command above reproduces the frozen report exactly.
The derived JSON matches the frozen JSON except for `errors_excluded`: it is 1
rather than 0 because the later HTTP 429 trace is now present. `--include-errors`
includes that trace in all aggregates and changes the evaluated population.
These are reproduction checks of the stored summaries, not new model runs.

## New public runs

This path invokes a paid external API and executes model-provided patches and
test commands in copied workspaces. Use it as a deliberate experiment in an
appropriate isolated environment; the archived dataset needs no rerun.

Prerequisites:

- Python 3; Node.js/npm for the TypeScript fixtures; `rg` and `patch` on `PATH`.
- `npm ci` at this repository's root installs the locked `tsx`/TypeScript tools.
- Place suitable external checkouts at `repos/kilocode-src` and
  `repos/opencode-src`, corresponding to the upstream projects linked in
  [the appendix](../PAPER_APPENDIX.md). Required source files are
  `packages/agent-runtime/src/utils/safe-stringify.ts` and
  `packages/util/src/path.ts`, respectively. The artifact does not record exact
  upstream commit pins or ship these checkouts; select compatible revisions and
  record their SHAs with your own run notes. Do not substitute invented source.
- Copy `keys.env.example` to ignored `keys.env` and privately set `geminienv`, or
  create an empty `keys.env` and supply `GEMINI_API_KEY` through the environment.
  The file must exist even for the environment fallback, because `load_api_key`
  reads it first. Placeholder key values must not shadow the environment key.
- The Gemini client uses `certifi` if installed; its existing fallback disables
  TLS certificate verification. Provision `certifi` in the experiment's Python
  environment before using live credentials.

Inspect arguments without credentials or execution:

```bash
python3 benchmark/run.py --help
```

Once prerequisites are met, this bounds execution to one task/model/condition
with concurrency 1, and keeps new traces away from the archive:

```bash
python3 benchmark/run.py --models "Gemini 3 Flash" --task-ids kilocode_safe_stringify_bigint --conditions matched --repeat 1 --limit 1 --parallel 1 --output analysis/new-runs --workspaces workspaces
python3 benchmark/analyze.py --runs analysis/new-runs --output analysis/new-results.json --report analysis/new-report.md
```

Create `analysis/` first if you have not used the offline commands. Configuration
and task paths are root-relative; the key-file path is config-directory-relative.
The task test commands assume the default workspace depth, resolving root
`node_modules/` via `../../node_modules/`. Preserve that layout when changing
workspace paths. `repos/`, `workspaces/`, `keys.env`, and `node_modules/` are
ignored. The runner's default concurrency is 40; the bounded example overrides it.

## Historical bundle

`paper_bundle/` first appears in initial commit
`b478a4799dedd72a2127d612d725dcd559f8a7b9` and its 15 original files are unchanged
through baseline `03e73e24ac5b3dbbec6dda15bddd9c5d6a08ffae`. There is no separate
release manifest establishing publication intent. We therefore preserve it as a
historical snapshot, rather than infer that it is a second maintained pipeline.

At that baseline, 13 files are byte-identical to root counterparts: `bench.py`,
`PAPER_APPENDIX.md`, `benchmark/run.py`, and the ten task files. Two differ:

| File | Root | Bundle |
| --- | --- | --- |
| `benchmark/config.json` | Five model labels, title-cased; two Gemini entries plus GLM/Opus/Codex | Three Gemini entries, including `gemini-2.5-pro`, with original lowercase labels |
| `benchmark/analyze.py` | Distance grouping; fixed five-model order and paper-style tables | No distance grouping; detailed condition/task/model/model-condition report |

Keep all 15 original snapshot files verbatim, including the two distinct files.
Do not replace them with links or synchronize the matching files: their original
paths and bytes preserve the snapshot's behavior. New work belongs in root.
`paper_bundle/README.md` is a new navigation note, outside the frozen payload.

The bundle is not self-contained: it has no `runs/`, key file, source checkouts,
or npm manifest. Its scripts resolve paths against `paper_bundle/`. To compare
its original analysis against the archived root records without changing it:

```bash
mkdir -p analysis
python3 paper_bundle/benchmark/analyze.py --runs ../runs --output ../analysis/bundle-results.json --report ../analysis/bundle-report.md
```

Its JSON has no `by_distance`; its report layout is intentionally preserved.
Use explicit relative/absolute paths for any further historical experiments;
do not assume running the bundle command from root makes its defaults root-relative.

## Artifact evidence and limits

| Preserved evidence | What the repository establishes |
| --- | --- |
| 610 `runs/eval_*.json` files | Added in `15ff9cf`; 122 summary records per model, each with an empty `events` array and no `budgets` field |
| `results.json` and `report.md` | Frozen aggregate outputs committed with those 610 records in `15ff9cf` |
| `runs/kilocode_safe_stringify_bigint__Gemini_3_Flash__matched__eec82b8a.json` | Added later in `571c518`; contains tool events and ends with `success: false` and HTTP 429 in `summary.error` |
| [Original README](README.original.md) | Historical claims, original setup instructions, quota/cost estimates, and proprietary-repository explanation, retained verbatim from `03e73e2` |
| [Appendix](../PAPER_APPENDIX.md) | Public protocol and intended qualitative patterns, preserved unchanged |

The `571c518` commit message calls the live trace successful, but the record
itself reports failure. It demonstrates recorded tool activity, not a successful
completed benchmark run. There are **611 total archived JSON records**.

The original README describes a 122-task proprietary evaluation, 3,500+
trajectories with ablations, estimated cost of $2,500–$5,000, and zero data
contamination. Those statements are historical author claims, not independently
validated here. This checkout contains only two distinct task IDs across the
610 evaluation summaries. Their empty event arrays cannot independently
establish how actions were performed, verify first-hit timings, inspect patches,
or reconstruct the claimed proprietary corpus. No missing traces or repositories
have been synthesized.

The root analyzer computes aggregate counts/rates and medians from stored summary
fields; it does not implement survival analysis or significance testing. Its
`success_given_hit` is `successes / hits`, without intersecting successful runs
with hit runs, so interpreting it as conditional probability assumes every
success had a hit. Its `missed_needle_rate` is `1 - hit_rate`. The original paper
claims and table headings should be read with these implementation limits.

## Integrity and maintenance

`python3 scripts/check_artifacts.py` uses only the standard library and reads
[artifact-integrity.json](artifact-integrity.json). The manifest records SHA-256
digests from cleanup baseline `03e73e2` for all 611 archived records, the 15
original bundle files, both frozen outputs, and the preserved original README
(629 files). It fails on missing or changed payloads, extra top-level run JSON,
or additional non-cache bundle files; the bundle navigation README is excluded.
Root pipeline files can evolve independently without changing snapshot digests.

This checks byte preservation, not empirical validity or authenticity of the
original research. The manifest is not a signed provenance record. If an archive
correction is necessary, document its source and reason for review rather than
automatically regenerating hashes to make a failure pass. Keep new experiments
and derived analysis separate from the archived payload.
