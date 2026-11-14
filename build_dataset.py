"""Combine a cycle's Vote411 and state-site records into one file per state, like data/2024."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

from collect_sc import ROOT, validate_records
from collect_vote411 import vote411_urls
from datasets import (DATASET_FOLDER, dataset_dir, load_dataset, load_settings, non_faq_rules, normalize_text, write_json,
                      write_state_file)
from parse_state_sites import PARSER_VERSION, parse_batch


def latest_vote411_batch(year):
    """The newest Vote411 batch whose validation report passed for every state."""
    for batch in sorted((ROOT / "data" / str(year) / "batches").glob("*"), reverse=True):
        report_path = batch / "validation_report.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report["status"] == "passed" and report["all_50_states_present"]:
                return batch
    raise SystemExit(f"No validated Vote411 batch for {year}; run validate_vote411_batch.py first.")


def latest_state_site_batch(year):
    batches = sorted(path for path in (ROOT / "data" / str(year) / "state_sites").glob("*")
                     if (path / "batch_manifest.json").is_file())
    if not batches:
        raise SystemExit(f"No state-site batch for {year}; run snapshot_state_sites.py first.")
    return batches[-1]


def vote411_records(batch, state):
    """Return (question-heading records, section records) for one state from a saved Vote411 batch.

    A section with no question headings becomes one record: its title as the question and its text
    as the answer, the structure most 2024 Vote411 records have. Both lists come from files the
    collector wrote beside the saved page, so nothing is downloaded.
    """
    questions_path = batch / state / f"{state}_qa_vote411.json"
    questions = json.loads(questions_path.read_text(encoding="utf-8"))["questions"] if questions_path.is_file() else []
    sections_path = batch / state / f"{state}_supporting_content_vote411.json"
    sections = json.loads(sections_path.read_text(encoding="utf-8"))["sections"] if sections_path.is_file() else []
    section_records = [{"q": section["topic"], "a": section["content"], "s": section["s"], "t": section["t"]}
                       for section in sections if section["kind"] == "section_without_questions"]
    return questions, section_records


def vote411_method(question_count, section_count):
    if question_count and section_count:
        return "mixed"
    return "question_headings" if question_count else "section_titles" if section_count else "none"


def vote411_extraction(batch, counts):
    """Describe how this cycle's Vote411 records were extracted, per state, for later comparisons."""
    versions = set()
    for state in counts:
        path = batch / state / "collection_metadata.json"
        if path.is_file():
            versions.add(json.loads(path.read_text(encoding="utf-8"))["extraction_version"])
    return {
        "methods": {state: vote411_method(count["vote411_question_records"], count["vote411_section_records"])
                    for state, count in counts.items()},
        "method_basis": "Built from the saved Vote411 batch without downloading. A section with question headings "
                        "gives one record per published question heading (collect_vote411.py). A section without "
                        "question headings gives one record, with the section title as the question and the "
                        "section text as the answer (build_dataset.py). A state with both kinds is 'mixed'; a "
                        "state with only section records is 'section_titles'. Introductions above a section's "
                        "first question stay in the batch's supporting content files.",
        "extraction_versions": sorted(versions),
    }


def drop_non_faq(state, records, settings):
    """Split state-site records into (kept, dropped) using the non-FAQ rules in settings.toml."""
    rules = non_faq_rules(settings)
    limits = settings["non_faq"]
    pages = defaultdict(set)
    for record in records:
        pages[(normalize_text(record["q"]), normalize_text(record["a"]))].add(record["s"])
    kept, dropped = [], []
    for record in records:
        question = normalize_text(record["q"])
        reason = next((name for name, pattern in rules if pattern.search(question)), None)
        page_count = len(pages[(question, normalize_text(record["a"]))])
        if (reason is None and page_count >= limits["repeated_min_pages"]
                and len(question.split()) <= limits["repeated_max_words"]):
            reason = f"repeated page element (same question and answer on {page_count} pages)"
        if reason is None:
            kept.append(record)
        else:
            dropped.append({"state": state, "rule": reason, **record})
    return kept, dropped


def build(year, baseline_year, vote411_batch=None, state_site_batch=None, contributor="Cole Easley"):
    """Write data/<year>/dataset/ and return its manifest."""
    vote411_batch = Path(vote411_batch or latest_vote411_batch(year)).resolve()
    state_site_batch = Path(state_site_batch or latest_state_site_batch(year)).resolve()
    baseline = load_dataset(dataset_dir(baseline_year))
    state_records, parse_report = parse_batch(state_site_batch, baseline)
    output = ROOT / "data" / str(year) / DATASET_FOLDER
    output.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    counts, dropped = {}, []
    for state in vote411_urls():
        site, site_dropped = drop_non_faq(state, state_records.get(state, []), settings)
        dropped += site_dropped
        questions, sections = vote411_records(vote411_batch, state)
        records = site + questions + sections
        validate_records(records, ("q", "a", "s", "t"))
        write_state_file(output / f"{state}_qa.json", state, records, contributor)
        counts[state] = {"state_site": len(site), "state_site_dropped_non_faq": len(site_dropped),
                         "vote411": len(questions) + len(sections), "vote411_question_records": len(questions),
                         "vote411_section_records": len(sections), "total": len(records)}
    write_json(output / "state_site_parse_report.json", parse_report)
    write_json(output / "dropped_records.json", dropped)
    manifest = {
        "year": year,
        "baseline_year": baseline_year,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "vote411_batch": vote411_batch.relative_to(ROOT).as_posix(),
        "state_site_batch": state_site_batch.relative_to(ROOT).as_posix(),
        "state_site_parser_version": PARSER_VERSION,
        "record_order": "state-site records first, then Vote411 question-heading records, then Vote411 section "
                        "records; the s field gives each record's source",
        "extraction": {
            "vote411": vote411_extraction(vote411_batch, counts),
            "state": {"method": "general_parser", "parser_version": PARSER_VERSION,
                      "method_basis": "parse_state_sites.py: a question is a short block ending in a question mark "
                                      "or labelled Q:, and its answer runs to the next question or non-question "
                                      "heading. Per-page parsers and flags are in the parse report; its record "
                                      "counts are before the non-FAQ rules in settings.toml are applied.",
                      "non_faq_filter": "Records matching settings.toml's non-FAQ rules are left out and listed in "
                                        "dropped_records.json."},
        },
        "counts": counts,
        "flagged_pages": [{"state": page["state"], "url": page["url"], "flags": page["flags"]}
                          for page in parse_report if page["flags"]],
        "parse_report": "state_site_parse_report.json",
        "dropped_records": "dropped_records.json",
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True, help="Collection cycle, for example 2026")
    parser.add_argument("--baseline-year", type=int, default=2024)
    parser.add_argument("--vote411-batch", type=Path, help="Default: newest validated batch for the year")
    parser.add_argument("--state-site-batch", type=Path, help="Default: newest state-site batch for the year")
    parser.add_argument("--contributor", default="Cole Easley")
    arguments = parser.parse_args()
    manifest = build(arguments.year, arguments.baseline_year, arguments.vote411_batch,
                     arguments.state_site_batch, arguments.contributor)
    totals = {key: sum(count[key] for count in manifest["counts"].values())
              for key in next(iter(manifest["counts"].values()))}
    print(f"{arguments.year}: {totals['total']} records ({totals['state_site']} state site, {totals['vote411']} Vote411, "
          f"of which {totals['vote411_section_records']} are section records); "
          f"{totals['state_site_dropped_non_faq']} non-FAQ records dropped; "
          f"{len(manifest['flagged_pages'])} flagged pages. Output: data/{arguments.year}/{DATASET_FOLDER}/")


if __name__ == "__main__":
    main()
