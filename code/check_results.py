"""Cross-check a cycle's published results: recount them a second way, and set up a spot check for a person.

The recount works the published numbers out again from the dataset files, comparison/pairs.csv,
topics.csv and settings.toml, using the documented definitions. It does not import compare_years.py
or analyze_states.py, so a mistake in the code that produced the numbers is not repeated here.
It writes check/check_results.md and check/spot_check.csv inside the analysis folder.
"""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import random
import statistics
from urllib.parse import urlparse

from collect_sc import ROOT
from datasets import NON_STATE_HOSTS, dataset_dir, load_dataset, load_settings, state_name


# The same seed on every run, so the five states and the spot-check rows do not change between runs.
SEED = 498
STATES_TO_READ_OFF = 5
SPOT_ROWS_PER_RESULT = 2
# One source as per_state.csv names its columns, as pairs.csv names it, and as the report names it.
SOURCES = (("state_site", "state site", "state election site"), ("vote411", "Vote411", "Vote411"))
COUNTS = ("same", "reworded", "new", "removed", "answers_minor", "answers_major", "compared_baseline", "compared_current")
# The columns of spot_check.csv a person fills in.
PERSON_FIELDS = ("agree", "checked_by", "date", "notes")


def read_csv(path):
    # utf-8-sig also reads files without a byte order mark, and files a person saved from Excel.
    with open(path, newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def record_source(record):
    """Which source a dataset record belongs to, from its s field: "vote411", "state_site" or None.

    Written here from the documented rule, not taken from the analysis code: an address or site
    name with 411 in it is Vote411, a page on one of the county or nonprofit hosts listed in
    datasets.py belongs to neither source, and any other address is the state election site.
    """
    address = str(record.get("s", "")).strip().lower()
    if "411" in address:
        return "vote411"
    if not address:
        return None
    host = (urlparse(address if "://" in address else "https://" + address).hostname or "").removeprefix("www.")
    return None if host in NON_STATE_HOSTS else "state_site"


def tally(results):
    """Count one state and source's pairs.csv rows by what their result column says.

    The documented definition: a major change is a new or removed question or section, or a
    matched one with a major answer or text change. Unchanged is "same question, same answer" or
    "same section, same text". Every other counted row is a minor edit, which includes a reworded
    question with the same answer. A record not matched to any section is not counted at all.
    Oregon's state site has 21 counted rows: 5 major and 3 minor.
    """
    counts = Counter()
    for result in results:
        if result.endswith("record not matched to any section"):
            continue
        counts["total"] += 1
        if result.startswith(("new ", "removed ")):
            counts[result.split()[0]] += 1
            counts["major"] += 1
            continue
        match, change = result.split(", ")
        counts[match.split()[0]] += 1          # "same" or "reworded"
        if change.startswith("major "):
            counts["answers_major"] += 1
            counts["major"] += 1
        elif change.startswith("minor "):
            counts["answers_minor"] += 1
            counts["minor"] += 1
        elif not (match.startswith("same ") and change.startswith("same ")):
            counts["minor"] += 1               # reworded, with the same answer
    counts["compared_baseline"] = counts["same"] + counts["reworded"] + counts["removed"]
    counts["compared_current"] = counts["same"] + counts["reworded"] + counts["new"]
    return counts


def rates(counts):
    """(minor, major, total) change rates to three decimals, or None for each when nothing was counted."""
    total = counts["total"]
    if not total:
        return None, None, None
    return round(counts["minor"] / total, 3), round(counts["major"] / total, 3), round((counts["minor"] + counts["major"]) / total, 3)


def left_out_reason(baseline_count, current_count, limits, baseline_year, year):
    """Why a state gets no change rate for a source, in words, or "" when it gets one.

    Written from the rule in settings.toml's [quality] comments: nothing in one of the two years,
    or a count under below_baseline_ratio or over above_baseline_ratio times the baseline year's.
    """
    if not baseline_count and not current_count:
        return "none in either year"
    if not baseline_count:
        return f"none in {baseline_year} to compare with"
    if not current_count:
        return f"none collected in {year}"
    if current_count < limits["below_baseline_ratio"] * baseline_count:
        return f"fewer than {limits['below_baseline_ratio']:g} times the {baseline_year} count"
    if current_count > limits["above_baseline_ratio"] * baseline_count:
        return f"more than {limits['above_baseline_ratio']:g} times the {baseline_year} count"
    return ""


def number(text):
    """A published cell as a number, or None when it is blank."""
    return None if text == "" else float(text) if "." in text else int(text)


def percent(share):
    """A share as a whole percent with halves rounded up, as the chart titles print it."""
    return f"{int(100 * share + 0.5)}%"


class Recount:
    """Collects every comparison of a recounted number with the published one."""

    def __init__(self):
        self.checked, self.mismatches = 0, []

    def compare(self, what, recounted, published):
        self.checked += 1
        if recounted != published:
            self.mismatches.append(f"{what}: recount {recounted}, published {published}")


def recount(year, baseline_year, output):
    """Recount the published numbers; return the Recount and the facts the report prints."""
    settings = load_settings()
    limits, topic_count = settings["quality"], len(settings["topics"])
    per_state = read_csv(output / "per_state.csv")
    pairs = read_csv(output / "comparison" / "pairs.csv")
    topics = read_csv(output / "topics.csv")
    datasets = {baseline_year: load_dataset(dataset_dir(baseline_year)), year: load_dataset(dataset_dir(year))}
    check, facts = Recount(), {"left_out": [], "states": {}, "pairs_rows": len(pairs)}

    # g. Every state appears once.
    codes = [row["state"] for row in per_state]
    check.compare("states listed more than once in per_state.csv", len(codes) - len(set(codes)), 0)

    # a. Records per year and source, from the dataset files.
    facts["records"] = {}
    for cycle, kind in ((baseline_year, "baseline"), (year, "current")):
        totals = Counter()
        for row in per_state:
            found = Counter(record_source(record) for record in datasets[cycle].get(row["state"], []))
            for column, _, name in SOURCES:
                check.compare(f"{state_name(row['state'])}, {name}, records in {cycle}", found[column], number(row[f"{kind}_{column}"]))
            totals.update(found)
        facts["records"][cycle] = totals

    # b. Counts and rates from the result column of pairs.csv.  c. Who should have no rate.  g. A rate or a note.
    results = {}
    for row in pairs:
        results.setdefault((row["state"], row["source"]), []).append(row["result"])
    major_rates = {column: {"recount": [], "published": []} for column, _, _ in SOURCES}
    for row in per_state:
        name = state_name(row["state"])
        for column, pairs_name, source_name in SOURCES:
            where = f"{name}, {source_name}"
            counts = tally(results.get((name, pairs_name), []))
            for key in COUNTS:
                check.compare(f"{where}, {key.replace('_', ' ')}", counts[key], number(row[f"{key}_{column}"]))
            published = [number(row[f"{key}_{column}"]) for key in ("minor_edit_rate", "major_change_rate", "change_rate")]
            note = row[f"change_rate_note_{column}"]
            reason = left_out_reason(number(row[f"compared_baseline_{column}"]), number(row[f"compared_current_{column}"]),
                                     limits, baseline_year, year)
            check.compare(f"{where}, left out of the change chart", "yes" if reason else "no", "yes" if note else "no")
            check.compare(f"{where}, has a rate or a note but not both",
                          "yes", "yes" if all(value is None for value in published) == bool(note) else "no")
            recounted = rates(counts)
            if not reason:
                major_rates[column]["recount"].append(recounted[1])
            if published[1] is not None:
                major_rates[column]["published"].append(published[1])
                for label, mine, theirs in zip(("minor edit rate", "major change rate", "change rate"), recounted, published):
                    check.compare(f"{where}, {label}", mine, theirs)
            if reason:
                facts["left_out"].append((source_name, reason, name))
            facts["states"][(row["state"], column)] = {"counts": counts, "reason": reason, "where": where}

    # d. The median major change rate and how many states it covers. The chart titles print these.
    facts["medians"] = {}
    for column, _, source_name in SOURCES:
        mine, theirs = major_rates[column]["recount"], major_rates[column]["published"]
        check.compare(f"{source_name}, states with a rate", len(mine), len(theirs))
        check.compare(f"{source_name}, median major change rate", statistics.median(mine) if mine else None,
                      statistics.median(theirs) if theirs else None)
        facts["medians"][source_name] = (statistics.median(mine) if mine else None, len(mine))

    # e. Topics covered, from topics.csv.
    covered = Counter((row["state"], row["year"]) for row in topics if int(row["questions"]) > 0)
    facts["topics"] = {}
    for cycle, kind in ((baseline_year, "baseline"), (year, "current")):
        for row in per_state:
            check.compare(f"{state_name(row['state'])}, topics covered in {cycle}", covered[(row["state"], str(cycle))],
                          number(row[f"topics_covered_{kind}"]))
        all_topics = sum(covered[(row["state"], str(cycle))] == topic_count for row in per_state)
        check.compare(f"states covering all {topic_count} topics in {cycle}", all_topics,
                      sum(number(row[f"topics_covered_{kind}"]) == topic_count for row in per_state))
        facts["topics"][cycle] = (all_topics, len(per_state), topic_count)

    # f. Rows in pairs.csv against the items in the per-state comparison files.
    rows_by_state, items_total = Counter(row["state"] for row in pairs), 0
    for row in per_state:
        items = len(json.loads((output / "comparison" / f"{row['state']}.json").read_text(encoding="utf-8"))["items"])
        items_total += items
        check.compare(f"{state_name(row['state'])}, rows in pairs.csv", rows_by_state[state_name(row["state"])], items)
    check.compare("rows in pairs.csv", len(pairs), items_total)
    facts["codes"] = codes
    return check, facts, pairs


def write_spot_check(path, pairs, baseline_year, year):
    """Create or extend check/spot_check.csv; return what the report says about it.

    Two rows of pairs.csv are picked for each source and result that occurs. A person opens the
    pages of each row and writes yes or no in the agree column. A row a person has written
    anything in is kept exactly as it is, the way review.csv keeps its rows.
    """
    kept = ["state", "source", "result", f"question_{baseline_year}", f"question_{year}", f"url_{baseline_year}",
            f"url_{year}", "question_similarity", "answer_similarity"]
    fields = kept + list(PERSON_FIELDS)

    def key(row):
        return tuple(row[field] for field in kept)

    groups = {}
    for row in pairs:
        groups.setdefault((row["source"], row["result"]), []).append(row)
    sample = []
    for group in sorted(groups):
        rows = groups[group]
        # Each source and result has its own seed, so a change in one group does not move the others' rows.
        picked = random.Random(f"{SEED}|{group[0]}|{group[1]}").sample(range(len(rows)), min(SPOT_ROWS_PER_RESULT, len(rows)))
        sample += [{field: rows[index][field] for field in kept} | dict.fromkeys(PERSON_FIELDS, "") for index in sorted(picked)]
    existing = []
    if path.is_file():
        with open(path, newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames != fields:
                raise SystemExit(f"{path} has other columns than this run expects ({', '.join(fields)}). "
                                 "Move the file away to keep what was filled in, then run again.")
            existing = list(reader)
    filled = {key(row): row for row in existing if any(row[field].strip() for field in PERSON_FIELDS)}
    sampled = {key(row) for row in sample}
    rows = [filled.get(key(row), row) for row in sample] + [row for row in filled.values() if key(row) not in sampled]
    if rows != existing:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8-sig") as file:  # the byte order mark lets Excel read it as UTF-8
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    answers = Counter(row["agree"].strip().lower() for row in rows if row["agree"].strip())
    in_pairs = {key(row) for row in pairs}
    return {"rows": len(rows), "filled": sum(answers.values()), "yes": answers["yes"], "no": answers["no"],
            "gone": sum(key(row) not in in_pairs for row in filled.values())}


def not_matching(count):
    """Such as "1 does not match" or "3 do not match"."""
    return f"{count:,} {'does' if count == 1 else 'do'} not match"


def report_lines(check, facts, spot, year, baseline_year):
    matching = check.checked - len(check.mismatches)
    summary = (f"{check.checked:,} numbers recounted, all match." if not check.mismatches else
               f"{check.checked:,} numbers recounted: {matching:,} match and {not_matching(len(check.mismatches))}.")
    lines = [f"# Cross-check of the {year} results", "", summary, "",
             "Written by `code/check_results.py`. It works the published numbers out a second time from the dataset files, "
             "`comparison/pairs.csv`, `topics.csv` and `settings.toml`, without the code that produced them, and compares "
             "them with `per_state.csv` and the per-state comparison files.", "", "## Mismatches", ""]
    lines += [f"- {line}" for line in check.mismatches] or ["None."]
    lines += ["", "## Numbers to compare with the README and the chart titles", "",
              f"| Records | {baseline_year} | {year} |", "| --- | --- | --- |"]
    old, new = facts["records"][baseline_year], facts["records"][year]
    for column, label in (("state_site", "State election sites"), ("vote411", "Vote411"), (None, "Other pages, not compared")):
        if column or old[None] or new[None]:
            lines.append(f"| {label} | {old[column]:,} | {new[column]:,} |")
    lines += [f"| All | {sum(old.values()):,} | {sum(new.values()):,} |", ""]
    for source_name, (median, states) in facts["medians"].items():
        lines.append(f"- Median major change, {source_name}: " + (f"{percent(median)} over {states} states" if states else "no state has a rate"))
    for cycle, (covering, states, topic_count) in facts["topics"].items():
        lines.append(f"- States with a question on all {topic_count} topics in {cycle}: {covering} of {states}")
    lines.append(f"- Rows in pairs.csv: {facts['pairs_rows']:,}")
    lines += ["", "States the change chart leaves out, and why:", ""]
    groups = {}
    for source_name, reason, name in facts["left_out"]:
        groups.setdefault((source_name, reason), []).append(name)
    # Listed by source, state election sites first, then by reason.
    order = [source_name for _, _, source_name in SOURCES]
    lines += [f"- {source_name[0].upper() + source_name[1:]}, {reason}: {', '.join(sorted(groups[(source_name, reason)]))}"
              for source_name, reason in sorted(groups, key=lambda group: (order.index(group[0]), group[1]))] or ["- None."]
    lines += ["", "## Five states to read off the change chart", "",
              "Picked with a fixed seed, so they are the same on every run. Find each state's bar on "
              "`charts/change_rate_by_state.png` and see that it matches.", ""]
    chosen = random.Random(SEED).sample(sorted(facts["codes"]), min(STATES_TO_READ_OFF, len(facts["codes"])))
    for code in sorted(chosen, key=state_name):
        for column, _, _ in SOURCES:
            state = facts["states"][(code, column)]
            counts = state["counts"]
            lines.append(f"- {state['where']}: " + (f"left out ({state['reason']})" if state["reason"] else
                         f"{counts['major']} of {counts['total']} major ({percent(counts['major'] / counts['total'])}), "
                         f"{counts['minor']} of {counts['total']} minor ({percent(counts['minor'] / counts['total'])})"))
    lines += ["", "## Spot check by a person", "",
              f"`spot_check.csv` holds {spot['rows']} rows of `pairs.csv`, {SPOT_ROWS_PER_RESULT} for each source and result that occurs. "
              "Open the two addresses of a row, see whether the result is right, and write yes or no in the agree column, "
              "with your name and the date. A row that is filled in is never changed by a later run.", "",
              f"- Filled in: {spot['filled']} of {spot['rows']}",
              f"- Say yes: {spot['yes']}", f"- Say no: {spot['no']}"]
    if spot["filled"] - spot["yes"] - spot["no"]:
        lines.append(f"- Neither yes nor no: {spot['filled'] - spot['yes'] - spot['no']}")
    if spot["gone"]:
        lines.append(f"- Filled-in rows that are no longer in pairs.csv: {spot['gone']}")
    return lines


def check_results(year, baseline_year, output):
    """Recount, write the report and the spot-check file; return (numbers recounted, mismatches)."""
    output = Path(output)
    check, facts, pairs = recount(year, baseline_year, output)
    folder = output / "check"
    folder.mkdir(parents=True, exist_ok=True)
    spot = write_spot_check(folder / "spot_check.csv", pairs, baseline_year, year)
    (folder / "check_results.md").write_text("\n".join(report_lines(check, facts, spot, year, baseline_year)) + "\n", encoding="utf-8")
    return check.checked, check.mismatches


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, required=True, help="Collection cycle, for example 2026")
    parser.add_argument("--baseline-year", type=int, default=2024, help="Cycle it was compared against")
    parser.add_argument("--output", type=Path, help="Analysis folder to check. Default: data/<year>/analysis")
    arguments = parser.parse_args()
    output = (arguments.output or ROOT / "data" / str(arguments.year) / "analysis").resolve()
    checked, mismatches = check_results(arguments.year, arguments.baseline_year, output)
    if mismatches:
        print(f"Cross-check: {checked:,} numbers recounted, {not_matching(len(mismatches))}:")
        print("\n".join("  " + line for line in mismatches))
        raise SystemExit(f"Do not share these outputs. Report: {output / 'check' / 'check_results.md'}")
    print(f"Cross-check: {checked:,} numbers recounted, all match. Report: {output / 'check' / 'check_results.md'}")


if __name__ == "__main__":
    main()
