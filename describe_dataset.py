"""Write a manifest for a dataset this pipeline did not build, such as the 2024 baseline.

The manifest records how each state's Vote411 records were extracted, inferred from the records
themselves, so the comparison can tell when two cycles used different methods. Correct a state by
editing the manifest's extraction.vote411.methods entry.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json

from collect_sc import ROOT
from datasets import (assign_vote411_section, dataset_dir, load_dataset, load_settings, normalize_text,
                      record_source, vote411_section_rules, write_json)


# A wording used by this many states is a rewritten Vote411 section title, since only titles are shared.
SHARED_WORDING_STATES = 5
# A state "follows the section layout" when its records cover this many sections, about one record each.
LAYOUT_MIN_SECTIONS = 10
LAYOUT_MAX_RECORDS_PER_SECTION = 1.5
# Share of section-title records at or above which a state is section_titles, at or below which question_headings.
SECTION_TITLES_SHARE = 0.9
QUESTION_HEADINGS_SHARE = 0.1
METHOD_BASIS = (
    "Inferred from the records. A record counts as a section title when its wording is used by at least "
    f"{SHARED_WORDING_STATES} states, or when it is the only record assigned to its section (by the keyword rules "
    f"in settings.toml) in a state whose records cover at least {LAYOUT_MIN_SECTIONS} sections with at most "
    f"{LAYOUT_MAX_RECORDS_PER_SECTION} records per section. A state is section_titles when at least "
    f"{SECTION_TITLES_SHARE:.0%} of its records are section titles, question_headings when at most "
    f"{QUESTION_HEADINGS_SHARE:.0%} are, and mixed otherwise."
)


def infer_vote411_methods(dataset, rules):
    """Return ({state: method}, {state: evidence}) from each state's Vote411 records."""
    questions = {state: [normalize_text(r["q"]) for r in records if record_source(r) == "vote411"]
                 for state, records in dataset.items()}
    states_using = Counter(question for qs in questions.values() for question in set(qs))
    methods, evidence = {}, {}
    for state, qs in sorted(questions.items()):
        if not qs:
            methods[state], evidence[state] = "none", {"records": 0}
            continue
        sections = [assign_vote411_section(question, rules) for question in qs]
        per_section = Counter(section for section in sections if section)
        follows_layout = (len(per_section) >= LAYOUT_MIN_SECTIONS
                          and len(qs) <= LAYOUT_MAX_RECORDS_PER_SECTION * len(per_section))
        title_like = [states_using[question] >= SHARED_WORDING_STATES
                      or (follows_layout and section is not None and per_section[section] == 1)
                      for question, section in zip(qs, sections)]
        share = sum(title_like) / len(qs)
        methods[state] = ("section_titles" if share >= SECTION_TITLES_SHARE
                          else "question_headings" if share <= QUESTION_HEADINGS_SHARE else "mixed")
        evidence[state] = {"records": len(qs), "sections_covered": len(per_section),
                           "unassigned_records": sum(section is None for section in sections),
                           "section_title_share": round(share, 2)}
    return methods, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--force", action="store_true", help="Replace an existing manifest")
    arguments = parser.parse_args()
    folder = dataset_dir(arguments.year)
    path = folder / "manifest.json"
    if path.is_file() and not arguments.force:
        raise SystemExit(f"{path.relative_to(ROOT)} exists; pass --force to replace it, which discards manual corrections.")
    methods, evidence = infer_vote411_methods(load_dataset(folder), vote411_section_rules(load_settings()))
    provenance_path = ROOT / "reference" / "baseline_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.is_file() else {}
    manifest = {
        "year": arguments.year,
        "described_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {key: provenance[key] for key in ("repository", "commit") if key in provenance},
        "extraction": {
            "vote411": {"methods": methods, "method_basis": METHOD_BASIS, "evidence": evidence},
            "state": {"method": "not recorded", "method_basis": "Collected by the original project; its extraction method is not documented."},
        },
    }
    write_json(path, manifest)
    print(f"Wrote {path.relative_to(ROOT)}: {dict(Counter(methods.values()))}")


if __name__ == "__main__":
    main()
