"""Compare two cycles per state within each source: state site to state site, Vote411 to Vote411."""

import argparse
from collections import Counter
import csv
import json
from difflib import SequenceMatcher
from pathlib import Path

from bs4 import BeautifulSoup

from collect_sc import ROOT, source_text
from datasets import (SOURCES, assign_vote411_section, dataset_dir, load_dataset, load_manifest, load_settings,
                      normalize_text, record_source, vote411_method, vote411_section_rules, write_json)


# Question pairs at or above this similarity are the same question reworded. Pairs from the
# 2024 to 2026 data at 0.8 to 0.9 read as rewordings ("obtain" vs "get a replacement ballot");
# pairs at 0.7 to 0.8 are often different questions on one topic.
REWORDED_THRESHOLD = 0.8
# A line repeated in at least this share of one source's answers in a state is page boilerplate,
# such as the contact line West Virginia appends to every 2026 answer. Needs at least BOILERPLATE_MIN answers.
BOILERPLATE_SHARE = 0.6
BOILERPLATE_MIN = 5
SUMMARY_FIELDS = ["state", "source", "unit", "baseline_method", "current_method", "baseline_count", "current_count",
                  "same", "reworded", "new", "removed", "unassigned", "answers_changed",
                  "excluded_other_baseline", "excluded_other_current"]
# Vote411 methods whose records stand for whole sections rather than single questions.
SECTION_METHODS = {"section_titles", "mixed", "sections_without_questions", "unknown"}


def similarity(first, second):
    return SequenceMatcher(None, first, second, autojunk=False).ratio()


def boilerplate_lines(records):
    """Lines that repeat across most answers of one state, source and year."""
    if len(records) < BOILERPLATE_MIN:
        return set()
    counts = Counter(line.strip() for record in records for line in set(record["a"].splitlines()) if line.strip())
    return {line for line, count in counts.items() if count >= BOILERPLATE_SHARE * len(records)}


def answer_body(record, boilerplate):
    return normalize_text("\n".join(line for line in record["a"].splitlines() if line.strip() not in boilerplate))


def answer_comparison(baseline, current, boilerplate=(set(), set())):
    """An answer is unchanged when its normalized words match; spacing differences come from extraction."""
    old, new = answer_body(baseline, boilerplate[0]), answer_body(current, boilerplate[1])
    if old.replace(" ", "") == new.replace(" ", ""):
        return "unchanged", 1.0
    return "changed", round(similarity(old, new), 3)


def item(status, baseline=None, current=None, question_similarity=None, boilerplate=(set(), set())):
    entry = {"status": status,
             "baseline_q": baseline["q"] if baseline else None, "current_q": current["q"] if current else None,
             "question_similarity": question_similarity,
             "baseline_s": baseline["s"] if baseline else None, "current_s": current["s"] if current else None}
    if baseline and current:
        entry["answer_status"], entry["answer_similarity"] = answer_comparison(baseline, current, boilerplate)
    return entry


def match_questions(baseline, current):
    """Classify each question as same, reworded, new or removed, matching one to one."""
    boilerplate = (boilerplate_lines(baseline), boilerplate_lines(current))
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
            items.append(item("same", record, unmatched_new.pop(index)[1], 1.0, boilerplate))
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
            items.append(item("reworded", unmatched_old[i][1], unmatched_new[j][1], round(score, 3), boilerplate))
    items += [item("removed", baseline=record) for i, (_, record) in enumerate(unmatched_old) if i not in used_old]
    items += [item("new", current=record) for j, (_, record) in enumerate(unmatched_new) if j not in used_new]
    return items


def comparison_unit(setting, baseline_method, current_method):
    """'question' or 'section' for one state's Vote411 records, following settings.toml."""
    if setting != "auto":
        return setting
    return "section" if {baseline_method, current_method} & SECTION_METHODS else "question"


def page_sections(manifest, state):
    """{title: section} from the cycle's saved Vote411 page, or None if the manifest names no saved page."""
    if "vote411_batch" not in manifest:
        return None
    folder = ROOT / manifest["vote411_batch"] / state
    page = folder / f"vote411-{state}.html"
    if not page.is_file():
        return None
    url = json.loads((folder / "source_metadata.json").read_text(encoding="utf-8"))["final_url"]
    soup = BeautifulSoup(page.read_bytes(), "html.parser")
    sections = {}
    for tab in soup.select(".tabs-right > .tab"):
        heading, body = tab.find("h4"), tab.select_one(".tab-body")
        if heading is not None and body is not None:
            sections[source_text([heading], url, include_links=False)] = {"a": source_text([body], url), "s": url}
    return sections


def record_sections(records, rules):
    """Group records into sections with the settings.toml keyword rules; return (sections, unassigned records)."""
    sections, unassigned = {}, []
    for record in records:
        title = assign_vote411_section(record["q"], rules)
        if title is None:
            unassigned.append(record)
            continue
        section = sections.setdefault(title, {"a": "", "s": record["s"]})
        section["a"] = (section["a"] + "\n\n" + record["q"] + "\n" + record["a"]).strip()
    return sections, unassigned


def match_sections(baseline_sections, current_sections, baseline_unassigned, current_unassigned):
    """Classify each Vote411 section as same, new or removed, and list records no section rule matched."""
    old = {title: {"q": title, **section} for title, section in baseline_sections.items()}
    new = {title: {"q": title, **section} for title, section in current_sections.items()}
    boilerplate = (boilerplate_lines(list(old.values())), boilerplate_lines(list(new.values())))
    items = [item("same", old[title], new[title], 1.0, boilerplate) if title in new else item("removed", baseline=old[title])
             for title in old]
    items += [item("new", current=new[title]) for title in new if title not in old]
    items += [item("unassigned", baseline=record) for record in baseline_unassigned]
    items += [item("unassigned", current=record) for record in current_unassigned]
    return items


def vote411_sections(manifest, state, records, rules):
    """Sections from the saved page when the cycle has one, otherwise from its records and the keyword rules."""
    from_page = page_sections(manifest, state)
    return (from_page, []) if from_page is not None else record_sections(records, rules)


def compare(baseline, current, states=None, baseline_manifest=None, current_manifest=None, settings=None):
    """Return ({state: items}, summary rows) for the states present in the current cycle.

    State-site records are compared question by question. Vote411 records are compared question by
    question or by section, as settings.toml's vote411_unit and the two manifests' methods decide.
    """
    baseline_manifest, current_manifest = baseline_manifest or {}, current_manifest or {}
    settings = settings or load_settings()
    rules = vote411_section_rules(settings)
    details, summary = {}, []
    for state in sorted(states or current):
        details[state] = []
        for source in SOURCES:
            old = [record for record in baseline.get(state, []) if record_source(record) == source]
            new = [record for record in current.get(state, []) if record_source(record) == source]
            methods = (vote411_method(baseline_manifest, state), vote411_method(current_manifest, state)) if source == "vote411" else ("", "")
            unit = comparison_unit(settings["comparison"]["vote411_unit"], *methods) if source == "vote411" else "question"
            if unit == "section":
                (old_sections, old_unassigned), (new_sections, new_unassigned) = (
                    vote411_sections(baseline_manifest, state, old, rules), vote411_sections(current_manifest, state, new, rules))
                items = match_sections(old_sections, new_sections, old_unassigned, new_unassigned)
                counted = (len(old_sections), len(new_sections))
            else:
                items = match_questions(old, new)
                counted = (len(old), len(new))
            for entry in items:
                entry["source"], entry["unit"] = source, unit
            details[state] += items
            counts = {status: sum(entry["status"] == status for entry in items)
                      for status in ("same", "reworded", "new", "removed", "unassigned")}
            summary.append({
                "state": state, "source": source, "unit": unit, "baseline_method": methods[0], "current_method": methods[1],
                "baseline_count": counted[0], "current_count": counted[1], **counts,
                "answers_changed": sum(entry.get("answer_status") == "changed" for entry in items),
                "excluded_other_baseline": sum(record_source(record) == "other" for record in baseline.get(state, [])) if source == "state" else 0,
                "excluded_other_current": sum(record_source(record) == "other" for record in current.get(state, [])) if source == "state" else 0,
            })
    return details, summary


def write_comparison(output, details, summary, baseline_year, year, settings=None):
    """Write one detail file per state and a summary CSV under output/comparison/."""
    folder = Path(output) / "comparison"
    units = {(row["state"], row["source"]): row["unit"] for row in summary}
    for state, items in details.items():
        write_json(folder / f"{state}.json", {
            "state": state, "baseline_year": baseline_year, "year": year,
            "reworded_threshold": REWORDED_THRESHOLD,
            "vote411_unit_setting": (settings or load_settings())["comparison"]["vote411_unit"],
            "vote411_unit": units.get((state, "vote411")),
            "note": "Counts are of sections when unit is 'section' and of questions otherwise.",
            "items": items})
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
    settings = load_settings()
    details, summary = compare(baseline, current, None, load_manifest(arguments.baseline_year),
                               load_manifest(arguments.year), settings)
    output = arguments.output or ROOT / "data" / str(arguments.year) / "analysis"
    write_comparison(output, details, summary, arguments.baseline_year, arguments.year, settings)
    totals = {key: sum(row[key] for row in summary) for key in ("same", "reworded", "new", "removed", "answers_changed")}
    print(f"{arguments.baseline_year} to {arguments.year}: {totals}. Output: {Path(output) / 'comparison'}")


if __name__ == "__main__":
    main()
