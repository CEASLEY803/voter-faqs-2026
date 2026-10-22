"""Check saved batch integrity and text retention without downloading pages."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup

from collect_sc import ROOT, source_text, validate_dataset, validate_records
from collect_vote411 import STATE_SLUGS


def text_tokens(text):
    return Counter(re.findall(r"\w+|[^\w\s]", text))


def check_state(directory, state):
    metadata = json.loads((directory / "collection_metadata.json").read_text(encoding="utf-8"))
    dataset = json.loads((directory / metadata["faq_file"]).read_text(encoding="utf-8"))
    supporting = json.loads((directory / metadata["supporting_content_file"]).read_text(encoding="utf-8"))
    if dataset["state"] != state or supporting["state"] != state:
        raise ValueError("Incorrect state identifier")
    if not dataset["questions"] and not supporting["sections"]:
        raise ValueError("Neither FAQ nor supporting content was extracted")
    validate_dataset(dataset, allow_empty=bool(supporting["sections"]))
    validate_records(supporting["sections"], ("topic", "kind", "content", "s", "t"))
    if supporting["num_sections"] != len(supporting["sections"]):
        raise ValueError("Incorrect supporting section count")
    source = metadata["sources"][0]
    expected_url = f"https://www.vote411.org/{STATE_SLUGS[state]}"
    if source["requested_url"] != expected_url:
        raise ValueError("Incorrect requested source URL")
    raw = (ROOT / source["snapshot"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError("Snapshot checksum mismatch")
    for entry in dataset["questions"] + supporting["sections"]:
        if entry["s"] != source["final_url"] or entry["t"] != source["collected_at"]:
            raise ValueError("Record source or timestamp does not match snapshot metadata")
    soup = BeautifulSoup(raw.decode("utf-8-sig"), "html.parser")
    bodies = soup.select(".tabs-right > .tab .tab-body")
    original_text = " ".join(source_text([body], source["final_url"]) for body in bodies)
    extracted_text = " ".join(entry["q"] + " " + entry["a"] for entry in dataset["questions"])
    extracted_text += " " + " ".join(entry["content"] for entry in supporting["sections"])
    if text_tokens(original_text) != text_tokens(extracted_text):
        raise ValueError("Source text tokens were lost or duplicated during extraction")
    if metadata.get("reprocessed_from"):
        original_source = json.loads((ROOT / metadata["reprocessed_from"] / "source_metadata.json").read_text())
        if source["collected_at"] != original_source["collected_at"] or source["sha256"] != original_source["sha256"]:
            raise ValueError("Reprocessing changed source bytes or collection time")
    return {"status": "passed", "faq_records": len(dataset["questions"]),
            "supporting_sections": len(supporting["sections"]), "review_flags": metadata["review_flags"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    arguments = parser.parse_args()
    manifest = json.loads((arguments.batch / "batch_manifest.json").read_text())
    results = {}
    for state in manifest["requested_states"]:
        try:
            results[state] = check_state(arguments.batch / state, state)
        except (ValueError, OSError, KeyError) as error:
            results[state] = {"status": "failed", "error": str(error)}
    failures = [state for state, result in results.items() if result["status"] == "failed"]
    report = {
        "status": "failed" if failures else "passed",
        "all_50_states_present": set(results) == set(STATE_SLUGS),
        "checks": ["record format and counts", "snapshot hashes", "state and source identity",
                   "source timestamps", "source-body word and punctuation token conservation"],
        "limitations": "Token counts do not verify text order, answer boundaries, browser appearance, or factual accuracy. Human source review remains required.",
        "states": results,
    }
    output = arguments.batch / "validation_report.json"
    output.write_text(json.dumps(report, indent=4) + "\n", encoding="utf-8")
    print(f"Validated {len(results)} states; {len(failures)} failed. Report: {output}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
