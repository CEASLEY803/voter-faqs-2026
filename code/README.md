# code/

This folder contains all the Python scripts that make the project run. You should run them from the root of the repository, not from inside this directory. For example:

```
python code/run_pipeline.py --year 2026
```

`run_pipeline.py` acts as the master switch that runs everything in order. But since every step is its own script, you can easily rerun individual pieces if you're debugging.

| Script | What it does |
| ----- | ----- |
| `run_pipeline.py` | Runs the entire pipeline for a given year. |
| `collect_vote411.py` | Scrapes the Vote411 pages. |
| `snapshot_state_sites.py` | Downloads the state election websites and imports any pages you had to save by hand. |
| `collect_sc.py` | The custom scraper for South Carolina, plus some shared utility functions. |
| `validate_vote411_batch.py` | Double-checks the parsed Vote411 records against the raw saved pages. |
| `parse_state_sites.py` | Turns the raw HTML state pages into actual Q&A records. |
| `build_dataset.py` | Merges everything into the final dataset (one JSON file per state). |
| `quality_report.py` | Generates the data quality report so you can spot errors. |
| `compare_years.py` | Compares the current year against the baseline year, state by state. |
| `analyze_states.py` | Crunches the stats across states and draws the charts. |
| `check_results.py` | Recounts the published numbers and generates a list of records to spot-check manually. |
| `datasets.py` | Helper script that handles reading/writing the JSON datasets and `settings.toml`. |
| `describe_dataset.py` | Generates a manifest file to help the pipeline understand older datasets (like 2024) that it didn't build itself. |
| `restore_baseline.py` | Re-downloads the original 2024 baseline files if you accidentally delete or break them. |

Remember, `settings.toml` (rules and thresholds) and `sources.csv` (the URLs to scrape) are kept in the repo root. For a full setup guide and list of terminal options, check out [docs/TechnicalDescription.md](../docs/TechnicalDescription.md#getting-started--how-to-run).
