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
                      normalize_text, record_source, state_name, vote411_method, vote411_section_rules, write_json)


# The thresholds used here (rewording, minor and major edits, boilerplate) live in settings.toml's
# [comparison] table; functions receive that table as `config`.
SUMMARY_FIELDS = ["state", "source", "unit", "unit_basis", "baseline_method", "current_method", "baseline_count", "current_count",
                  "same", "reworded", "new", "removed", "unassigned", "answers_changed", "answers_minor", "answers_major",
                  "excluded_other_baseline", "excluded_other_current"]
# Current-cycle Vote411 methods that include one record per published question heading.
QUESTION_LEVEL_METHODS = {"question_headings", "mixed"}
PAIR_SOURCE_NAMES = {"state": "state site", "vote411": "Vote411"}
ANSWER_KEYS = ("baseline_a", "current_a")
ANSWER_WORDS = {"unchanged": "same", "minor_change": "minor", "major_change": "major"}


def similarity(first, second):
    return SequenceMatcher(None, first, second, autojunk=False).ratio()


def boilerplate_lines(records, config):
    """Lines that repeat across most answers of one state, source and year."""
    if len(records) < config["boilerplate_min_answers"]:
        return set()
    counts = Counter(line.strip() for record in records for line in set(record["a"].splitlines()) if line.strip())
    return {line for line, count in counts.items() if count >= config["boilerplate_share"] * len(records)}


def answer_body(record, boilerplate):
    return normalize_text("\n".join(line for line in record["a"].splitlines() if line.strip() not in boilerplate))


def answer_comparison(baseline, current, boilerplate, config):
    """unchanged when the normalized words match (spacing differences come from extraction); otherwise
    minor_change or major_change, split at config["answer_minor_threshold"]."""
    old, new = answer_body(baseline, boilerplate[0]), answer_body(current, boilerplate[1])
    if old.replace(" ", "") == new.replace(" ", ""):
        return "unchanged", 1.0
    score = round(similarity(old, new), 3)
    return ("minor_change" if score >= config["answer_minor_threshold"] else "major_change"), score


def item(status, baseline=None, current=None, question_similarity=None, boilerplate=(set(), set()), config=None):
    entry = {"status": status,
             "baseline_q": baseline["q"] if baseline else None, "current_q": current["q"] if current else None,
             "question_similarity": question_similarity,
             "baseline_s": baseline["s"] if baseline else None, "current_s": current["s"] if current else None,
             # The answers go to pairs.csv only; write_comparison leaves them out of the per-state JSON files.
             "baseline_a": baseline["a"] if baseline else None, "current_a": current["a"] if current else None}
    if baseline and current:
        entry["answer_status"], entry["answer_similarity"] = answer_comparison(baseline, current, boilerplate, config)
    return entry


def match_questions(baseline, current, config):
    """Classify each question as same, reworded, new or removed, matching one to one."""
    boilerplate = (boilerplate_lines(baseline, config), boilerplate_lines(current, config))
    threshold = config["reworded_threshold"]
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
            items.append(item("same", record, unmatched_new.pop(index)[1], 1.0, boilerplate, config))
    # Pass 2: the most similar remaining pairs, best first, above the threshold.
    candidates = []
    for i, (old_key, _) in enumerate(unmatched_old):
        for j, (new_key, _) in enumerate(unmatched_new):
            matcher = SequenceMatcher(None, old_key, new_key, autojunk=False)
            if matcher.real_quick_ratio() >= threshold and matcher.quick_ratio() >= threshold:
                score = matcher.ratio()
                if score >= threshold:
                    candidates.append((score, i, j))
    used_old, used_new = set(), set()
    for score, i, j in sorted(candidates, reverse=True):
        if i not in used_old and j not in used_new:
            used_old.add(i)
            used_new.add(j)
            items.append(item("reworded", unmatched_old[i][1], unmatched_new[j][1], round(score, 3), boilerplate, config))
    items += [item("removed", baseline=record) for i, (_, record) in enumerate(unmatched_old) if i not in used_old]
    items += [item("new", current=record) for j, (_, record) in enumerate(unmatched_new) if j not in used_new]
    return items


def comparison_unit(config, state, baseline_method, current_method):
    """Return (unit, basis) for one state's Vote411 records: 'question' or 'section', and what decided it.

    Priority: the state's entry in vote411_unit_overrides, then a fixed vote411_unit, then the "auto"
    rule: question by question only when the baseline used question headings and the current cycle
    has question-heading records too.
    """
    override = config.get("vote411_unit_overrides", {}).get(state)
    if override:
        return override, "override in settings.toml"
    if config["vote411_unit"] != "auto":
        return config["vote411_unit"], "vote411_unit in settings.toml"
    by_question = baseline_method == "question_headings" and current_method in QUESTION_LEVEL_METHODS
    return ("question" if by_question else "section"), "auto, from the manifests' methods"


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
    grouped, unassigned = {}, []
    for record in records:
        title = assign_vote411_section(record["q"], rules)
        if title is None:
            unassigned.append(record)
        else:
            grouped.setdefault(title, []).append(record)
    # A section made of one record is a section title rewritten as a question, which was not on the
    # page, so only its answer counts. Several records are questions that were on the page.
    sections = {title: {"a": members[0]["a"] if len(members) == 1
                        else "\n\n".join(r["q"] + "\n" + r["a"] for r in members), "s": members[0]["s"]}
                for title, members in grouped.items()}
    return sections, unassigned


def match_sections(baseline_sections, current_sections, baseline_unassigned, current_unassigned, config):
    """Classify each Vote411 section as same, new or removed, and list records no section rule matched."""
    old = {title: {"q": title, **section} for title, section in baseline_sections.items()}
    new = {title: {"q": title, **section} for title, section in current_sections.items()}
    boilerplate = (boilerplate_lines(list(old.values()), config), boilerplate_lines(list(new.values()), config))
    items = [item("same", old[title], new[title], 1.0, boilerplate, config) if title in new else item("removed", baseline=old[title])
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
    config = settings["comparison"]
    details, summary = {}, []
    for state in sorted(states or current):
        details[state] = []
        for source in SOURCES:
            old = [record for record in baseline.get(state, []) if record_source(record) == source]
            new = [record for record in current.get(state, []) if record_source(record) == source]
            methods = (vote411_method(baseline_manifest, state), vote411_method(current_manifest, state)) if source == "vote411" else ("", "")
            unit, basis = comparison_unit(config, state, *methods) if source == "vote411" else ("question", "")
            if unit == "section":
                (old_sections, old_unassigned), (new_sections, new_unassigned) = (
                    vote411_sections(baseline_manifest, state, old, rules), vote411_sections(current_manifest, state, new, rules))
                items = match_sections(old_sections, new_sections, old_unassigned, new_unassigned, config)
                counted = (len(old_sections), len(new_sections))
            else:
                items = match_questions(old, new, config)
                counted = (len(old), len(new))
            for entry in items:
                entry["source"], entry["unit"] = source, unit
            details[state] += items
            counts = {status: sum(entry["status"] == status for entry in items)
                      for status in ("same", "reworded", "new", "removed", "unassigned")}
            summary.append({
                "state": state, "source": source, "unit": unit, "unit_basis": basis,
                "baseline_method": methods[0], "current_method": methods[1],
                "baseline_count": counted[0], "current_count": counted[1], **counts,
                "answers_changed": sum(entry.get("answer_status") in ("minor_change", "major_change") for entry in items),
                "answers_minor": sum(entry.get("answer_status") == "minor_change" for entry in items),
                "answers_major": sum(entry.get("answer_status") == "major_change" for entry in items),
                "excluded_other_baseline": sum(record_source(record) == "other" for record in baseline.get(state, [])) if source == "state" else 0,
                "excluded_other_current": sum(record_source(record) == "other" for record in current.get(state, [])) if source == "state" else 0,
            })
    return details, summary


def result_label(entry, baseline_year, year):
    """Both statuses in plain words, such as "same question, major answer change" or "new section"."""
    status, unit = entry["status"], entry["unit"]
    if status == "unassigned":
        return f"{baseline_year if entry['baseline_q'] is not None else year} record not matched to any section"
    if status in ("new", "removed"):
        return f"{status} {unit}"
    # A section's answer is the section's text.
    content = "answer" if unit == "question" else "text"
    change = ANSWER_WORDS[entry["answer_status"]]
    return f"{status} {unit}, " + (f"same {content}" if change == "same" else f"{change} {content} change")


def write_pairs(path, details, baseline_year, year):
    """Write every compared question or section of every state to one CSV, sorted by state name, then source.

    This is the file people browse and filter, so it uses full state names and names its columns by
    year. The result column already says the unit and both statuses in words; the separate status
    fields stay in the per-state JSON files.
    """
    old, new = baseline_year, year
    fields = ["state", "source", "result", f"question_{old}", f"question_{new}", f"answer_{old}", f"answer_{new}",
              "question_similarity", "answer_similarity", f"url_{old}", f"url_{new}"]
    with open(path, "w", newline="", encoding="utf-8-sig") as file:  # the byte order mark lets Excel read it as UTF-8
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for state in sorted(details, key=state_name):
            for source in SOURCES:
                for entry in details[state]:
                    if entry["source"] == source:
                        writer.writerow({
                            "state": state_name(state), "source": PAIR_SOURCE_NAMES[source],
                            "result": result_label(entry, baseline_year, year),
                            f"question_{old}": entry["baseline_q"], f"question_{new}": entry["current_q"],
                            f"answer_{old}": entry["baseline_a"], f"answer_{new}": entry["current_a"],
                            "question_similarity": entry["question_similarity"],
                            "answer_similarity": entry.get("answer_similarity", ""),
                            f"url_{old}": entry["baseline_s"], f"url_{new}": entry["current_s"]})


def bold(text):
    """Bold text for the table page, which resets the browser's own bold style."""
    return f'<b style="font-weight:700">{text}</b>'


def write_pairs_metadata(path, baseline_year, year, repository):
    """Write the title and the how-to steps that Datasette Lite shows above the pairs.csv table.

    The file is written on every run so that its years, and the example column in the search step,
    are the run's own. The link printed by run_pipeline.py loads it from the same folder as pairs.csv.
    """
    steps = [
        f"To see only one result, like <i>new question</i>, click it in the {bold('result')} box below.",
        f"To see one state, choose {bold('state')} in the {bold('- column -')} menu, type its full name in the box "
        f"next to it (like <i>Oregon</i>), and click {bold('Apply filters')}.",
        f"To search for a word, choose a column like {bold(f'question_{year}')}, change {bold('=')} to "
        f"{bold('contains')}, type the word, and click {bold('Apply filters')}.",
        f"To read a row's full answers, click its number in the {bold('Link')} column.",
    ]
    content = {
        "title": f"U.S. Voter FAQs: {baseline_year} and {year}",
        "description": f"This database puts every {baseline_year} voter FAQ question next to its {year} version.",
        "source": f"github.com/{repository}",
        "source_url": f"https://github.com/{repository}",
        "databases": {"data": {"tables": {"pairs": {
            "title": f"Voter FAQ questions, {baseline_year} vs {year}",
            "description_html": f"<p>{bold('How to use it')}</p>"
                                '<ul style="list-style:disc;padding-left:1.4em;margin:0.3em 0 0.6em">'
                                + "".join(f"<li>{step}</li>" for step in steps) + "</ul>"}}}}}
    # Always written with plain line endings, so the file is the same on Windows, macOS and Linux
    # and git shows no change when the years are the same.
    path.write_text(json.dumps(content, indent=4, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def pairs_table_link(output, baseline_year, year, github):
    """The Datasette Lite address that opens output/comparison/pairs.csv as a table in the browser.

    Datasette Lite reads the file from GitHub, so the address is built from the repository and branch
    in settings.toml's [github] table, and it shows the copy that was last pushed. The part after #
    picks the columns shown first and the two boxes of clickable values (result and source).
    """
    folder = (Path(output) / "comparison").resolve().relative_to(ROOT).as_posix()
    repository, branch = github["repository"], github["branch"]
    return (f"https://lite.datasette.io/?csv=https://github.com/{repository}/blob/{branch}/{folder}/pairs.csv"
            f"&metadata=https://raw.githubusercontent.com/{repository}/{branch}/{folder}/pairs_metadata.json"
            f"#/data/pairs?_col=state&_col=source&_col=result&_col=question_{baseline_year}&_col=question_{year}"
            "&_facet=result&_facet=source&_size=20")


def write_comparison(output, details, summary, baseline_year, year, settings=None):
    """Write one detail file per state, a summary CSV, pairs.csv and its table page text under output/comparison/."""
    folder = Path(output) / "comparison"
    units = {(row["state"], row["source"]): row["unit"] for row in summary}
    bases = {(row["state"], row["source"]): row["unit_basis"] for row in summary}
    settings = settings or load_settings()
    config = settings["comparison"]
    for state, items in details.items():
        write_json(folder / f"{state}.json", {
            "state": state, "baseline_year": baseline_year, "year": year,
            "reworded_threshold": config["reworded_threshold"],
            "answer_minor_threshold": config["answer_minor_threshold"],
            "vote411_unit_setting": config["vote411_unit"],
            "vote411_unit": units.get((state, "vote411")),
            "vote411_unit_basis": bases.get((state, "vote411")),
            "note": "Counts are of sections when unit is 'section' and of questions otherwise.",
            "items": [{key: value for key, value in entry.items() if key not in ANSWER_KEYS} for entry in items]})
    with open(folder / "summary.csv", "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary)
    write_pairs(folder / "pairs.csv", details, baseline_year, year)
    write_pairs_metadata(folder / "pairs_metadata.json", baseline_year, year, settings["github"]["repository"])


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
    totals = {key: sum(row[key] for row in summary)
              for key in ("same", "reworded", "new", "removed", "answers_minor", "answers_major")}
    print(f"{arguments.baseline_year} to {arguments.year}: {totals}. Output: {Path(output) / 'comparison'}")


if __name__ == "__main__":
    main()
