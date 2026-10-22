"""Run the checked Vote411 parser on selected states or all 50 states."""

import argparse
from datetime import datetime, timezone
import json
import time

import requests

from collect_sc import ROOT, fetch_page, parse_vote411, validate_dataset, validate_records


STATE_SLUGS = {
    "ak": "alaska", "al": "alabama", "ar": "arkansas", "az": "arizona",
    "ca": "california", "co": "colorado", "ct": "connecticut", "de": "delaware",
    "fl": "florida", "ga": "georgia", "hi": "hawaii", "ia": "iowa",
    "id": "idaho", "il": "illinois", "in": "indiana", "ks": "kansas",
    "ky": "kentucky", "la": "louisiana", "ma": "massachusetts", "md": "maryland",
    "me": "maine", "mi": "michigan", "mn": "minnesota", "mo": "missouri",
    "ms": "mississippi", "mt": "montana", "nc": "north-carolina", "nd": "north-dakota",
    "ne": "nebraska", "nh": "new-hampshire", "nj": "new-jersey", "nm": "new-mexico",
    "nv": "nevada", "ny": "new-york", "oh": "ohio", "ok": "oklahoma",
    "or": "oregon", "pa": "pennsylvania", "ri": "rhode-island", "sc": "south-carolina",
    "sd": "south-dakota", "tn": "tennessee", "tx": "texas", "ut": "utah",
    "va": "virginia", "vt": "vermont", "wa": "washington", "wi": "wisconsin",
    "wv": "west-virginia", "wy": "wyoming",
}


def collect_state(state, contributor, batch_dir=None):
    """Keep one state's source snapshot and validated outputs in a separate run."""
    slug = STATE_SLUGS[state]
    url = f"https://www.vote411.org/{slug}"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if batch_dir is None:
        run_dir = ROOT / "data" / "2026" / "runs" / run_id
    else:
        run_dir = batch_dir / state
    run_dir.mkdir(parents=True, exist_ok=False)
    page, source_metadata = fetch_page(url, run_dir / f"vote411-{state}.html")
    (run_dir / "source_metadata.json").write_text(
        json.dumps(source_metadata, indent=4) + "\n", encoding="utf-8")
    questions, supporting = parse_vote411(page, source_metadata)
    dataset = {
        "state": state,
        "num_questions": len(questions),
        "num_answers": len(questions),
        "contributor": contributor,
        "questions": questions,
    }
    validate_dataset(dataset)
    validate_records(supporting, ("topic", "kind", "content", "s", "t"))
    faq_filename = f"{state}_qa_vote411.json"
    supporting_filename = f"{state}_supporting_content_vote411.json"
    supporting_dataset = {"state": state, "num_sections": len(supporting), "sections": supporting}
    metadata = {
        "state": state,
        "coverage": "Vote411 only; state election commission not yet collected in this run",
        "sources": [source_metadata],
        "counts": {"vote411": len(questions), "supporting_sections": len(supporting)},
        "extraction_version": 2,
        "faq_file": faq_filename,
        "supporting_content_file": supporting_filename,
        "review_status": "Pending human review of source fidelity and completeness",
    }
    outputs = {
        faq_filename: dataset,
        supporting_filename: supporting_dataset,
        "collection_metadata.json": metadata,
    }
    for filename, content in outputs.items():
        serialized = json.dumps(content, indent=4, ensure_ascii=False) + "\n"
        (run_dir / filename).write_text(serialized, encoding="utf-8")
    print(f"{state.upper()}: {len(questions)} FAQ records; {len(supporting)} supporting sections")
    print(f"Vote411-only output: {run_dir / faq_filename}")
    return run_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    accepted_states = list(STATE_SLUGS) + list(STATE_SLUGS.values())
    parser.add_argument("states", nargs="*", help="State codes or full URL slugs")
    parser.add_argument("--all", action="store_true", help="Collect all 50 US states")
    parser.add_argument("--contributor", default="Cole Easley")
    arguments = parser.parse_args()
    if arguments.all and arguments.states:
        parser.error("Use --all or specific states, not both.")
    if not arguments.all and not arguments.states:
        parser.error("Supply state codes or --all.")
    for state in arguments.states:
        if state not in accepted_states:
            parser.error(f"Unsupported state: {state}")
    codes_by_slug = {slug: code for code, slug in STATE_SLUGS.items()}
    if arguments.all:
        states = list(STATE_SLUGS)
    else:
        states = list(dict.fromkeys(codes_by_slug.get(state, state) for state in arguments.states))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    batch_dir = ROOT / "data" / "2026" / "batches" / run_id
    batch_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"requested_states": states, "coverage": "Vote411 only", "status": "running", "results": {}}
    manifest_path = batch_dir / "batch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=4) + "\n", encoding="utf-8")
    for index, state in enumerate(states):
        if index:
            time.sleep(1)
        try:
            run_dir = collect_state(state, arguments.contributor, batch_dir)
            metadata = json.loads((run_dir / "collection_metadata.json").read_text(encoding="utf-8"))
            manifest["results"][state] = {
                "status": "success", "directory": run_dir.relative_to(ROOT).as_posix(),
                "counts": metadata["counts"],
            }
        except (requests.RequestException, ValueError, OSError) as error:
            manifest["results"][state] = {
                "status": "failed", "error_type": type(error).__name__, "error": str(error),
                "directory": (batch_dir / state).relative_to(ROOT).as_posix(),
            }
            print(f"{state.upper()} FAILED: {error}")
        manifest_path.write_text(json.dumps(manifest, indent=4) + "\n", encoding="utf-8")
    failed = [state for state, result in manifest["results"].items() if result["status"] == "failed"]
    manifest["status"] = "completed_with_failures" if failed else "completed"
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest_path.write_text(json.dumps(manifest, indent=4) + "\n", encoding="utf-8")
    print(f"Batch finished: {len(states) - len(failed)} succeeded; {len(failed)} failed.")
    print(f"Manifest: {manifest_path}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
