# Needle Benchmark: Empirical Results

## Overall Performance (Table 3)

| Model | Success (%) | Needle hit (%) | Median T_first (calls) | Median T_first (min) |
| :--- | :---: | :---: | :---: | :---: |
| Gemini 3 Flash | 25.4 | 73.0 | 11.5 | 6.2 |
| Gemini 3 Pro | 31.1 | 77.0 | 12.0 | 9.5 |
| GLM 4.7 | 31.1 | 73.8 | 11.8 | 8.8 |
| Opus 4.5 | 34.4 | 83.6 | 9.6 | 10.4 |
| Codex 5.2 High | 35.2 | 80.3 | 8.3 | 18.5 |

## Impact of Needle Distance (Table 4)

| Distance | Success (%) | Needle hit (%) | Missed-needle failure (%) |
| :--- | :---: | :---: | :---: |
| Near | 32 | 78 | 22 |
| Mid | 31 | 77 | 23 |
| Far | 31 | 78 | 22 |

## Notes
Needle hit rate reflects whether the agent accessed the annotated spec file. Success is measured by passing the hashed test suite within 40 tool calls.
