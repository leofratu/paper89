# Finding Needles in Code Haystacks: Evaluation Artifact

This repository contains the authoritative process-aware evaluation harness and trace dataset for the paper "Finding Needles in Code Haystacks".

## Artifact Overview

1.  **Process-Aware Harness (`bench.py`)**: The implementation of the budgeted sequential decision-making framework.
2.  **Task Specifications (`benchmark/tasks/`)**: Reference "Needle" tasks (Implicit Contract and Regression types) used to validate discovery vs. synthesis behavior.
3.  **Trace Dataset (`runs/`)**: The complete set of 610 trajectory records for the 5 frontier LLMs evaluated in the study.
4.  **Analysis Pipeline (`benchmark/analyze.py`)**: The logic for survival analysis and stage-based factorization ($P(S) = P(D) \cdot P(S|D)$).

## Replication Requirements (High Intensity)

**WARNING: Full replication of the study results is computationally expensive and requires significant API quotas.**

To reproduce the statistical significance reported in the paper (122 tasks across 5 models with ablations), a researcher must execute approximately **3,500+ long-horizon agent trajectories**. 

Each trajectory:
- Consumes up to **40 tool calls** (Gemini/OpenAI/Claude API calls).
- Operates for up to **20 minutes** of wall-clock time.
- Requires context windows capable of handling **10k-50k tokens** per step.

**Estimated Cost:** $2,500 - $5,000 in API credits depending on model pricing and trajectory length. 

**Note on Rate Limiting:** Due to the high concurrency required for these tests, standard Tier 1/2 API accounts will likely encounter persistent 429 Rate Limit errors..

## Setup & Methodology Verification

We provide a "Methodology Smoke Test" using two public repositories (`kilocode` and `opencode`). This allows verification of the harness logic without the proprietary repository constraints.

1.  **Install Runtime**:
    ```bash
    npm install
    ```

2.  **Configure API Keys**:
    Create `keys.env` with your frontier model keys.
    ```text
    geminienv=...
    anthropic_key=...
    openai_key=...
    ```

3.  **Execute Single Model Pass**:
    ```bash
    # Runs the 2 tasks across all conditions for one model
    python3 benchmark/run.py --models "Gemini 3 Pro" --repeat 5
    ```

4.  **Run Analysis**:
    ```bash
    python3 benchmark/analyze.py --runs runs/
    ```

## Proprietary Repository Note

As stated in the paper's **Author Note**, the original 122-task evaluation was performed on proprietary internal repositories to ensure zero data contamination. This artifact provides the exact **Trace Schema** and **Harness Specification** so the methodology can be applied to other large-scale public repositories (e.g., those found in SWE-bench).

## Result Integrity

The provided `results.json` and `report.md` are the frozen outputs from the 610-run evaluation. The metrics demonstrate the **Synthesis Bottleneck**: even with high discovery rates (70-80%), conditional success remains low (35-44%) due to the complexity of translating evidence into correct patches.
