"""Collect source text and retain snapshots for human review."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment, Tag
import requests


ROOT = Path(__file__).resolve().parent
SC_URL = "https://scvotes.gov/voters/voter-faq/"
VOTE411_URL = "https://www.vote411.org/south-carolina"


def render_html(element):
    """Render block boundaries and nested lists without splitting inline text."""
    if isinstance(element, Comment):
        return ""
    if not isinstance(element, Tag):
        return re.sub(r"\s+", " ", str(element).replace("\u200b", ""))
    if element.name == "br":
        return "\n"
    if element.name in {"ul", "ol"}:
        items = []
        number = int(element.get("start", 1))
        for item in element.find_all("li", recursive=False):
            if element.name == "ol":
                number = int(item.get("value", number))
                marker = f"{number}. "
                number += 1
            else:
                marker = "- "
            content = "".join(render_html(child) for child in item.children).strip()
            lines = content.splitlines()
            if lines:
                formatted = marker + lines[0]
                for line in lines[1:]:
                    formatted += "\n" + (" " * len(marker) + line if line.strip() else "")
                items.append(formatted)
        return "\n\n" + "\n".join(items) + "\n\n"
    content = "".join(render_html(child) for child in element.children)
    if element.name in {"p", "div", "section", "article", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}:
        return "\n\n" + content + "\n\n"
    return content


def source_text(elements, url):
    """Preserve paragraphs and lists, and append published link destinations."""
    parts = []
    for element in elements:
        copied = deepcopy(element)
        if isinstance(copied, Tag):
            for unwanted in copied.select("script, style"):
                unwanted.decompose()
            links = copied.find_all("a", href=True)
            if copied.name == "a":
                links.insert(0, copied)
            for link in links:
                target = urljoin(url, link.get("href", ""))
                if urlparse(target).scheme in {"http", "https", "mailto", "tel"}:
                    if target != link.get_text(strip=True):
                        link.append(f" ({target})")
        parts.append(render_html(copied))
    combined_text = "".join(parts)
    normalized_lines = []
    for line in combined_text.splitlines():
        normalized_lines.append(line.rstrip())
    normalized_text = "\n".join(normalized_lines)
    normalized_text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", normalized_text)
    return normalized_text.strip()


def fetch_page(url, snapshot_path):
    """Save exact response bytes and decode them strictly as UTF-8."""
    response = requests.get(url, headers={"User-Agent": "VoterFAQResearch/1.0"}, timeout=40)
    response.raise_for_status()
    if "html" not in response.headers.get("Content-Type", "").lower():
        raise ValueError(f"Expected HTML from {url}")
    html = response.content.decode("utf-8-sig", errors="strict")
    snapshot_path.write_bytes(response.content)
    metadata = {
        "requested_url": url, "final_url": response.url,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "snapshot": snapshot_path.relative_to(ROOT).as_posix(),
    }
    return BeautifulSoup(html, "html.parser"), metadata


def make_entry(question, answer, metadata):
    return {"q": question, "a": answer, "s": metadata["final_url"], "t": metadata["collected_at"]}


def make_supporting_content(topic, kind, content, metadata):
    return {"topic": topic, "kind": kind, "content": content,
            "s": metadata["final_url"], "t": metadata["collected_at"]}


def parse_scvotes(soup, metadata):
    rows = soup.select(".accordion-row")
    if not rows:
        raise ValueError("SC Votes accordion rows were not found.")
    entries = []
    for row in rows:
        question = row.select_one(".accordion-row-toggle")
        answer = row.select_one(".accordion-row-content")
        if question is None or answer is None:
            raise ValueError("An SC Votes row has changed structure.")
        entries.append(make_entry(source_text([question], metadata["final_url"]),
                                  source_text([answer], metadata["final_url"]), metadata))
    return entries


def parse_vote411(soup, metadata):
    tabs = soup.select(".tabs-right > .tab")
    if not tabs:
        raise ValueError("Vote411 tabs were not found.")
    entries = []
    supporting = []
    url = metadata["final_url"]
    for tab in tabs:
        heading = tab.find("h4")
        body = tab.select_one(".tab-body")
        if heading is None or body is None:
            raise ValueError("A Vote411 tab has changed structure.")
        title = source_text([heading], url)
        questions = body.find_all("h6")
        if any(question.parent is not body for question in questions):
            raise ValueError(f"Nested question headings need review: {title}")
        if not questions:
            content = source_text([body], url)
            if content:
                supporting.append(make_supporting_content(title, "section_without_questions", content, metadata))
            continue
        introduction = []
        for child in body.children:
            if isinstance(child, Tag) and child.name == "h6":
                break
            introduction.append(child)
        introductory_text = source_text(introduction, url)
        if introductory_text:
            supporting.append(make_supporting_content(title, "topic_introduction", introductory_text, metadata))
        for question in questions:
            answer_parts = []
            for sibling in question.next_siblings:
                if isinstance(sibling, Tag) and sibling.name == "h6":
                    break
                answer_parts.append(sibling)
            entries.append(make_entry(source_text([question], url), source_text(answer_parts, url), metadata))
    return entries, supporting


def validate_dataset(dataset):
    """Check format and collection defects, without deciding factual correctness."""
    entries = dataset["questions"]
    if not entries or dataset["num_questions"] != len(entries) or dataset["num_answers"] != len(entries):
        raise ValueError("Empty dataset or incorrect counts.")
    validate_records(entries, ("q", "a", "s", "t"))


def validate_records(entries, fields):
    """Apply shared text, source, and timestamp checks to either record type."""
    for index, entry in enumerate(entries):
        for field in fields:
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"Entry {index + 1} has an empty {field}.")
            if "\ufffd" in entry[field]:
                raise ValueError(f"Entry {index + 1} contains a Unicode replacement character.")
        if urlparse(entry["s"]).scheme != "https":
            raise ValueError(f"Entry {index + 1} has an invalid source URL.")
        timestamp = datetime.fromisoformat(entry["t"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Collection timestamps must include a timezone.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contributor", default="Cole Easley")
    parser.add_argument("--from-run", type=Path, help="Reprocess a saved run without downloading pages.")
    arguments = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = ROOT / "data" / "2026" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    if arguments.from_run:
        saved_metadata = json.loads((arguments.from_run / "collection_metadata.json").read_text(encoding="utf-8"))
        primary_page, primary_metadata = replay_page(saved_metadata["sources"][0], arguments.from_run, run_dir)
        secondary_page, secondary_metadata = replay_page(saved_metadata["sources"][1], arguments.from_run, run_dir)
    else:
        primary_page, primary_metadata = fetch_page(SC_URL, run_dir / "scvotes.html")
        secondary_page, secondary_metadata = fetch_page(VOTE411_URL, run_dir / "vote411-sc.html")
    primary = parse_scvotes(primary_page, primary_metadata)
    secondary, supporting = parse_vote411(secondary_page, secondary_metadata)
    entries = primary + secondary
    dataset = {"state": "sc", "num_questions": len(entries), "num_answers": len(entries),
               "contributor": arguments.contributor, "questions": entries}
    validate_dataset(dataset)
    validate_records(supporting, ("topic", "kind", "content", "s", "t"))
    output = run_dir / "sc_qa.json"
    output.write_text(json.dumps(dataset, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    supporting_dataset = {"state": "sc", "num_sections": len(supporting), "sections": supporting}
    (run_dir / "sc_supporting_content.json").write_text(
        json.dumps(supporting_dataset, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    metadata = {"sources": [primary_metadata, secondary_metadata],
                "counts": {"scvotes": len(primary), "vote411": len(secondary), "supporting_sections": len(supporting)},
                "extraction_version": 2,
                "reprocessed_from": str(arguments.from_run) if arguments.from_run else None,
                "review_status": "Pending human review of source fidelity and completeness",
                "supporting_content_file": "sc_supporting_content.json"}
    (run_dir / "collection_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"SC Votes: {len(primary)}; Vote411: {len(secondary)}; total: {len(entries)}")
    print(f"Supporting sections saved separately: {len(supporting)}")
    print(f"Validated output: {output}")


def replay_page(metadata, original_run, run_dir):
    """Reuse original source bytes and collection time, verifying their checksum."""
    filename = Path(metadata["snapshot"]).name
    content = (original_run / filename).read_bytes()
    if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
        raise ValueError(f"Saved source checksum mismatch: {filename}")
    destination = run_dir / filename
    destination.write_bytes(content)
    updated_metadata = dict(metadata)
    updated_metadata["snapshot"] = destination.relative_to(ROOT).as_posix()
    return BeautifulSoup(content.decode("utf-8-sig", errors="strict"), "html.parser"), updated_metadata


if __name__ == "__main__":
    main()
