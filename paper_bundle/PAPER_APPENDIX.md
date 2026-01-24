# Public Benchmark Appendix (Replica)

This appendix describes the public replication protocol for the needle
benchmark. It is designed to reproduce the qualitative findings reported in the
paper: high discovery, synthesis bottleneck, and degraded discovery under
mismatch.

## Repositories

- https://github.com/Kilo-Org/kilocode
- https://github.com/anomalyco/opencode

## Tasks

Two tasks are provided (one per repo). Each task ships:

- A hidden spec (the annotated needle) containing the true expected outputs.
- A decoy spec used only under mismatch conditions.
- A small test file that validates hashed outputs, so the expected values are not
  embedded in tests.

Needle hits are defined as access to the **real** spec file.

## Conditions

- matched: issue text explicitly references the real spec path.
- mismatched: issue text references a decoy spec path.

This setup makes discovery high under matched conditions and lower under
mismatch, while still permitting exploratory discovery.

## Budgets

- tool calls: 40
- wall clock: 20 minutes

These match the paper's budget settings.

## Tools

- search (rg), open, edit (patch), run_tests, run_all
- The runner ignores `final` responses until at least one edit is attempted and tests pass.

## Metrics

- P(H): needle hit rate
- P(S): end-to-end success
- P(S|H): conditional success after discovery
- fail-after-hit: 1 - P(S|H)
- missed-needle: 1 - P(H)

## Expected Qualitative Pattern

- High needle discovery in matched condition.
- Discovery drops under mismatch due to decoy path.
- Success remains lower than discovery (synthesis bottleneck).

## Reproducibility

- `bench.py` is a single-file harness with provider placeholders.
- `benchmark/run.py` and `benchmark/analyze.py` provide the full runnable
  pipeline with trace logging and summary metrics.
