"""Cross-state analysis: counts, change rates, topic coverage, rankings and charts."""

import argparse
import csv
from pathlib import Path
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from collect_sc import ROOT
from compare_years import compare, write_comparison
from datasets import SOURCES, dataset_dir, load_dataset, load_manifest, load_settings, normalize_text, record_source


# Keyword rules applied to normalized question text (lowercase, punctuation removed). Only the
# question is checked, because answers mention many topics in passing.
TOPICS = {
    "registration": r"\bregist",
    "mail_absentee": r"\babsentee|\bmail in\b|\bby mail\b|\bvote by mail|\bmail ballot|\bdrop box",
    "early_voting": r"\bearly vot|\bvote early|\bvoting early",
    "voter_id": r"\b(photo|voter|valid|acceptable|show|bring|need|required?|forms? of) (an )?ids?\b|\bidentification\b|\bid (card|required|requirements?)\b",
    "polling_places": r"\bpolling (place|location|site)|\bpolls?\b|\bwhere (do|can|should|will) i vote|\bvote centers?\b|\bprecinct",
    "deadlines": r"\bdeadlines?\b|\blast day\b|\bdue\b|\bhow late\b|\bpostmark|\bby what date\b|\bhow soon\b",
}
TOPIC_LABELS = {"registration": "Registration", "mail_absentee": "Mail and absentee", "early_voting": "Early voting",
                "voter_id": "Voter ID", "polling_places": "Polling places", "deadlines": "Deadlines"}
SOURCE_LABELS = {"state": "State election site", "vote411": "Vote411"}
# Reference palette: categorical slots 1 and 2, sequential blue ramp, text and surface tokens.
COLORS = {"baseline": "#2a78d6", "current": "#eb6834", "single": "#2a78d6",
          "text": "#0b0b0b", "muted": "#52514e", "grid": "#e4e3df", "surface": "#fcfcfb"}
SEQUENTIAL = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def topic_counts(records):
    counts = dict.fromkeys(TOPICS, 0)
    for record in records:
        question = normalize_text(record["q"])
        for topic, pattern in TOPICS.items():
            if re.search(pattern, question):
                counts[topic] += 1
    return counts


def change_rate(row):
    """Share of questions in either year that did not carry over with the same wording and answer."""
    total = row["same"] + row["reworded"] + row["new"] + row["removed"]
    unchanged = row["same"] - row["same_answer_changed"]
    return round(1 - unchanged / total, 3) if total else None


def rank(rows, key, reverse=True):
    """Dense 1-based ranks; states with no value are left unranked."""
    values = sorted({row[key] for row in rows if row[key] is not None}, reverse=reverse)
    return {row["state"]: (values.index(row[key]) + 1 if row[key] is not None else None) for row in rows}


def per_state_table(baseline, current, details, summary, states):
    by_key = {(row["state"], row["source"]): row for row in summary}
    rows = []
    for state in states:
        row = {"state": state}
        vote411_row = by_key[(state, "vote411")]
        row["vote411_unit"] = vote411_row["unit"]
        row["vote411_method_baseline"], row["vote411_method_current"] = vote411_row["baseline_method"], vote411_row["current_method"]
        for source in SOURCES:
            stats = dict(by_key[(state, source)])
            stats["same_answer_changed"] = sum(1 for item in details[state] if item["source"] == source
                                               and item["status"] == "same" and item.get("answer_status") == "changed")
            label = "state_site" if source == "state" else "vote411"
            # Record counts are always questions; compared counts are sections when the unit is "section".
            row[f"baseline_{label}"] = sum(record_source(r) == source for r in baseline.get(state, []))
            row[f"current_{label}"] = sum(record_source(r) == source for r in current.get(state, []))
            row[f"compared_baseline_{label}"] = stats["baseline_count"]
            row[f"compared_current_{label}"] = stats["current_count"]
            for status in ("same", "reworded", "new", "removed"):
                row[f"{status}_{label}"] = stats[status]
            row[f"answers_changed_{label}"] = stats["answers_changed"]
            row[f"change_rate_{label}"] = change_rate(stats)
            # How much matched answers (or sections) changed, since a section edited in one word counts as changed.
            similarities = [item["answer_similarity"] for item in details[state]
                            if item["source"] == source and "answer_similarity" in item]
            row[f"mean_answer_similarity_{label}"] = round(sum(similarities) / len(similarities), 3) if similarities else None
        for year_key, dataset in (("baseline", baseline), ("current", current)):
            counts = topic_counts([r for r in dataset.get(state, []) if record_source(r) in SOURCES])
            row[f"topics_covered_{year_key}"] = sum(1 for count in counts.values() if count)
            row[f"topic_questions_{year_key}"] = sum(counts.values())
            for topic, count in counts.items():
                row[f"{topic}_{year_key}"] = count
        rows.append(row)
    coverage_order = sorted(rows, key=lambda r: (-r["topics_covered_current"], -r["topic_questions_current"], r["state"]))
    for position, row in enumerate(coverage_order, start=1):
        row["coverage_rank"] = position
    for label in ("state_site", "vote411"):
        ranks = rank(rows, f"change_rate_{label}")
        for row in rows:
            row[f"change_rank_{label}"] = ranks[row["state"]]
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


def chart_change(rows, path, baseline_year, year):
    """Change rate per state, one panel per source, each sorted on its own values."""
    figure, axes = plt.subplots(1, 2, figsize=(11, max(4, 0.22 * len(rows) + 1.5)), facecolor=COLORS["surface"])
    for axis, label in zip(axes, ("state_site", "vote411")):
        style_axis(axis)
        ranked = sorted((r for r in rows if r[f"change_rate_{label}"] is not None), key=lambda r: r[f"change_rate_{label}"])
        axis.barh(range(len(ranked)), [100 * r[f"change_rate_{label}"] for r in ranked], height=0.7, color=COLORS["single"])
        axis.set_yticks(range(len(ranked)), [r["state"].upper() for r in ranked])
        axis.set_ylim(-0.6, max(len(ranked), 1) - 0.4)
        axis.set_xlim(0, 100)
        axis.set_xlabel("Change rate (%)", color=COLORS["muted"], fontsize=8)
        title = SOURCE_LABELS["state" if label == "state_site" else "vote411"]
        if label == "vote411":
            by_section = sum(r["vote411_unit"] == "section" for r in ranked)
            title += f" (by section in {by_section} states, by question in {len(ranked) - by_section})"
        axis.set_title(title, color=COLORS["text"], fontsize=10, loc="left")
    figure.suptitle(f"Share not carried over unchanged, {baseline_year} to {year}",
                    color=COLORS["text"], x=0.01, ha="left")
    figure.tight_layout()
    figure.savefig(path, dpi=150, facecolor=COLORS["surface"])
    plt.close(figure)


def chart_topics(rows, path, baseline_year, year):
    """Questions per topic and state for both years on one color scale."""
    order = sorted(rows, key=lambda r: r["coverage_rank"])
    topics = list(TOPICS)
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
        axis.set_xticks([i + 0.5 for i in range(len(topics))], [TOPIC_LABELS[t] for t in topics], rotation=40, ha="right")
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
    details, summary = compare(baseline, current, states, load_manifest(baseline_year), load_manifest(year), settings)
    write_comparison(output, details, summary, baseline_year, year, settings)
    rows = per_state_table(baseline, current, details, summary, states)
    write_csv(Path(output) / "per_state.csv", rows)
    topic_rows = [{"state": r["state"], "year": y, "topic": t, "questions": r[f"{t}_{k}"]}
                  for r in rows for y, k in ((baseline_year, "baseline"), (year, "current")) for t in TOPICS]
    write_csv(Path(output) / "topics.csv", topic_rows)
    rankings = sorted(({"state": r["state"], "coverage_rank": r["coverage_rank"], "topics_covered": r["topics_covered_current"],
                        "change_rank_state_site": r["change_rank_state_site"], "change_rate_state_site": r["change_rate_state_site"],
                        "change_rank_vote411": r["change_rank_vote411"], "change_rate_vote411": r["change_rate_vote411"],
                        "vote411_unit": r["vote411_unit"]}
                       for r in rows), key=lambda r: r["coverage_rank"])
    write_csv(Path(output) / "rankings.csv", rankings)
    charts = Path(output) / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    chart_counts(rows, charts / "questions_per_state.png", baseline_year, year)
    chart_change(rows, charts / "change_rate_by_state.png", baseline_year, year)
    chart_topics(rows, charts / "topic_coverage.png", baseline_year, year)
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
