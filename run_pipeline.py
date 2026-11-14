"""Run the whole pipeline for one election cycle.

Steps: optional collection (--collect), build data/<year>/dataset/, write the data quality report
to data/<year>/quality/, create or extend the review file data/<year>/review.csv, then compare with
the baseline cycle and write the cross-state analysis. Thresholds and rules are in settings.toml. With --approved-only, the comparison and analysis use only states marked approved in
the review file and are written to data/<year>/analysis_approved/ instead of data/<year>/analysis/.
"""

import argparse
import csv
from datetime import date
import json
from pathlib import Path
import subprocess
import sys

from analyze_states import analyze
from build_dataset import build, latest_state_site_batch, latest_vote411_batch
from collect_sc import ROOT
from collect_vote411 import vote411_urls
from compare_years import pairs_table_link
from datasets import DATASET_FOLDER, load_settings
from quality_report import write_quality_report
from snapshot_state_sites import REMOVED_PAGE_ERRORS


REVIEW_FIELDS = ["state", "status", "reviewer", "review_date", "notes"]
STATUSES = {"pending", "approved", "rejected"}


def run(script, *arguments):
    """Run one of the project's scripts with the same Python; stop the pipeline if it fails."""
    command = [sys.executable, str(ROOT / script), *map(str, arguments)]
    print("Running:", " ".join(command[1:]))
    if subprocess.run(command, cwd=ROOT).returncode != 0:
        raise SystemExit(f"{script} failed; fix the problem above and run the pipeline again.")


def collect(year):
    """Download Vote411 and state-site pages, look for replacements for removed pages; stop if pages still need saving by hand."""
    run("collect_vote411.py", "--all", "--year", year)
    run("validate_vote411_batch.py", latest_vote411_batch_path(year))
    run("snapshot_state_sites.py", "--year", year)
    batch = latest_state_site_batch(year)
    # Runs before the check below, so the suggestions exist even when the pipeline stops for pages to save by hand.
    run("snapshot_state_sites.py", "--year", year, "--batch", batch.relative_to(ROOT), "--find-replacements")
    manifest = json.loads((batch / "batch_manifest.json").read_text(encoding="utf-8"))
    blocked = [page for pages in manifest["pages"].values() for page in pages
               if page["status"] == "failed" and page.get("error") not in REMOVED_PAGE_ERRORS]
    if blocked:
        run("snapshot_state_sites.py", "--year", year, "--batch", batch.relative_to(ROOT), "--checklist")
        raise SystemExit(f"{len(blocked)} pages refused scripted downloads. Save them by hand as listed in "
                         f"manual_saves/checklist.csv, import them with snapshot_state_sites.py --batch "
                         f"{batch.relative_to(ROOT)} --import-manual, then rerun this pipeline without --collect.")


def latest_vote411_batch_path(year):
    """The newest Vote411 batch folder, validated or not, so the new batch can be validated."""
    return sorted((ROOT / "data" / str(year) / "batches").glob("*"))[-1].relative_to(ROOT)


def sync_review_file(path, states):
    """Create the review file, or add states it lacks; rows already in it are never changed."""
    rows = []
    if path.is_file():
        with open(path, newline="", encoding="utf-8-sig") as file:
            rows = list(csv.DictReader(file))
    present = {row["state"].strip().lower() for row in rows}
    missing = [state for state in states if state not in present]
    if missing or not path.is_file():
        rows += [{"state": state, "status": "pending", "reviewer": "", "review_date": "", "notes": ""} for state in missing]
        with open(path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=REVIEW_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    return rows


def approved_states(rows):
    """States marked approved; an approved row must name a reviewer and give a YYYY-MM-DD date."""
    approved, problems = [], []
    for line, row in enumerate(rows, start=2):
        status = row.get("status", "").strip().lower()
        if status not in STATUSES:
            problems.append(f"line {line}: status must be pending, approved or rejected, not {row.get('status')!r}")
        elif status == "approved":
            try:
                date.fromisoformat(row.get("review_date", "").strip())
            except ValueError:
                problems.append(f"line {line}: {row['state']} is approved but review_date is not a YYYY-MM-DD date")
                continue
            if not row.get("reviewer", "").strip():
                problems.append(f"line {line}: {row['state']} is approved but has no reviewer name")
                continue
            approved.append(row["state"].strip().lower())
    if problems:
        raise SystemExit("review.csv has problems:\n  " + "\n  ".join(problems))
    return approved


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, required=True, help="Collection cycle, for example 2026")
    parser.add_argument("--baseline-year", type=int, default=2024, help="Cycle to compare against")
    parser.add_argument("--collect", action="store_true", help="Download Vote411 and state-site pages first")
    parser.add_argument("--skip-build", action="store_true", help="Reuse data/<year>/dataset/ as it is")
    parser.add_argument("--approved-only", action="store_true", help="Compare and analyze approved states only")
    parser.add_argument("--vote411-batch", type=Path, help="Default: newest validated Vote411 batch for the year")
    parser.add_argument("--state-site-batch", type=Path, help="Default: newest state-site batch for the year")
    parser.add_argument("--contributor", default="Cole Easley")
    arguments = parser.parse_args()
    year = arguments.year
    if arguments.collect:
        collect(year)
    if not arguments.skip_build:
        manifest = build(year, arguments.baseline_year, arguments.vote411_batch or latest_vote411_batch(year),
                         arguments.state_site_batch or latest_state_site_batch(year), arguments.contributor)
        print(f"Built the {year} dataset: {sum(c['total'] for c in manifest['counts'].values()):,} questions and sections "
              f"from state election sites and Vote411, one file per state in data/{year}/{DATASET_FOLDER}/")
    findings = write_quality_report(year, arguments.baseline_year)
    print(f"Checked the data: {len(findings):,} possible problems")
    review_path = ROOT / "data" / str(year) / "review.csv"
    rows = sync_review_file(review_path, list(vote411_urls()))
    approved = approved_states(rows)
    print(f"Review: {len(approved)} of {len(rows)} states approved")
    if arguments.approved_only:
        if not approved:
            raise SystemExit("No states are approved yet; mark states approved in the review file first.")
        states, output = approved, ROOT / "data" / str(year) / "analysis_approved"
    else:
        states, output = None, ROOT / "data" / str(year) / "analysis"
    analyzed = analyze(year, arguments.baseline_year, output, states)
    print(f"Compared {year} with {arguments.baseline_year} for {len(analyzed)} states")
    # Each line above is printed as its step finishes. The steps below say which file to open for each one.
    folder = f"data/{year}/{output.name}"
    print(f"""
Next steps:
  1. Check the possible problems: data/{year}/quality/quality_summary.md
  2. Approve each state after checking its data: data/{year}/review.csv
  3. See each state's change rates: {folder}/per_state.csv and the charts in {folder}/charts/
  4. Browse every compared question (the link reads the copy on GitHub, so push this data first):
     {pairs_table_link(output, arguments.baseline_year, year, load_settings()["github"])}""")


if __name__ == "__main__":
    main()
