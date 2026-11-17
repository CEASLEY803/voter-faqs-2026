"""Cross-state analysis: counts, change rates, topic coverage, rankings and charts."""

import argparse
import csv
from collections import Counter
from pathlib import Path
import statistics
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

from collect_sc import ROOT
from compare_years import compare, count_word, write_comparison
from datasets import (SOURCES, above_baseline, below_baseline, dataset_dir, load_dataset, load_manifest, load_settings, question_topics,
                      record_source, state_name, topic_rules)


SOURCE_LABELS = {"state_site": "State election site", "vote411": "Vote411"}
# Reference palette: categorical slots 1 and 2, text and surface tokens.
COLORS = {"baseline": "#2a78d6", "current": "#eb6834", "major": "#2a78d6", "minor": "#86b6ef",
          "text": "#0b0b0b", "muted": "#52514e", "grid": "#e4e3df", "surface": "#fcfcfb", "empty": "#ffffff"}
# Topic chart: the lowest question count of each color step, its legend label and its color. The
# colors are one blue ramp, checked as an ordinal palette, whose lightest step is still clearly
# visible, so a square with one question never looks like an empty one.
TOPIC_STEPS = [(1, "1 question", "#86b6ef"), (2, "2 to 4", "#3987e5"), (5, "5 to 9", "#184f95"), (10, "10 or more", "#0d366b")]
# How each Vote411 extraction method (see VOTE411_METHODS in datasets.py) is described on a chart.
METHOD_WORDS = {"question_headings": "one record per question", "section_titles": "one record per section",
                "sections_without_questions": "one record per section", "mixed": "sections split into questions",
                "page_fragments": "records are page fragments"}
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
# GitHub shows a chart about 850 pixels wide, whatever its real size. Every chart is drawn 8.5 by 8
# inches, so a hundredth of an inch is one pixel on that page. The chart code below is written in
# those page pixels: positions are measured from the top left corner, and no text is under 10.
PAGE_WIDTH, PAGE_HEIGHT = 850, 800
SAVE_DPI = 200
SMALL, BODY, PANEL_TITLE, TITLE = 10, 10.5, 11.5, 14.5
# The two side by side panels of a chart: left edge of each, and their width.
PANEL_LEFTS, PANEL_WIDTH = (38, 464), 366


def topic_counts(records, topics):
    """Questions per topic. Only the question is checked, because answers mention many topics in passing."""
    counts = {topic["name"]: 0 for topic in topics}
    for record in records:
        for name in question_topics(record["q"], topics):
            counts[name] += 1
    return counts


def change_rates(items):
    """Split one state and source's compared units (questions or sections) into unchanged, minor and major.

    minor: a matched pair whose answer has only a minor edit, or whose question was reworded while the
           answer is unchanged or has a minor edit.
    major: a matched pair whose answer has a major edit, plus every new and removed unit.
    Returns (minor_edit_rate, major_change_rate, change_rate); change_rate is their sum.
    """
    counted = [item for item in items if item["status"] in ("same", "reworded", "new", "removed")]
    if not counted:
        return None, None, None
    major = sum(item["status"] in ("new", "removed") or item.get("answer_status") == "major_change" for item in counted)
    unchanged = sum(item["status"] == "same" and item.get("answer_status") == "unchanged" for item in counted)
    minor = len(counted) - major - unchanged
    return round(minor / len(counted), 3), round(major / len(counted), 3), round((minor + major) / len(counted), 3)


def rank(rows, key, reverse=True):
    """Dense 1-based ranks; states with no value are left unranked."""
    values = sorted({row[key] for row in rows if row[key] is not None}, reverse=reverse)
    return {row["state"]: (values.index(row[key]) + 1 if row[key] is not None else None) for row in rows}


# Why a state's change rates are left out for a source, in the order the end-of-run warning lists them.
LEFT_OUT_REASONS = ("none_collected", "under", "over", "none_in_baseline", "none_in_either")


def left_out_reason(baseline_count, current_count, limits):
    """One of LEFT_OUT_REASONS, or "" when the two years' records for a source can be compared.

    The counts are the counts actually compared (the compared_ columns of per_state.csv), so both
    years are counted in the same unit.

    With no records in one year, every question in the other year would count as new or removed.
    With far fewer records than the baseline year, most "removed" questions are questions the
    collection missed. With far more, most "new" questions come from pages the baseline year did
    not include. All of these measure the collection, not the state. limits is settings.toml's
    [quality] table.
    """
    if not baseline_count and not current_count:
        return "none_in_either"
    if not baseline_count:
        return "none_in_baseline"
    if not current_count:
        return "none_collected"
    if below_baseline(current_count, baseline_count, limits["below_baseline_ratio"]):
        return "under"
    return "over" if above_baseline(current_count, baseline_count, limits["above_baseline_ratio"]) else ""


def missing_year_words(baseline_year, year):
    """The three missing-year reasons in words. They say what the collection has, so "none collected
    in 2026" is not read as "this state has no FAQ page"."""
    return {"none_collected": f"none collected in {year}",
            "none_in_baseline": f"none in {baseline_year} to compare with",
            "none_in_either": "none in either year"}


def reason_words(reason, baseline_year, year, limits):
    """A left-out reason in words, such as "none collected in 2026" or "under half as many as 2024"."""
    under, over = limits["below_baseline_ratio"], limits["above_baseline_ratio"]
    return {**missing_year_words(baseline_year, year),
            "under": f"under {'half' if under == 0.5 else f'{under:.0%}'} as many as {baseline_year}",
            "over": f"over {'twice' if over == 2 else f'{over:g} times'} as many as {baseline_year}"}[reason]


def missing_year_note(baseline_count, current_count, baseline_year, year):
    """Which year has no records for a source, such as "none collected in 2026", or "" when both years have some."""
    words = missing_year_words(baseline_year, year)
    if not baseline_count and not current_count:
        return words["none_in_either"]
    if not baseline_count:
        return words["none_in_baseline"]
    return words["none_collected"] if not current_count else ""


def no_rate_note(baseline_count, current_count, baseline_year, year, limits, counted="records"):
    """Why a state's change rates are left blank for a source, or "" when the two years can be compared.

    A missing year gets the missing-year note. A count under or over the limits gets both counts,
    such as "13 records in 2026, 79 in 2024" or "23 sections in 2026, 2 in 2024". counted names
    what the two counts are counts of.
    """
    reason = left_out_reason(baseline_count, current_count, limits)
    if reason in ("under", "over"):
        return f"{current_count} {counted} in {year}, {baseline_count} in {baseline_year}"
    return missing_year_note(baseline_count, current_count, baseline_year, year) if reason else ""


def left_out_warning(rows, baseline_year, year, limits):
    """Lines that name every state the change charts leave out, grouped by source and reason; [] when none is.

    A state is listed when its change_rate_note for the source is not empty, which is exactly when
    the change chart shows a note in place of its bar.
    """
    lines = []
    for source in SOURCES:
        label = "state_site" if source == "state" else "vote411"
        plural = {"state_site": "State election sites", "vote411": "Vote411"}[label]
        groups = {}
        for row in rows:
            if row[f"change_rate_note_{label}"]:
                reason = left_out_reason(row[f"compared_baseline_{label}"], row[f"compared_current_{label}"], limits)
                groups.setdefault(reason, []).append(state_name(row["state"]))
        lines += [f"  {plural}, {reason_words(reason, baseline_year, year, limits)}: {', '.join(sorted(groups[reason]))}"
                  for reason in LEFT_OUT_REASONS if reason in groups]
    return ["Warning: the change charts leave these out.", *lines] if lines else []


def per_state_table(baseline, current, details, summary, states, baseline_year, year, topics, limits):
    by_key = {(row["state"], row["source"]): row for row in summary}
    rows = []
    for state in states:
        row = {"state": state}
        vote411_row = by_key[(state, "vote411")]
        row["vote411_unit"], row["vote411_unit_basis"] = vote411_row["unit"], vote411_row["unit_basis"]
        row["vote411_method_baseline"], row["vote411_method_current"] = vote411_row["baseline_method"], vote411_row["current_method"]
        for source in SOURCES:
            stats = by_key[(state, source)]
            label = "state_site" if source == "state" else "vote411"
            # Record counts are always questions; compared counts are sections when the unit is "section".
            row[f"baseline_{label}"] = sum(record_source(r) == source for r in baseline.get(state, []))
            row[f"current_{label}"] = sum(record_source(r) == source for r in current.get(state, []))
            row[f"compared_baseline_{label}"] = stats["baseline_count"]
            row[f"compared_current_{label}"] = stats["current_count"]
            for status in ("same", "reworded", "new", "removed"):
                row[f"{status}_{label}"] = stats[status]
            row[f"answers_minor_{label}"] = stats["answers_minor"]
            row[f"answers_major_{label}"] = stats["answers_major"]
            # The compared counts are used, so a Vote411 state compared by section is judged by its sections.
            note = no_rate_note(stats["baseline_count"], stats["current_count"], baseline_year, year, limits,
                                count_word(source, stats["unit"]))
            (row[f"minor_edit_rate_{label}"], row[f"major_change_rate_{label}"], row[f"change_rate_{label}"]) = (
                (None, None, None) if note else change_rates([item for item in details[state] if item["source"] == source]))
            row[f"change_rate_note_{label}"] = note
            similarities = [item["answer_similarity"] for item in details[state]
                            if item["source"] == source and "answer_similarity" in item]
            row[f"mean_answer_similarity_{label}"] = round(sum(similarities) / len(similarities), 3) if similarities else None
        for year_key, dataset in (("baseline", baseline), ("current", current)):
            counts = topic_counts([r for r in dataset.get(state, []) if record_source(r) in SOURCES], topics)
            row[f"topics_covered_{year_key}"] = sum(1 for count in counts.values() if count)
            row[f"topic_questions_{year_key}"] = sum(counts.values())
            for topic, count in counts.items():
                row[f"{topic}_{year_key}"] = count
        rows.append(row)
    coverage_order = sorted(rows, key=lambda r: (-r["topics_covered_current"], -r["topic_questions_current"], r["state"]))
    for position, row in enumerate(coverage_order, start=1):
        row["coverage_rank"] = position
    for label in ("state_site", "vote411"):
        ranks = rank(rows, f"major_change_rate_{label}")
        for row in rows:
            row[f"major_change_rank_{label}"] = ranks[row["state"]]
    return rows


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def points(pixels):
    """Page pixels to the points matplotlib uses for text and line sizes."""
    return pixels * 72 / 100


def percent(share):
    """A share as a whole percent, with halves rounded up."""
    return f"{int(100 * share + 0.5)}%"


def new_figure():
    return plt.figure(figsize=(PAGE_WIDTH / 100, PAGE_HEIGHT / 100), facecolor=COLORS["surface"])


def write(figure, left, top, text, size=BODY, color="muted", **style):
    """Put text on the page, with its top left corner at (left, top) in page pixels."""
    figure.text(left / PAGE_WIDTH, 1 - top / PAGE_HEIGHT, text, fontsize=points(size), color=COLORS[color],
                va="top", ha="left", **style)


def add_legend(figure, top, handles):
    figure.legend(handles=handles, frameon=False, fontsize=points(BODY), labelcolor=COLORS["text"], loc="upper left",
                  bbox_to_anchor=(6 / PAGE_WIDTH, 1 - top / PAGE_HEIGHT), ncols=len(handles), borderaxespad=0,
                  handlelength=1.4, handletextpad=0.5, columnspacing=1.6)


def add_panel(figure, left, top, height, states):
    """One panel, placed in page pixels, with one row per state code, the first at the top."""
    axis = figure.add_axes([left / PAGE_WIDTH, 1 - (top + height) / PAGE_HEIGHT, PANEL_WIDTH / PAGE_WIDTH, height / PAGE_HEIGHT])
    axis.set_facecolor(COLORS["surface"])
    for spine in axis.spines.values():
        spine.set_visible(False)
    axis.set_yticks(range(len(states)), [state.upper() for state in states])
    axis.set_ylim(len(states) - 0.5, -0.5)
    axis.tick_params(axis="y", colors=COLORS["muted"], labelsize=points(SMALL), length=0, pad=points(4))
    axis.tick_params(axis="x", colors=COLORS["muted"], labelsize=points(SMALL), length=0, pad=points(3))
    return axis


def bar_panel(figure, left, top, height, states):
    axis = add_panel(figure, left, top, height, states)
    axis.spines["bottom"].set_visible(True)
    axis.spines["bottom"].set_color(COLORS["grid"])
    axis.grid(axis="x", color=COLORS["grid"], linewidth=points(1))
    axis.set_axisbelow(True)
    return axis


def row_note(axis, x, row, text, italic=True):
    """Words in place of a bar. Reasons for a missing bar are in italics; "no change" is not."""
    axis.text(x, row, text, va="center", ha="left", fontsize=points(SMALL), color=COLORS["muted"],
              style="italic" if italic else "normal")


def save(figure, path):
    figure.savefig(path, dpi=SAVE_DPI, facecolor=COLORS["surface"])
    plt.close(figure)


def vote411_build_note(rows, baseline_year, year):
    """Title and two lines for the Vote411 panel of the counts chart, from the methods in the manifests.

    When the most common extraction method differs between the two cycles, the record counts are not
    like for like, and the panel says how each cycle was mostly built.
    """
    lines = []
    for key, cycle in (("baseline", baseline_year), ("current", year)):
        methods = Counter(r[f"vote411_method_{key}"] for r in rows if r[f"vote411_method_{key}"] != "none")
        method, states = methods.most_common(1)[0] if methods else ("none", 0)
        lines.append((method, f"{cycle}: {METHOD_WORDS.get(method, method)} in {states} of {sum(methods.values())} states"))
    if lines[0][0] == lines[1][0]:
        return "Vote411", ["Records per state"]
    return "Vote411: the two years are not like for like", [line for _, line in lines]


def chart_counts(rows, path, baseline_year, year):
    """Records per state in both years, one panel per source so each keeps its own scale."""
    order = sorted(rows, key=lambda r: (-(r["current_state_site"] + r["current_vote411"]), r["state"]))
    figure = new_figure()
    write(figure, 8, 8, f"Voter FAQ records collected per state, {baseline_year} and {year}", TITLE, "text", fontweight="bold")
    write(figure, 8, 32, f"States are sorted by their {year} records from both sources together, most at the top.")
    add_legend(figure, 51, [Patch(color=COLORS["baseline"], label=str(baseline_year)), Patch(color=COLORS["current"], label=str(year))])
    vote411_title, vote411_lines = vote411_build_note(rows, baseline_year, year)
    headings = {"state_site": (SOURCE_LABELS["state_site"], ["Questions per state"]), "vote411": (vote411_title, vote411_lines)}
    top = 96 + 15 * max(len(lines) for _, lines in headings.values())
    for left, label in zip(PANEL_LEFTS, ("state_site", "vote411")):
        title, lines = headings[label]
        write(figure, left, 76, title, PANEL_TITLE, "text", fontweight="bold")
        for number, line in enumerate(lines):
            write(figure, left, 93 + 15 * number, line)
        axis = bar_panel(figure, left, top, PAGE_HEIGHT - 26 - top, [r["state"] for r in order])
        rows_at = range(len(order))
        # Each row holds two bars, the earlier year on top, with a gap of surface color between them.
        axis.barh([row - 0.2 for row in rows_at], [r[f"baseline_{label}"] for r in order], height=0.4,
                  color=COLORS["baseline"], edgecolor=COLORS["surface"], linewidth=points(0.6))
        axis.barh([row + 0.2 for row in rows_at], [r[f"current_{label}"] for r in order], height=0.4,
                  color=COLORS["current"], edgecolor=COLORS["surface"], linewidth=points(0.6))
        longest = max(max(r[f"baseline_{label}"], r[f"current_{label}"]) for r in order)
        axis.set_xlim(0, longest * 1.03)
        for row, r in enumerate(order):
            note = missing_year_note(r[f"baseline_{label}"], r[f"current_{label}"], baseline_year, year)
            if note:
                row_note(axis, max(r[f"baseline_{label}"], r[f"current_{label}"]) + longest * 0.015, row, note)
    save(figure, path)


def chart_change(rows, path, baseline_year, year, minor_threshold):
    """Major and minor change per state, one panel per source, each sorted by its major change rate."""
    figure = new_figure()
    by_section = [r["state"] for r in rows if r["vote411_unit"] == "section"]
    by_question = [r["state"] for r in rows if r["vote411_unit"] != "section"]
    write(figure, 8, 8, f"How much each state's voter FAQ changed from {baseline_year} to {year}", TITLE, "text", fontweight="bold")
    write(figure, 8, 32, f"The share of each state's questions{' (or Vote411 sections)' if by_section else ''} that changed. "
                         "States are sorted by major change. The line marks the median state.")
    add_legend(figure, 51, [
        Patch(color=COLORS["major"], label=f"Major: new, removed, or edited below {minor_threshold} similarity"),
        Patch(color=COLORS["minor"], label=f"Minor edits ({minor_threshold} similarity or above)"),
        Line2D([], [], color=COLORS["text"], linewidth=points(1.5), label="Median major change")])
    for left, label in zip(PANEL_LEFTS, ("state_site", "vote411")):
        rated = sorted((r for r in rows if r[f"major_change_rate_{label}"] is not None),
                       key=lambda r: (-r[f"major_change_rate_{label}"], -r[f"change_rate_{label}"], r["state"]))
        # States with no rate go below the others, with the reason in place of a bar.
        unrated = sorted((r for r in rows if r[f"major_change_rate_{label}"] is None), key=lambda r: r["state"])
        axis = bar_panel(figure, left, 111, PAGE_HEIGHT - 26 - 111, [r["state"] for r in rated + unrated])
        major = [100 * r[f"major_change_rate_{label}"] for r in rated]
        minor = [100 * r[f"minor_edit_rate_{label}"] for r in rated]
        # The surface-colored edge leaves a gap between the two segments of a bar.
        axis.barh(range(len(rated)), major, height=0.7, color=COLORS["major"], edgecolor=COLORS["surface"], linewidth=points(1))
        axis.barh(range(len(rated)), minor, left=major, height=0.7, color=COLORS["minor"], edgecolor=COLORS["surface"],
                  linewidth=points(1))
        for row, r in enumerate(rated):
            if r[f"change_rate_{label}"] == 0:
                row_note(axis, 1, row, "no change", italic=False)
        for row, r in enumerate(unrated, start=len(rated)):
            row_note(axis, 1, row, r[f"change_rate_note_{label}"])
        if rated and unrated:
            axis.axhline(len(rated) - 0.5, color=COLORS["grid"], linewidth=points(1))
        title = SOURCE_LABELS[label]
        if rated:
            median = statistics.median(r[f"major_change_rate_{label}"] for r in rated)
            axis.plot([100 * median] * 2, [-0.5, len(rated) - 0.5], color=COLORS["text"], linewidth=points(1.5))
            title += f": median major change {percent(median)} ({len(rated)} states)"
        axis.set_xlim(0, 100)
        axis.set_xticks(range(0, 101, 25), [f"{tick}%" for tick in range(0, 101, 25)])
        line = "Share of questions"
        if label == "vote411" and by_section:
            line = f"Compared by section in {len(by_section)} states"
            if by_question:
                named = f" ({', '.join(state.upper() for state in by_question)})" if len(by_question) <= 5 else ""
                line += f", by question in {len(by_question)}{named}"
        write(figure, left, 76, title, PANEL_TITLE, "text", fontweight="bold")
        write(figure, left, 93, line)
    save(figure, path)


def coverage_title(rows, topics, baseline_year, year):
    """The topic chart's finding, such as "49 of 50 states covered all six topics in 2024, and all 50 in 2026"."""
    def states(key):
        full = sum(r[f"topics_covered_{key}"] == len(topics) for r in rows)
        return f"all {len(rows)}" if full == len(rows) else f"{full} of {len(rows)}"
    title = (f"{states('baseline')} states covered all {NUMBER_WORDS.get(len(topics), len(topics))} topics in {baseline_year}, "
             f"and {states('current')} in {year}")
    return title[0].upper() + title[1:]


def chart_topics(rows, path, baseline_year, year, topics):
    """Questions per topic and state for both years, in a few color steps, with empty squares marked."""
    order = sorted(rows, key=lambda r: r["coverage_rank"])
    cycles = (("baseline", baseline_year), ("current", year))
    gaps = [f"{state_name(r['state'])} {topic['label'].lower()} in {cycle}" for key, cycle in cycles for r in order
            for topic in topics if not r[f"{topic['name']}_{key}"]]
    figure = new_figure()
    write(figure, 8, 8, coverage_title(rows, topics, baseline_year, year), TITLE, "text", fontweight="bold")
    write(figure, 8, 32, f"Each square is one state and topic. States are ordered by topics covered in {year}, then by their "
                         f"{year} questions on those topics, most at the top.")
    if not gaps:
        gap_line = "No state is missing a topic in either year."
    else:
        gap_line = f"An X marks a topic with no question: {'; '.join(gaps)}." if len(gaps) <= 3 else \
            f"An X marks a topic with no question ({len(gaps)} squares)."
    write(figure, 8, 47, gap_line)
    add_legend(figure, 66, [Line2D([], [], linestyle="none", marker="x", color=COLORS["text"], markersize=points(8),
                                   markeredgewidth=points(1.6), label="no question")]
               + [Patch(color=color, label=label) for _, label, color in TOPIC_STEPS])
    colors = ListedColormap([COLORS["empty"]] + [color for _, _, color in TOPIC_STEPS])
    steps = BoundaryNorm([0] + [low for low, _, _ in TOPIC_STEPS] + [float("inf")], colors.N)
    names = ["\n".join(textwrap.wrap(topic["label"], 9, break_long_words=False)) for topic in topics]
    for left, (key, cycle) in zip(PANEL_LEFTS, cycles):
        write(figure, left, 90, str(cycle), PANEL_TITLE, "text", fontweight="bold")
        axis = add_panel(figure, left, 137, PAGE_HEIGHT - 8 - 137, [r["state"] for r in order])
        grid = [[r[f"{topic['name']}_{key}"] for topic in topics] for r in order]
        # The surface-colored cell edges keep neighboring squares apart.
        axis.pcolormesh(grid, cmap=colors, norm=steps, edgecolors=COLORS["surface"], linewidth=points(2))
        axis.set_yticks([row + 0.5 for row in range(len(order))], [r["state"].upper() for r in order])
        axis.set_ylim(len(order), 0)
        axis.xaxis.tick_top()
        axis.set_xticks([column + 0.5 for column in range(len(topics))], names, linespacing=1.05)
        for row, counts in enumerate(grid):
            for column, count in enumerate(counts):
                if not count:
                    axis.add_patch(Rectangle((column + 0.04, row + 0.1), 0.92, 0.8, facecolor=COLORS["empty"],
                                             edgecolor=COLORS["text"], linewidth=points(1.2)))
                    axis.plot(column + 0.5, row + 0.5, marker="x", color=COLORS["text"], markersize=points(8),
                              markeredgewidth=points(1.8))
    save(figure, path)


def analyze(year, baseline_year, output, states=None):
    """Run the comparison and the cross-state analysis for the given states; return the per-state rows."""
    baseline, current = load_dataset(dataset_dir(baseline_year)), load_dataset(dataset_dir(year))
    states = sorted(states or current)
    settings = load_settings()
    topics = topic_rules(settings)
    details, summary = compare(baseline, current, states, load_manifest(baseline_year), load_manifest(year), settings)
    write_comparison(output, details, summary, baseline_year, year, settings)
    rows = per_state_table(baseline, current, details, summary, states, baseline_year, year, topics, settings["quality"])
    write_csv(Path(output) / "per_state.csv", rows)
    topic_rows = [{"state": r["state"], "year": y, "topic": t, "questions": r[f"{t}_{k}"]}
                  for r in rows for y, k in ((baseline_year, "baseline"), (year, "current"))
                  for t in (topic["name"] for topic in topics)]
    write_csv(Path(output) / "topics.csv", topic_rows)
    rankings = sorted(({"state": r["state"], "coverage_rank": r["coverage_rank"], "topics_covered": r["topics_covered_current"],
                        **{f"{name}_{label}": r[f"{name}_{label}"] for label in ("state_site", "vote411")
                           for name in ("major_change_rank", "major_change_rate", "minor_edit_rate", "change_rate")},
                        "vote411_unit": r["vote411_unit"]}
                       for r in rows), key=lambda r: r["coverage_rank"])
    write_csv(Path(output) / "rankings.csv", rankings)
    charts = Path(output) / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    chart_counts(rows, charts / "questions_per_state.png", baseline_year, year)
    chart_change(rows, charts / "change_rate_by_state.png", baseline_year, year,
                 settings["comparison"]["answer_minor_threshold"])
    chart_topics(rows, charts / "topic_coverage.png", baseline_year, year, topics)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--baseline-year", type=int, default=2024)
    parser.add_argument("--output", type=Path, help="Default: data/<year>/analysis")
    parser.add_argument("states", nargs="*", help="Limit to these state codes")
    arguments = parser.parse_args()
    output = arguments.output or ROOT / "data" / str(arguments.year) / "analysis"
    rows = analyze(arguments.year, arguments.baseline_year, output, arguments.states)
    print(f"Analyzed {len(rows)} states. Output: {output}")


if __name__ == "__main__":
    main()
