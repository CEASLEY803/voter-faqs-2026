"""Collect source text and retain snapshots for human review."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag
import requests


ROOT = Path(__file__).resolve().parent
SC_URL = "https://scvotes.gov/voters/voter-faq/"
VOTE411_URL = "https://www.vote411.org/south-carolina"


def source_text(elements, url):
    """Keep published wording and append link targets while normalizing whitespace."""
    parts = []
    for element in elements:
        copied = deepcopy(element)
        if isinstance(copied, Tag):
            for unwanted in copied.select("script, style"):
                unwanted.decompose()
            links = ([copied] if copied.name == "a" else []) + copied.find_all("a", href=True)
            for link in links:
                target = urljoin(url, link.get("href", ""))
                if urlparse(target).scheme in {"http", "https", "mailto", "tel"}:
                    if target != link.get_text(strip=True):
                        link.append(f" ({target})")
            parts.append(copied.get_text(" ", strip=True))
        else:
            parts.append(str(copied))
    return re.sub(r"\s+", " ", " ".join(parts).replace("\u200b", "")).strip()


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
    review = []
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
            entries.append(make_entry(title, source_text([body], url), metadata))
            review.append({"question": title, "reason": "Published topic title used as q"})
            continue
        introduction = []
        for child in body.children:
            if isinstance(child, Tag) and child.name == "h6":
                break
            introduction.append(child)
        introductory_text = source_text(introduction, url)
        if introductory_text:
            entries.append(make_entry(title, introductory_text, metadata))
            review.append({"question": title, "reason": "Introductory text preserved under published topic title"})
        for question in questions:
            answer_parts = []
            for sibling in question.next_siblings:
                if isinstance(sibling, Tag) and sibling.name == "h6":
                    break
                answer_parts.append(sibling)
            entries.append(make_entry(source_text([question], url), source_text(answer_parts, url), metadata))
    return entries, review


def validate_dataset(dataset):
    """Check format and collection defects, without deciding factual correctness."""
    entries = dataset["questions"]
    if not entries or dataset["num_questions"] != len(entries) or dataset["num_answers"] != len(entries):
        raise ValueError("Empty dataset or incorrect counts.")
    for index, entry in enumerate(entries):
        for field in ("q", "a", "s", "t"):
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
    arguments = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = ROOT / "data" / "2026" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    primary_page, primary_metadata = fetch_page(SC_URL, run_dir / "scvotes.html")
    secondary_page, secondary_metadata = fetch_page(VOTE411_URL, run_dir / "vote411-sc.html")
    primary = parse_scvotes(primary_page, primary_metadata)
    secondary, review = parse_vote411(secondary_page, secondary_metadata)
    entries = primary + secondary
    dataset = {"state": "sc", "num_questions": len(entries), "num_answers": len(entries),
               "contributor": arguments.contributor, "questions": entries}
    validate_dataset(dataset)
    output = run_dir / "sc_qa.json"
    output.write_text(json.dumps(dataset, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    metadata = {"sources": [primary_metadata, secondary_metadata],
                "counts": {"scvotes": len(primary), "vote411": len(secondary)},
                "review_status": "Pending human review of source fidelity and completeness",
                "review_items": review}
    (run_dir / "collection_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"SC Votes: {len(primary)}; Vote411: {len(secondary)}; total: {len(entries)}")
    print(f"Topic or introduction entries to review: {len(review)}")
    print(f"Validated output: {output}")


if __name__ == "__main__":
    main()
