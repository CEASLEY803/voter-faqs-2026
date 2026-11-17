# data/

This directory holds all the data, organized by election year.

| Folder | What's in it |
| ----- | ----- |
| [`2024/`](2024/) | The baseline 2024 dataset from the AI for Society Research Group. The pipeline treats this as read-only and just uses it for comparison. |
| [`2026/`](2026/) | Everything the pipeline scraped and built for the 2026 cycle: the raw HTML pages, the JSON datasets, the quality reports, and the final analysis charts. |

If you run the pipeline for a new cycle (for example, `python code/run_pipeline.py --year 2028`), it will automatically generate a `2028/` folder and drop a README inside it for you.
