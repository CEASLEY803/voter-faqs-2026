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

from analyze_states import analyze, left_out_warning
from build_dataset import build, latest_state_site_batch, latest_vote411_batch
from check_results import check_results, not_matching
from collect_sc import CODE, ROOT
from collect_vote411 import vote411_urls
from compare_years import pairs_table_link
from datasets import DATASET_FOLDER, load_manifest, load_settings
from quality_report import write_quality_report
from snapshot_state_sites import REMOVED_PAGE_ERRORS


REVIEW_FIELDS = ["state", "status", "reviewer", "review_date", "notes"]
STATUSES = {"pending", "approved", "rejected"}


def run(script, *arguments):
    """Run one of the project's scripts with the same Python; stop the pipeline if it fails."""
    command = [sys.executable, str(CODE / script), *map(str, arguments)]
    print("Running:", " ".join(command[1:]))
    if subprocess.run(command, cwd=ROOT).returncode != 0:
        raise SystemExit(f"code/{script} failed; fix the problem above and run the pipeline again.")


def blocked_pages(batch):
    """Pages in a state-site batch that failed because the site refused them, not because they are gone."""
    manifest = json.loads((batch / "batch_manifest.json").read_text(encoding="utf-8"))
    return [page for pages in manifest["pages"].values() for page in pages
            if page["status"] == "failed" and page.get("error") not in REMOVED_PAGE_ERRORS]


def collect(year):
    """Download Vote411 and state-site pages, follow menu pages, look for replacements for removed pages; stop if pages still need saving by hand."""
    run("collect_vote411.py", "--all", "--year", year)
    run("validate_vote411_batch.py", latest_vote411_batch_path(year))
    run("snapshot_state_sites.py", "--year", year)
    batch = latest_state_site_batch(year)
    # A saved page that is only a menu of FAQ topics has its linked pages downloaded too. This runs before
    # the check below, so a linked page that refuses the download joins the list of pages to save by hand.
    run("snapshot_state_sites.py", "--year", year, "--batch", batch.relative_to(ROOT), "--follow-menus")
    # Runs before the check below, so the suggestions exist even when the pipeline stops for pages to save by hand.
    run("snapshot_state_sites.py", "--year", year, "--batch", batch.relative_to(ROOT), "--find-replacements")
    if blocked_pages(batch):
        # --checklist first fills what it can from the Internet Archive, then lists the rest to save by hand.
        run("snapshot_state_sites.py", "--year", year, "--batch", batch.relative_to(ROOT), "--checklist")
    blocked = blocked_pages(batch)
    if blocked:
        raise SystemExit(f"{len(blocked)} pages refused scripted downloads and have no Internet Archive copy "
                         f"from the weeks before election day. Save them by hand as listed in "
                         f"manual_saves/checklist.csv, import them with code/snapshot_state_sites.py --batch "
                         f"{batch.relative_to(ROOT)} --import-manual (it says so if an imported page leads to more "
                         f"pages to save), then rerun this pipeline without --collect.")


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


def year_folder_contents(year, baseline_year):
    """(name, what it holds) for everything the pipeline can put in data/<year>/, in the order a cycle makes it."""
    return [
        ("state_sites/", "State election site pages exactly as they were saved. One folder per collection batch, with a "
                         "subfolder per state and a `batch_manifest.json` that says where each page came from and when."),
        ("batches/", "Vote411 pages exactly as they were saved, and the records taken from them. One folder per "
                     "collection batch, with a subfolder per state."),
        ("runs/", "Runs of the South Carolina collector `code/collect_sc.py`, each with the pages it saved and the records taken from them."),
        (f"{DATASET_FOLDER}/", f"The {year} dataset: one file per state (`<state>_qa.json`) with its questions and answers from both "
                               "sources, plus `manifest.json` and the build's reports."),
        ("quality/", "The data quality report: possible problems in the dataset, as `quality_report.csv` and `quality_summary.md`."),
        ("review.csv", "One row per state. A person marks a state approved or rejected here after checking its data."),
        ("analysis/", f"The comparison with {baseline_year} for every state: change rates in `per_state.csv`, the charts, every "
                      "compared question in `comparison/pairs.csv`, and the cross-check in `check/`."),
        ("analysis_approved/", "The same comparison, for only the states marked approved in `review.csv`."),
    ]


def write_year_readme(year, baseline_year):
    """Write data/<year>/README.md: what the folder holds, the record counts and one line per folder or file in it.

    It lists only what exists, and it holds no date or time, so a second run on the same data writes
    the same file. It is written into data/<year>/ itself and nowhere deeper: batches/ and
    state_sites/ must hold batch folders only, because the newest entry in them is taken as the newest batch.
    """
    folder = ROOT / "data" / str(year)
    counts = load_manifest(year)["counts"]
    totals = {key: sum(count[key] for count in counts.values()) for key in ("state_site", "vote411", "total")}
    lines = [
        f"# {year} voter FAQ data", "",
        f"This folder holds the voter FAQ data collected for the {year} election cycle, for {len(counts)} state{'s' if len(counts) != 1 else ''}. "
        f"It was compared with the {baseline_year} data in `data/{baseline_year}/`.", "",
        "| Source | Records |", "| --- | --- |",
        f"| State election sites | {totals['state_site']:,} |", f"| Vote411 | {totals['vote411']:,} |",
        f"| Both | {totals['total']:,} |", "",
        "| Folder or file | What it holds |", "| --- | --- |",
    ]
    lines += [f"| `{name}` | {holds} |" for name, holds in year_folder_contents(year, baseline_year) if (folder / name).exists()]
    lines += ["", "How the data is collected, built, checked and compared is described in "
                  "[docs/TechnicalDescription.md](../../docs/TechnicalDescription.md).", "",
              "This file is written by `code/run_pipeline.py` at the end of each run."]
    (folder / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    folder = f"data/{year}/{output.name}"
    # The numbers just written are worked out a second time by separate code. A difference means a mistake
    # in one of the two, so the run stops before anyone shares the outputs.
    recounted, mismatches = check_results(year, arguments.baseline_year, output)
    if mismatches:
        print(f"Cross-check: {recounted:,} numbers recounted, {not_matching(len(mismatches))}:")
        print("\n".join("  " + line for line in mismatches))
        raise SystemExit(f"The recount and the published numbers differ, so do not share these outputs. "
                         f"The differences are also listed in {folder}/check/check_results.md.")
    print(f"Cross-check: {recounted:,} numbers recounted, all match")
    # A chart with states missing looks complete, so the run says which ones are left out and why.
    warning = left_out_warning(analyzed, arguments.baseline_year, year, load_settings()["quality"])
    if warning:
        print("\n" + "\n".join(warning))
    write_year_readme(year, arguments.baseline_year)
    # Each line above is printed as its step finishes. The steps below say which file to open for each one.
    print(f"""
Next steps:
  1. Check the possible problems: data/{year}/quality/quality_summary.md
  2. Approve each state after checking its data: data/{year}/review.csv
  3. See each state's change rates: {folder}/per_state.csv and the charts in {folder}/charts/
  4. Check the results by hand: fill in {folder}/check/spot_check.csv and compare {folder}/check/check_results.md with the charts
  5. Browse every compared question (the link reads the copy on GitHub, so push this data first):
     {pairs_table_link(output, arguments.baseline_year, year, load_settings()["github"])}""")


if __name__ == "__main__":
    main()
