"""Write a cycle's data quality report: one CSV row per finding, plus a short Markdown summary."""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from collect_sc import ROOT, source_urls
from datasets import (SOURCES, below_baseline, dataset_dir, load_dataset, load_manifest, load_settings, normalize_text,
                      record_source)
from snapshot_state_sites import REMOVED_PAGE_ERRORS


FIELDS = ["category", "state", "source", "url", "question", "detail"]
SOURCE_NAMES = {"state": "state site", "vote411": "Vote411"}
# Category: what a row in that category means. The order here is the order in both output files.
# removed_page comes first because it is the one to act on before the next run.
CATEGORIES = {
    "removed_page": "State-site pages still in sources.csv that are gone from the site, so nothing was collected from them. "
                    "Find each page's new address and update sources.csv before the next run.",
    "flagged_page": "Saved state-site pages the parser flagged: no Q&A found, or far fewer records than the baseline had for the same URL.",
    "missing_source": "States with no records from a source.",
    "below_baseline": "States whose record count for a source is below {below_baseline_ratio:.0%} of the baseline cycle's count.",
    "dropped_non_faq": "State-site records left out by the non-FAQ rules in settings.toml.",
    "short_answer": "Answers shorter than {short_answer_chars} characters.",
    "long_answer": "Answers longer than {long_answer_chars} characters, which can mean an answer ran on into later content.",
    "duplicate_question": "The same question more than once within one state and source.",
}


def removed_pages(year):
    """Return (state, url, error) for each state-site page still in sources.csv that the site no longer has.

    The pages come from the state-site batch the build used. A failed page whose URL has since been
    replaced in sources.csv is left out, because it has already been dealt with.
    """
    batch = ROOT / load_manifest(year)["state_site_batch"]
    pages = json.loads((batch / "batch_manifest.json").read_text(encoding="utf-8"))["pages"]
    urls = source_urls("state")
    return [(state, record["requested_url"], record["error"])
            for state, records in pages.items() for record in records
            if record["status"] == "failed" and record["error"] in REMOVED_PAGE_ERRORS
            and record["requested_url"] in urls.get(state, [])]


def find_issues(year, baseline_year, settings):
    """Return one dict per finding, using the fields in FIELDS."""
    limits = settings["quality"]
    folder = dataset_dir(year)
    current, baseline = load_dataset(folder), load_dataset(dataset_dir(baseline_year))
    rows = []

    def add(category, state, source="", url="", question="", detail=""):
        rows.append({"category": category, "state": state, "source": SOURCE_NAMES.get(source, source),
                     "url": url, "question": question, "detail": detail})

    for state, url, error in removed_pages(year):
        add("removed_page", state, "state", url, detail=error)
    for page in json.loads((folder / "state_site_parse_report.json").read_text(encoding="utf-8")):
        for flag in page["flags"]:
            add("flagged_page", page["state"], "state", page["url"], detail=flag)
    for state in sorted(current):
        for source in SOURCES:
            count = sum(record_source(record) == source for record in current[state])
            baseline_count = sum(record_source(record) == source for record in baseline.get(state, []))
            if count == 0:
                add("missing_source", state, source, detail=f"0 records; the {baseline_year} baseline had {baseline_count}")
            elif below_baseline(count, baseline_count, limits["below_baseline_ratio"]):
                add("below_baseline", state, source, detail=f"{count} records; the {baseline_year} baseline had {baseline_count}")
    for record in json.loads((folder / "dropped_records.json").read_text(encoding="utf-8")):
        add("dropped_non_faq", record["state"], "state", record["s"], record["q"], f"Rule: {record['rule']}")
    for state in sorted(current):
        groups = defaultdict(list)
        for record in current[state]:
            source = record_source(record)
            length = len(record["a"])
            if length < limits["short_answer_chars"]:
                add("short_answer", state, source, record["s"], record["q"], f"{length} characters: {record['a']}")
            elif length > limits["long_answer_chars"]:
                add("long_answer", state, source, record["s"], record["q"], f"{length} characters")
            groups[(source, normalize_text(record["q"]))].append(record)
        for (source, _), records in groups.items():
            if len(records) > 1:
                pages = len({record["s"] for record in records})
                answers = len({normalize_text(record["a"]) for record in records})
                add("duplicate_question", state, source, records[0]["s"], records[0]["q"],
                    f"{len(records)} records on {pages} page{'s' if pages != 1 else ''}; "
                    + ("identical answers" if answers == 1 else f"{answers} different answers"))
    order = list(CATEGORIES)
    return sorted(rows, key=lambda row: (order.index(row["category"]), row["state"], row["source"], row["question"]))


def summary_markdown(rows, year, baseline_year, settings):
    """A short summary: what was checked, how many findings per category, and which states they touch."""
    manifest = load_manifest(year)
    totals = {key: sum(count[key] for count in manifest["counts"].values()) for key in ("state_site", "vote411", "total")}
    by_category = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)
    lines = [
        f"# Data quality summary, {year}",
        "",
        f"Generated by `quality_report.py` from `data/{year}/combined/`. Every finding is a row in `quality_report.csv`.",
        "",
        f"- Records: {totals['total']} ({totals['state_site']} state site, {totals['vote411']} Vote411) in {len(manifest['counts'])} states.",
        f"- Baseline cycle: {baseline_year}.",
        f"- State-site batch: `{manifest['state_site_batch']}`.",
        f"- Vote411 batch: `{manifest['vote411_batch']}`.",
        "",
        "| Category | Findings | States | What it means |",
        "| --- | --- | --- | --- |",
    ]
    for category, description in CATEGORIES.items():
        found = by_category[category]
        lines.append(f"| `{category}` | {len(found)} | {len({row['state'] for row in found})} | "
                     f"{description.format(**settings['quality'])} |")
    for category in CATEGORIES:
        found = by_category[category]
        if not found:
            continue
        lines += ["", f"## {category}", ""]
        if category == "removed_page":
            lines += [f"- {row['state'].upper()}: {row['url']} ({row['detail']})" for row in found]
        elif category in ("missing_source", "below_baseline"):
            lines += [f"- {row['state'].upper()}, {row['source']}: {row['detail']}" for row in found]
        elif category == "dropped_non_faq":
            lines += [f"- {row['state'].upper()}: \"{row['question']}\" ({row['detail']})" for row in found]
        else:
            counts = Counter(row["state"] for row in found)
            lines.append("Findings per state: " + ", ".join(f"{state.upper()} {count}" for state, count in sorted(counts.items())) + ".")
    return "\n".join(lines) + "\n"


def write_quality_report(year, baseline_year, settings=None):
    """Write data/<year>/quality/quality_report.csv and quality_summary.md; return the findings."""
    settings = settings or load_settings()
    rows = find_issues(year, baseline_year, settings)
    folder = ROOT / "data" / str(year) / "quality"
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "quality_report.csv", "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (folder / "quality_summary.md").write_text(summary_markdown(rows, year, baseline_year, settings), encoding="utf-8")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--baseline-year", type=int, default=2024)
    arguments = parser.parse_args()
    rows = write_quality_report(arguments.year, arguments.baseline_year)
    counts = Counter(row["category"] for row in rows)
    print(f"{len(rows)} findings: " + ", ".join(f"{category} {counts[category]}" for category in CATEGORIES)
          + f". Output: data/{arguments.year}/quality/")


if __name__ == "__main__":
    main()
