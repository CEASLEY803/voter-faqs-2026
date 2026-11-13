"""Cross-state analysis: counts, change rates, topic coverage, rankings and charts."""

import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from collect_sc import ROOT
from compare_years import compare, write_comparison
from datasets import (SOURCES, dataset_dir, load_dataset, load_manifest, load_settings, question_topics, record_source,
                      topic_rules)


SOURCE_LABELS = {"state": "State election site", "vote411": "Vote411"}
# Reference palette: categorical slots 1 and 2, sequential blue ramp, text and surface tokens.
COLORS = {"baseline": "#2a78d6", "current": "#eb6834", "major": "#2a78d6", "minor": "#86b6ef",
          "text": "#0b0b0b", "muted": "#52514e", "grid": "#e4e3df", "surface": "#fcfcfb"}
SEQUENTIAL = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


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


def missing_year_note(baseline_count, current_count, baseline_year, year):
    """Why a state's change rates are left blank for a source, or "" when both years have records.

    With no records in one year, every question in the other year would count as new or removed:
    that is missing data, not change.
    """
    if not baseline_count and not current_count:
        return f"no {baseline_year} or {year} records"
    if not baseline_count:
        return f"no {baseline_year} records"
    return f"no {year} records" if not current_count else ""


def per_state_table(baseline, current, details, summary, states, baseline_year, year, topics):
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
            note = missing_year_note(row[f"baseline_{label}"], row[f"current_{label}"], baseline_year, year)
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


def style_axis(axis):
    axis.set_facecolor(COLORS["surface"])
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.spines["bottom"].set_color(COLORS["grid"])
    axis.tick_params(colors=COLORS["muted"], labelsize=8, length=0)
    axis.grid(axis="x", color=COLORS["grid"], linewidth=0.8)
    axis.set_axisbelow(True)


def chart_counts(rows, path, baseline_year, year):
    """Questions per state in both years, one panel per source so each keeps its own scale."""
    order = sorted(rows, key=lambda r: r["current_state_site"] + r["current_vote411"])
    positions = range(len(order))
    figure, axes = plt.subplots(1, 2, figsize=(11, max(4, 0.22 * len(order) + 1.5)), sharey=True, facecolor=COLORS["surface"])
    for axis, label in zip(axes, ("state_site", "vote411")):
        style_axis(axis)
        axis.barh([p + 0.21 for p in positions], [r[f"baseline_{label}"] for r in order], height=0.38,
                  color=COLORS["baseline"], label=str(baseline_year), edgecolor=COLORS["surface"], linewidth=1)
        axis.barh([p - 0.21 for p in positions], [r[f"current_{label}"] for r in order], height=0.38,
                  color=COLORS["current"], label=str(year), edgecolor=COLORS["surface"], linewidth=1)
        axis.set_title(SOURCE_LABELS["state" if label == "state_site" else "vote411"], color=COLORS["text"], fontsize=10, loc="left")
        axis.set_xlabel("Questions", color=COLORS["muted"], fontsize=8)
    axes[0].set_yticks(list(positions), [r["state"].upper() for r in order])
    axes[0].set_ylim(-0.6, len(order) - 0.4)
    axes[1].legend(frameon=False, fontsize=8, labelcolor=COLORS["text"], loc="lower right")
    figure.suptitle(f"Voter FAQ questions per state, {baseline_year} and {year}", color=COLORS["text"], x=0.01, ha="left")
    figure.tight_layout()
    figure.savefig(path, dpi=150, facecolor=COLORS["surface"])
    plt.close(figure)


def chart_change(rows, path, baseline_year, year, minor_threshold):
    """Major and minor change per state, one panel per source, each sorted by its major change rate."""
    figure, axes = plt.subplots(1, 2, figsize=(11, max(4, 0.22 * len(rows) + 2)), facecolor=COLORS["surface"])
    for axis, label in zip(axes, ("state_site", "vote411")):
        style_axis(axis)
        ranked = sorted((r for r in rows if r[f"change_rate_{label}"] is not None),
                        key=lambda r: (r[f"major_change_rate_{label}"], r[f"change_rate_{label}"]))
        # States with no records in one year have no rate; they go at the bottom with a note instead of a bar.
        unrated = sorted((r for r in rows if r[f"change_rate_{label}"] is None), key=lambda r: r["state"], reverse=True)
        positions = range(len(unrated), len(unrated) + len(ranked))
        major = [100 * r[f"major_change_rate_{label}"] for r in ranked]
        minor = [100 * r[f"minor_edit_rate_{label}"] for r in ranked]
        # The surface-colored edge leaves a gap between the two segments of a bar.
        axis.barh(positions, major, height=0.7, color=COLORS["major"], edgecolor=COLORS["surface"], linewidth=1,
                  label=f"Major: new, removed, or edited below {minor_threshold} similarity")
        axis.barh(positions, minor, left=major, height=0.7, color=COLORS["minor"], edgecolor=COLORS["surface"],
                  linewidth=1, label=f"Minor edits only ({minor_threshold} similarity or above)")
        for position, r in enumerate(unrated):
            axis.text(1, position, r[f"change_rate_note_{label}"], va="center", ha="left", fontsize=8,
                      style="italic", color=COLORS["muted"])
        axis.set_yticks(range(len(unrated) + len(ranked)), [r["state"].upper() for r in unrated + ranked])
        axis.set_ylim(-0.6, max(len(unrated) + len(ranked), 1) - 0.4)
        axis.set_xlim(0, 100)
        title = SOURCE_LABELS["state" if label == "state_site" else "vote411"]
        unit = "questions"
        if label == "vote411":
            by_section = sum(r["vote411_unit"] == "section" for r in ranked)
            unit = "sections" if by_section == len(ranked) else "questions" if not by_section else "sections or questions"
            if 0 < by_section < len(ranked):
                title += f" (by section in {by_section} states, by question in {len(ranked) - by_section})"
        axis.set_xlabel(f"Share of {unit} (%)", color=COLORS["muted"], fontsize=8)
        axis.set_title(title, color=COLORS["text"], fontsize=10, loc="left")
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, frameon=False, fontsize=8, labelcolor=COLORS["text"], loc="lower left",
                  bbox_to_anchor=(0.01, 0), ncols=2)
    figure.suptitle(f"Change per state, {baseline_year} to {year}", color=COLORS["text"], x=0.01, ha="left")
    figure.tight_layout(rect=(0, 0.025, 1, 1))
    figure.savefig(path, dpi=150, facecolor=COLORS["surface"])
    plt.close(figure)


def chart_topics(rows, path, baseline_year, year, topics):
    """Questions per topic and state for both years on one color scale."""
    order = sorted(rows, key=lambda r: r["coverage_rank"])
    labels = [topic["label"] for topic in topics]
    topics = [topic["name"] for topic in topics]
    peak = max([1] + [r[f"{t}_{k}"] for r in order for t in topics for k in ("baseline", "current")])
    colormap = LinearSegmentedColormap.from_list("blues", SEQUENTIAL)
    figure, axes = plt.subplots(1, 2, figsize=(9, max(4, 0.22 * len(order) + 2)), sharey=True,
                                facecolor=COLORS["surface"], layout="constrained")
    for axis, key, title in zip(axes, ("baseline", "current"), (str(baseline_year), str(year))):
        grid = [[r[f"{t}_{key}"] for t in topics] for r in order]
        # The surface-colored cell edges keep neighboring cells of similar shade apart.
        image = axis.pcolormesh(grid, cmap=colormap, vmin=0, vmax=min(peak, 20),
                                edgecolors=COLORS["surface"], linewidth=1.5)
        axis.set_facecolor(COLORS["surface"])
        axis.set_xticks([i + 0.5 for i in range(len(topics))], labels, rotation=40, ha="right")
        axis.set_yticks([i + 0.5 for i in range(len(order))], [r["state"].upper() for r in order])
        axis.set_ylim(len(order), 0)
        axis.tick_params(colors=COLORS["muted"], labelsize=8, length=0)
        axis.set_title(title, color=COLORS["text"], fontsize=10, loc="left")
        for spine in axis.spines.values():
            spine.set_visible(False)
    bar = figure.colorbar(image, ax=axes, shrink=0.4, pad=0.02)
    bar.set_label("Questions on the topic (20 or more shown darkest)", color=COLORS["muted"], fontsize=8)
    bar.ax.tick_params(colors=COLORS["muted"], labelsize=8)
    bar.outline.set_visible(False)
    figure.suptitle("Topic coverage by state, ordered by coverage rank", color=COLORS["text"], x=0.01, ha="left")
    figure.savefig(path, dpi=150, facecolor=COLORS["surface"])
    plt.close(figure)


def analyze(year, baseline_year, output, states=None):
    """Run the comparison and the cross-state analysis for the given states; return the per-state rows."""
    baseline, current = load_dataset(dataset_dir(baseline_year)), load_dataset(dataset_dir(year))
    states = sorted(states or current)
    settings = load_settings()
    topics = topic_rules(settings)
    details, summary = compare(baseline, current, states, load_manifest(baseline_year), load_manifest(year), settings)
    write_comparison(output, details, summary, baseline_year, year, settings)
    rows = per_state_table(baseline, current, details, summary, states, baseline_year, year, topics)
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
