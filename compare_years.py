"""Compare two cycles per state within each source: state site to state site, Vote411 to Vote411."""

import argparse
import csv
from difflib import SequenceMatcher
from pathlib import Path

from collect_sc import ROOT
from datasets import SOURCES, dataset_dir, load_dataset, normalize_text, record_source, write_json


# Question pairs at or above this similarity are the same question reworded. Pairs from the
# 2024 to 2026 data at 0.8 to 0.9 read as rewordings ("obtain" vs "get a replacement ballot");
# pairs at 0.7 to 0.8 are often different questions on one topic.
REWORDED_THRESHOLD = 0.8
SUMMARY_FIELDS = ["state", "source", "baseline_count", "current_count", "same", "reworded", "new", "removed",
                  "answers_changed", "excluded_other_baseline", "excluded_other_current"]


def similarity(first, second):
    return SequenceMatcher(None, first, second, autojunk=False).ratio()


def answer_comparison(baseline, current):
    """An answer is unchanged when its normalized words match; spacing differences come from extraction."""
    old, new = normalize_text(baseline["a"]), normalize_text(current["a"])
    if old.replace(" ", "") == new.replace(" ", ""):
        return "unchanged", 1.0
    return "changed", round(similarity(old, new), 3)


def item(status, baseline=None, current=None, question_similarity=None):
    entry = {"status": status,
             "baseline_q": baseline["q"] if baseline else None, "current_q": current["q"] if current else None,
             "question_similarity": question_similarity,
             "baseline_s": baseline["s"] if baseline else None, "current_s": current["s"] if current else None}
    if baseline and current:
        entry["answer_status"], entry["answer_similarity"] = answer_comparison(baseline, current)
    return entry


def match_questions(baseline, current):
    """Classify each question as same, reworded, new or removed, matching one to one."""
    items = []
    old = [(normalize_text(record["q"]), record) for record in baseline]
    new = [(normalize_text(record["q"]), record) for record in current]
    # Pass 1: identical questions after normalization.
    unmatched_new = list(new)
    unmatched_old = []
    for key, record in old:
        index = next((i for i, (other, _) in enumerate(unmatched_new) if other == key), None)
        if index is None:
            unmatched_old.append((key, record))
        else:
            items.append(item("same", record, unmatched_new.pop(index)[1], 1.0))
    # Pass 2: the most similar remaining pairs, best first, above the threshold.
    candidates = []
    for i, (old_key, _) in enumerate(unmatched_old):
        for j, (new_key, _) in enumerate(unmatched_new):
            matcher = SequenceMatcher(None, old_key, new_key, autojunk=False)
            if matcher.real_quick_ratio() >= REWORDED_THRESHOLD and matcher.quick_ratio() >= REWORDED_THRESHOLD:
                score = matcher.ratio()
                if score >= REWORDED_THRESHOLD:
                    candidates.append((score, i, j))
    used_old, used_new = set(), set()
    for score, i, j in sorted(candidates, reverse=True):
        if i not in used_old and j not in used_new:
            used_old.add(i)
            used_new.add(j)
            items.append(item("reworded", unmatched_old[i][1], unmatched_new[j][1], round(score, 3)))
    items += [item("removed", baseline=record) for i, (_, record) in enumerate(unmatched_old) if i not in used_old]
    items += [item("new", current=record) for j, (_, record) in enumerate(unmatched_new) if j not in used_new]
    return items


def compare(baseline, current, states=None):
    """Return ({state: items}, summary rows) for the states present in the current cycle."""
    details, summary = {}, []
    for state in sorted(states or current):
        details[state] = []
        for source in SOURCES:
            old = [record for record in baseline.get(state, []) if record_source(record) == source]
            new = [record for record in current.get(state, []) if record_source(record) == source]
            items = match_questions(old, new)
            for entry in items:
                entry["source"] = source
            details[state] += items
            counts = {status: sum(entry["status"] == status for entry in items) for status in ("same", "reworded", "new", "removed")}
            summary.append({
                "state": state, "source": source, "baseline_count": len(old), "current_count": len(new), **counts,
                "answers_changed": sum(entry.get("answer_status") == "changed" for entry in items),
                "excluded_other_baseline": sum(record_source(record) == "other" for record in baseline.get(state, [])) if source == "state" else 0,
                "excluded_other_current": sum(record_source(record) == "other" for record in current.get(state, [])) if source == "state" else 0,
            })
    return details, summary


def write_comparison(output, details, summary, baseline_year, year):
    """Write one detail file per state and a summary CSV under output/comparison/."""
    folder = Path(output) / "comparison"
    for state, items in details.items():
        write_json(folder / f"{state}.json", {"state": state, "baseline_year": baseline_year, "year": year,
                                              "reworded_threshold": REWORDED_THRESHOLD, "items": items})
    with open(folder / "summary.csv", "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--baseline-year", type=int, default=2024)
    parser.add_argument("--output", type=Path, help="Default: data/<year>/analysis")
    arguments = parser.parse_args()
    baseline, current = load_dataset(dataset_dir(arguments.baseline_year)), load_dataset(dataset_dir(arguments.year))
    details, summary = compare(baseline, current)
    output = arguments.output or ROOT / "data" / str(arguments.year) / "analysis"
    write_comparison(output, details, summary, arguments.baseline_year, arguments.year)
    totals = {key: sum(row[key] for row in summary) for key in ("same", "reworded", "new", "removed", "answers_changed")}
    print(f"{arguments.baseline_year} to {arguments.year}: {totals}. Output: {Path(output) / 'comparison'}")


if __name__ == "__main__":
    main()
