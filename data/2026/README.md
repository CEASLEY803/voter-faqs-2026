# 2026 voter FAQ data

This folder holds the voter FAQ data collected for the 2026 election cycle, for 50 states. It was compared with the 2024 data in `data/2024/`.

| Source | Records |
| --- | --- |
| State election sites | 2,028 |
| Vote411 | 2,360 |
| Both | 4,388 |

| Folder or file | What it holds |
| --- | --- |
| `state_sites/` | State election site pages exactly as they were saved. One folder per collection batch, with a subfolder per state and a `batch_manifest.json` that says where each page came from and when. |
| `batches/` | Vote411 pages exactly as they were saved, and the records taken from them. One folder per collection batch, with a subfolder per state. |
| `runs/` | Runs of the South Carolina collector `code/collect_sc.py`, each with the pages it saved and the records taken from them. |
| `dataset/` | The 2026 dataset: one file per state (`<state>_qa.json`) with its questions and answers from both sources, plus `manifest.json` and the build's reports. |
| `quality/` | The data quality report: possible problems in the dataset, as `quality_report.csv` and `quality_summary.md`. |
| `review.csv` | One row per state. A person marks a state approved or rejected here after checking its data. |
| `analysis/` | The comparison with 2024 for every state: change rates in `per_state.csv`, the charts, every compared question in `comparison/pairs.csv`, and the cross-check in `check/`. |

How the data is collected, built, checked and compared is described in [docs/TechnicalDescription.md](../../docs/TechnicalDescription.md).

This file is written by `code/run_pipeline.py` at the end of each run.
