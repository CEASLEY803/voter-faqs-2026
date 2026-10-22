"""Run the checked Vote411 parser on the three pilot states."""

import argparse
from datetime import datetime, timezone
import json

from collect_sc import ROOT, fetch_page, parse_vote411, validate_dataset, validate_records


STATE_SLUGS = {"sc": "south-carolina", "ga": "georgia", "oh": "ohio"}


def collect_state(state, contributor):
    """Keep one state's source snapshot and validated outputs in a separate run."""
    slug = STATE_SLUGS[state]
    url = f"https://www.vote411.org/{slug}"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = ROOT / "data" / "2026" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    page, source_metadata = fetch_page(url, run_dir / f"vote411-{state}.html")
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
    parser.add_argument("states", nargs="+", choices=accepted_states)
    parser.add_argument("--contributor", default="Cole Easley")
    arguments = parser.parse_args()
    codes_by_slug = {slug: code for code, slug in STATE_SLUGS.items()}
    for state in arguments.states:
        code = codes_by_slug.get(state, state)
        collect_state(code, arguments.contributor)


if __name__ == "__main__":
    main()
