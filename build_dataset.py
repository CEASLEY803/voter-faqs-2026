"""Combine a cycle's Vote411 and state-site records into one file per state, like data/2024."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from collect_sc import ROOT, validate_records
from collect_vote411 import vote411_urls
from datasets import dataset_dir, load_dataset, write_json, write_state_file
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
    path = batch / state / f"{state}_qa_vote411.json"
    return json.loads(path.read_text(encoding="utf-8"))["questions"] if path.is_file() else []


def build(year, baseline_year, vote411_batch=None, state_site_batch=None, contributor="Cole Easley"):
    """Write data/<year>/combined/ and return its manifest."""
    vote411_batch = Path(vote411_batch or latest_vote411_batch(year)).resolve()
    state_site_batch = Path(state_site_batch or latest_state_site_batch(year)).resolve()
    baseline = load_dataset(dataset_dir(baseline_year))
    state_records, parse_report = parse_batch(state_site_batch, baseline)
    output = ROOT / "data" / str(year) / "combined"
    output.mkdir(parents=True, exist_ok=True)
    counts = {}
    for state in vote411_urls():
        site, vote411 = state_records.get(state, []), vote411_records(vote411_batch, state)
        records = site + vote411
        validate_records(records, ("q", "a", "s", "t"))
        write_state_file(output / f"{state}_qa.json", state, records, contributor)
        counts[state] = {"state_site": len(site), "vote411": len(vote411), "total": len(records)}
    write_json(output / "state_site_parse_report.json", parse_report)
    manifest = {
        "year": year,
        "baseline_year": baseline_year,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "vote411_batch": vote411_batch.relative_to(ROOT).as_posix(),
        "state_site_batch": state_site_batch.relative_to(ROOT).as_posix(),
        "state_site_parser_version": PARSER_VERSION,
        "record_order": "state-site records first, then Vote411 records; the s field gives each record's source",
        "counts": counts,
        "flagged_pages": [{"state": page["state"], "url": page["url"], "flags": page["flags"]}
                          for page in parse_report if page["flags"]],
        "parse_report": "state_site_parse_report.json",
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
    totals = {key: sum(count[key] for count in manifest["counts"].values()) for key in ("state_site", "vote411", "total")}
    print(f"{arguments.year}: {totals['total']} records ({totals['state_site']} state site, {totals['vote411']} Vote411); "
          f"{len(manifest['flagged_pages'])} flagged pages. Output: data/{arguments.year}/combined/")


if __name__ == "__main__":
    main()
