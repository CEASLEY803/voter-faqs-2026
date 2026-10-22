# U.S. Voter FAQs: 2024 and 2026

This project collects voter FAQ information available on source websites in 2026 and stores it separately so it can be compared with the existing 2024 dataset from the AI for Society Research Group.

The sources are each state's official election website and [Vote411](https://www.vote411.org/). The goal is to compare the information between 2024 and 2026, both within each state and across states.

The agreed cutoff for FAQs is October 10, 2026. Each record also includes the actual date and time its source page was downloaded.

## Prior work (2024)

The 2024 dataset comes from the AI for Society Research Group's [election-dataset-us repository](https://github.com/ai4society/election-dataset-us/). This project uses that data for comparison and keeps the 2026 collection in separate files.

The original project also has a research paper, [Do Voters Get the Information They Want? Understanding Authentic Voter FAQs in the US and How to Improve for Informed Electoral Participation](https://arxiv.org/abs/2412.15273). The authors provide their preferred paper citation in the original repository's [Citation section](https://github.com/ai4society/election-dataset-us/#citation).

The exact repository version used for the 2024 data is recorded in `reference/baseline_provenance.json`.

## Supporting information

Some pages have a clear Q&A structure. Others contain useful information under headings that are not phrased as questions. This information is saved separately from the FAQ records.

A state can have zero extracted FAQs but still have supporting information. An empty FAQ file does not mean the source page was empty.

Each FAQ record has these fields:

| Field | Meaning |
|---|---|
| `q` | Published question |
| `a` | Published answer |
| `s` | Source URL |
| `t` | When the source page was downloaded |

Supporting records use `topic`, `kind`, and `content`, with the same source and time fields as the FAQ records. The `kind` field distinguishes a topic introduction from a section without recognized questions.

## File structure

| File or folder | Content |
|---|---|
| `data/2024/` | The original data used for comparison. These files are kept unchanged. |
| `data/2026/runs/` | Individual collection runs, kept so outputs can be compared after changes to the code. |
| `data/2026/batches/` | Vote411 collection runs for selected states or all 50 states. Earlier batches are kept to track changes to the extraction. |
| `reference/` | Selected files from the original repository and a record of the baseline version used. |
| `collect_sc.py` | The South Carolina collector and shared collection functions used by the Vote411 tools. |
| `collect_vote411.py` | The Vote411 collector for selected states or all 50 states. |
| `validate_vote411_batch.py` | Checks saved Vote411 results against their saved source pages. |
| `restore_baseline.py` | Recovers the original data from the recorded repository version. |
| `requirements.txt` | Python libraries needed to run the tools. |
| `AI_USAGE.md` | The record of coding prompts and model information used for transparency. |

## Setup

Install Python, open PowerShell, and go to the project folder. These commands use Windows paths.

Create a Python environment for the project:

```powershell
python -m venv .venv
```

Install the libraries needed to run the tools:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The 2024 files are already included. If they need to be recovered, run:

```powershell
.\.venv\Scripts\python.exe restore_baseline.py
```

The recovery script will not overwrite an existing baseline file if its contents differ from the original.

## Run the collectors

To collect South Carolina from both SC Votes and Vote411:

```powershell
.\.venv\Scripts\python.exe collect_sc.py
```

To collect Vote411 for selected states, supply their lowercase state codes:

```powershell
.\.venv\Scripts\python.exe collect_vote411.py ga oh
```

Full URL names such as `south-carolina` also work.

To collect Vote411 for all 50 states:

```powershell
.\.venv\Scripts\python.exe collect_vote411.py --all
```

The program saves questions, supporting information, source pages, and collection details in a new folder for each run. The Vote411 collector also records each state's success or failure in `batch_manifest.json`. If a state fails, it records the error and continues. Failed states can be retried by supplying their codes in a new run.

## Reuse saved pages

When the code changes, it can be run on saved pages instead of downloading them again. This lets the outputs be compared using the same source material.

For a saved South Carolina run:

```powershell
.\.venv\Scripts\python.exe collect_sc.py --from-run "PATH_TO_SAVED_RUN"
```

Replace `PATH_TO_SAVED_RUN` with the saved run's folder under `data/2026/runs/`.

For a saved Vote411 batch:

```powershell
.\.venv\Scripts\python.exe collect_vote411.py --all --from-batch "PATH_TO_BATCH_FOLDER"
```

Replace `PATH_TO_BATCH_FOLDER` with the saved batch's folder under `data/2026/batches/`.

The new output goes into a separate folder. The source pages and original download times are kept unchanged.

## Check a Vote411 batch

```powershell
.\.venv\Scripts\python.exe validate_vote411_batch.py "PATH_TO_BATCH_FOLDER"
```

Use the batch folder you want to check. The results are saved in that folder as `validation_report.json`.

The checks cover required fields, record counts, source URLs, download times, and whether the saved source files have changed. They also compare the counts of words and punctuation in the extracted content with the source sections to help find lost or repeated text.

## Limits and review

Passing the automated checks does not prove that every question and answer was recorded properly. JSON outputs should still be compared with the source page.

Possible issues include lost paragraph breaks, broken characters, incomplete answers, and incorrect question and answer pairings.

The Vote411 extractor recognizes certain question headings and bold question labels. Questions written in another format may remain within another answer or supporting section instead of becoming separate FAQ records. During manual review, two question-like subheadings were kept with their existing answers because they explained something within those answers.

The saved pages show what was downloaded at the recorded time. Websites can change afterward. A download time does not show when the text was first published. For pages downloaded after the agreed October 10 cutoff, the timestamp alone does not establish what was on the page by that cutoff.

## License and credit

New code and documentation in this project use the MIT license in `LICENSE`, copyright 2026 Cole Easley.

Material included from the original 2024 project keeps its MIT license and copyright notice in `reference/LICENSE`, copyright 2024 AI for Society Research Group.

Keep the copyright notices when sharing the code or original dataset. Text and pages collected from other websites may have their own rules for reuse. This project's MIT license does not change those rules.
