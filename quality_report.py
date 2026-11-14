"""Write a cycle's data quality report: one CSV row per finding, plus a short Markdown summary."""

import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from collect_sc import ROOT, source_urls
from datasets import (DATASET_FOLDER, SOURCES, below_baseline, dataset_dir, load_dataset, load_manifest, load_settings,
                      normalize_text, normalize_url, record_source)
from snapshot_state_sites import CANDIDATES_FILE, REMOVED_PAGE_ERRORS, removed_pages as removed_in_batch


FIELDS = ["category", "state", "source", "url", "question", "detail"]
SOURCE_NAMES = {"state": "state site", "vote411": "Vote411"}
# Category: what a row in that category means. The order here is the order in both output files.
# removed_page and menu_page come first because they are the ones to act on before the next run.
CATEGORIES = {
    "removed_page": "State-site pages still in sources.csv that are gone from the site, so nothing was collected from them. "
                    "Check the candidate replacements listed below and update sources.csv by hand before the next run.",
    "menu_page": "Saved state-site pages with no questions of their own that link to FAQ pages on the same site. "
                 "Each is listed below with its linked pages and their question counts. A linked page that is not "
                 "saved yet is missing from the dataset.",
    "flagged_page": "Saved state-site pages the parser flagged: no Q&A found, or far fewer records than the baseline had for the same URL.",
    "missing_source": "States with no records from a source.",
    "below_baseline": "States whose record count for a source is below {below_baseline_ratio:.0%} of the baseline cycle's count.",
    "dropped_non_faq": "State-site records left out by the non-FAQ rules in settings.toml.",
    "short_answer": "Answers shorter than {short_answer_chars} characters.",
    "long_answer": "Answers longer than {long_answer_chars} characters, which can mean an answer ran on into later content.",
    "duplicate_question": "The same question more than once within one state and source.",
}


def removed_pages(year):
    """Return one dict for each state-site page still in sources.csv that the site no longer has.

    The pages come from the state-site batch the build used. A failed page whose URL has since been
    replaced in sources.csv is left out, because it has already been dealt with. Each dict has the
    state, url, error and candidates. The candidates are the replacement pages that
    snapshot_state_sites.py --find-replacements saved in the batch folder, so nothing is downloaded
    here. candidates is None when that search has not covered the page.
    """
    batch = ROOT / load_manifest(year)["state_site_batch"]
    manifest = json.loads((batch / "batch_manifest.json").read_text(encoding="utf-8"))
    searched = {}
    if (batch / CANDIDATES_FILE).is_file():
        saved = json.loads((batch / CANDIDATES_FILE).read_text(encoding="utf-8"))
        searched = {(page["state"], page["removed_url"]): page for page in saved["pages"]}
    pages = []
    for state, record in removed_in_batch(manifest, source_urls("state")):
        found = searched.get((state, record["requested_url"]), {})
        pages.append({"state": state, "url": record["requested_url"], "error": record["error"],
                      "candidates": found.get("candidates"), "searched_at": found.get("searched_at", "")})
    return pages


def candidate_result(candidate):
    """What the search learned about one candidate: its question count, or why it could not be read."""
    if candidate.get("error"):
        return f"not counted: {candidate['error']}"
    return f"{candidate['questions']} question{'s' if candidate['questions'] != 1 else ''}"


def removed_page_detail(page):
    """The detail cell for a removed page: its error, then its candidates on one line."""
    if page["candidates"] is None:
        return f"{page['error']}; candidates not searched"
    if not page["candidates"]:
        return f"{page['error']}; no candidate found"
    return f"{page['error']}; candidates: " + ", ".join(
        f"{candidate['url']} ({candidate_result(candidate)})" for candidate in page["candidates"])


def removed_page_lines(year):
    """The summary's removed_page section: each page, with its candidates listed under it."""
    pages = removed_pages(year)
    lines = []
    if any(page["candidates"] for page in pages):
        lines += ["A candidate is a page on the same site that may have replaced the removed page. It was found by "
                  f"`snapshot_state_sites.py --find-replacements` on {max(page['searched_at'] for page in pages)[:10]}. The question count is "
                  "what the parser finds on the candidate. Closeness runs from 0 to 1 and says how alike the candidate's "
                  "address and link text are to the removed address; a low number is a weak guess. Open a candidate "
                  "before using it.", ""]
    for page in pages:
        lines.append(f"- {page['state'].upper()}: {page['url']} ({page['error']})")
        if page["candidates"] is None:
            lines.append("  - Candidates not searched. Run `snapshot_state_sites.py --batch <batch folder> --find-replacements`.")
        elif not page["candidates"]:
            lines.append("  - No candidate found.")
        for candidate in page["candidates"] or []:
            moved = normalize_url(candidate["final_url"]) != normalize_url(candidate["url"])
            lines.append(f"  - Candidate: {candidate['url']}, {candidate_result(candidate)} "
                         f"(link text \"{candidate['link_text']}\", closeness {candidate['closeness']}"
                         + (f", redirects to {candidate['final_url']})" if moved else ")"))
    return lines


def menu_pages(year):
    """The menu pages in the build's parse report, each with the pages it links to.

    build_dataset.py writes the list when it parses the batch, so each linked page's question count
    is the number of records the build took from it, before the non-FAQ rules.
    """
    report = json.loads((dataset_dir(year) / "state_site_parse_report.json").read_text(encoding="utf-8"))
    return [page for page in report if page.get("menu_links")]


def linked_page_result(link):
    """One linked page in words: its question count, or why it is not in the dataset."""
    if link["status"] == "saved":
        return f"{link['records']} question{'s' if link['records'] != 1 else ''}"
    if link["status"] == "failed" and link["error"] not in REMOVED_PAGE_ERRORS:
        return f"still has to be saved by hand: {link['error']}"
    if link["status"] == "failed":
        return f"not downloaded: {link['error']}"
    return "not downloaded yet"


def menu_page_total(page):
    """Such as "26 linked pages, 19 saved with 143 questions"."""
    saved = [link for link in page["menu_links"] if link["status"] == "saved"]
    return (f"{len(page['menu_links'])} linked page{'s' if len(page['menu_links']) != 1 else ''}, "
            f"{len(saved)} saved with {sum(link['records'] for link in saved)} questions")


def menu_page_lines(year):
    """The summary's menu_page section: each menu page, with its linked pages listed under it."""
    pages = menu_pages(year)
    lines = ["A menu page has no questions of its own. Its questions are on the pages it links to. "
             "`snapshot_state_sites.py --batch <batch folder> --follow-menus` downloads those pages into the batch. "
             "A linked page that refuses the download has to be saved by hand like any other blocked page: "
             "run the same script with `--checklist`, save the pages it lists, then run it with `--import-manual`. "
             "Rebuild the dataset afterwards.", ""]
    for page in pages:
        lines.append(f"- {page['state'].upper()}: {page['url']} ({menu_page_total(page)})")
        lines += [f"  - {link['url']}, {linked_page_result(link)} (link text \"{link['link_text']}\")"
                  for link in page["menu_links"]]
    return lines


def find_issues(year, baseline_year, settings):
    """Return one dict per finding, using the fields in FIELDS."""
    limits = settings["quality"]
    folder = dataset_dir(year)
    current, baseline = load_dataset(folder), load_dataset(dataset_dir(baseline_year))
    rows = []

    def add(category, state, source="", url="", question="", detail=""):
        rows.append({"category": category, "state": state, "source": SOURCE_NAMES.get(source, source),
                     "url": url, "question": question, "detail": detail})

    for page in removed_pages(year):
        add("removed_page", page["state"], "state", page["url"], detail=removed_page_detail(page))
    for page in menu_pages(year):
        add("menu_page", page["state"], "state", page["url"], detail=menu_page_total(page) + ": " + ", ".join(
            f"{link['url']} ({linked_page_result(link)})" for link in page["menu_links"]))
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
        f"Generated by `quality_report.py` from `data/{year}/{DATASET_FOLDER}/`. Every finding is a row in `quality_report.csv`.",
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
            lines += removed_page_lines(year)
        elif category == "menu_page":
            lines += menu_page_lines(year)
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
