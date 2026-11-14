"""Turn saved state election site pages into Q&A records with one general parser."""

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import Comment
from pypdf import PdfReader

from collect_sc import ROOT, load_sources, make_entry, parse_scvotes, source_text
from datasets import hostname, load_dataset, normalize_url, record_source


PARSER_VERSION = 2
QUESTION_MAX_CHARS = 300
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
# Elements that hold one question label when their text reads as a question.
LABEL_TAGS = {"button", "summary", "dt", "label", "strong", "b", "span", "em"}
# Containers whose whole text is checked as a question when nothing inside them is one.
SHORT_CONTAINERS = {"div", "span", "td", "th"}
# A label tag that wraps any of these is treated as a container instead of a single label.
BLOCK_TAGS = HEADINGS | {"div", "p", "ul", "ol", "dl", "li", "table", "section", "article", "blockquote", "details", "form"}
Q_LABEL = re.compile(r"^\s*Q\s*[:.)]\s*", re.I)
A_LABEL = re.compile(r"^\s*A(nswer)?\s*[:.)]\s*", re.I)
# In-page navigation repeated inside answers, such as Vermont's "Return to Top" and North Dakota's "Copy Link".
NAVIGATION_LINE = re.compile(r"^\s*((back|return) to top|top of page|copy link)\b[^\n]*$", re.I | re.M)
# Page feedback widgets phrased as questions.
BOILERPLATE_QUESTION = re.compile(r"^(was this (page|information|content) (helpful|useful)|did you find what you|"
                                  r"is there anything wrong with this page|how can we improve)", re.I)
# Unfilled page templates, such as Arizona's hidden "__title__?" blocks.
TEMPLATE_PLACEHOLDER = re.compile(r"__\w+__|\{\{.*?\}\}")
ROOT_SELECTORS = ("main", "[role=main]", "#main-content", "#maincontent", "#main", "#content", ".main-content", "article")
REMOVE_SELECTOR = ("script, style, noscript, template, svg, iframe, nav, aside, footer, "
                   "[role=navigation], [role=banner], [role=contentinfo], [role=complementary], [role=search]")
NAV_CLASS = re.compile(r"(^|[-_])(nav|navbar|navigation|menu|megamenu|breadcrumbs?|sidebar|sidenav|footer|skip)([-_]|$)")
# Hostnames with their own parser; everything else uses the general parser.
SITE_PARSERS = {"scvotes.gov": parse_scvotes}
# Fraction of the 2024 count for the same URL below which a page is flagged for review.
LOW_COUNT_RATIO = 0.5
PDF_QUESTION = re.compile(r"(?m)^\s*(\d+)\.\s+")


def visible_text(element):
    return re.sub(r"\s+", " ", element.get_text(" ", strip=True))


def is_question_text(text, strict=False):
    """A question is short and ends with ? or starts with a Q: label.

    strict applies to plain paragraphs and divs, which must be a single sentence, because
    answers often contain lines such as "Not sure if you are registered?".
    """
    if (not text or len(text) > QUESTION_MAX_CHARS or not text.endswith("?")
            or BOILERPLATE_QUESTION.match(text) or TEMPLATE_PLACEHOLDER.search(text)):
        return False
    # A Q: label marks a question even when it has several sentences.
    return bool(Q_LABEL.match(text)) or not (strict and re.search(r"[.!?]\s+[A-Z]", text[:-1]))


def is_toggle_link(element):
    """Accordion toggles are often links to an anchor or carry aria/data toggle attributes."""
    return element.get("href", "").startswith("#") or any(
        attribute in element.attrs for attribute in ("aria-expanded", "aria-controls", "data-toggle", "data-bs-toggle", "role"))


def content_root(soup):
    """Pick the page's main content area so site menus, headers and footers are left out.

    For each selector, the match with the most text wins, and it must hold at least a
    tenth of the page's text, so a small widget such as Wyoming's first <article> is skipped.
    """
    body = soup.body or soup
    page_length = len(visible_text(body)) or 1
    for selector in ROOT_SELECTORS:
        matches = soup.select(selector)
        if matches:
            root = max(matches, key=lambda match: len(visible_text(match)))
            if len(visible_text(root)) >= 0.1 * page_length:
                return root
    return body


def holds_page_content(element):
    """A wrapper around the main content or the page title is never a menu, whatever its class."""
    return element.find(["main", "h1"]) is not None or element.select_one("[role=main]") is not None


def remove_page_chrome(root):
    """Remove menus and sidebars inside the content area, but never a wrapper holding most of the page."""
    total = len(visible_text(root)) or 1
    for element in root.select(REMOVE_SELECTOR):
        if not element.decomposed and len(visible_text(element)) < 0.6 * total and not holds_page_content(element):
            element.decompose()
    for element in root.find_all(True):
        if element.decomposed:
            continue
        names = " ".join(element.get("class", [])) + " " + element.get("id", "")
        if (any(NAV_CLASS.search(name.lower()) for name in names.split())
                and len(visible_text(element)) < 0.6 * total and not holds_page_content(element)):
            element.decompose()


def page_blocks(element):
    """Return (kind, element) blocks in page order; kind is question, heading or content.

    A container with no question or heading inside it stays one content block, so its
    paragraphs and lists keep their formatting when rendered.
    """
    if isinstance(element, Comment):
        return []
    if isinstance(element, NavigableString):
        return [("content", element)] if str(element).strip() else []
    if not isinstance(element, Tag):
        return []
    name = element.name
    text = visible_text(element)
    if name in HEADINGS:
        return [("question" if is_question_text(text) else "heading", element)]
    is_label = name in LABEL_TAGS or (name == "a" and is_toggle_link(element))
    if is_label and element.find(BLOCK_TAGS) is None:
        if name in {"button", "summary"} and not is_question_text(text):
            return []  # controls such as "Expand all"
        return [("question" if is_question_text(text) else "content", element)]
    if name == "p":
        return paragraph_blocks(element, text)
    if name == "a" and not is_label:
        return [("content", element)]
    blocks = [block for child in element.children for block in page_blocks(child)]
    if any(kind != "content" for kind, _ in blocks):
        return blocks
    if name in SHORT_CONTAINERS and is_question_text(text, strict=True):
        return [("question", element)]
    return [("content", element)] if blocks else []


def paragraph_blocks(paragraph, text):
    """Handle a whole-paragraph question, a bold lead-in question, and "Q: ... A: ..." paragraphs."""
    first = next((child for child in paragraph.children
                  if isinstance(child, Tag) or str(child).strip()), None)
    if isinstance(first, Tag) and first.name in {"strong", "b"} and is_question_text(visible_text(first)):
        remainder = deepcopy(paragraph)
        remainder.find(first.name).decompose()
        return [("question", first), ("content", remainder)]
    if is_question_text(text, strict=True):
        return [("question", paragraph)]
    if Q_LABEL.match(text) and "?" in text:
        question, answer = text.split("?", 1)
        answer_tag = Tag(name="p")
        answer_tag.append(answer)
        question_tag = Tag(name="p")
        question_tag.append(question + "?")
        return [("question", question_tag), ("content", answer_tag)]
    return [("content", paragraph)]


def clean_question(text):
    return Q_LABEL.sub("", re.sub(r"\s+", " ", text)).strip()


def heading_level(element):
    """Level of a heading, or of the heading inside a label such as <a><h4>...</h4></a>; None if neither."""
    if isinstance(element, Tag):
        heading = element if element.name in HEADINGS else element.find(HEADINGS)
        if heading is not None:
            return int(heading.name[1])
    return None


def heading_in_answer(element, question):
    """A heading deeper than the question's own heading, or a sentence-length one, is part of the answer.

    New Jersey, for example, writes answers in <h5> under <h4> questions.
    """
    question_level = heading_level(question)
    return (question_level is not None and heading_level(element) > question_level) or len(visible_text(element)) > 150


def records_from_blocks(blocks, metadata):
    """Pair each question with the blocks after it until the next question or non-question heading."""
    url = metadata["final_url"]
    records = []
    seen = set()
    question = None
    answer_parts = []

    def flush():
        if question is None:
            return
        q = clean_question(source_text([question], url, include_links=False))
        a = NAVIGATION_LINE.sub("", A_LABEL.sub("", source_text(answer_parts, url), count=1))
        a = re.sub(r"\n{3,}", "\n\n", a).strip()
        # A question with no answer is a table-of-contents entry or a menu item.
        if q and a and (q, a) not in seen:
            seen.add((q, a))
            records.append(make_entry(q, a, metadata))

    for kind, element in blocks:
        if kind == "heading" and question is not None and heading_in_answer(element, question):
            kind = "content"
        if kind == "content":
            if question is not None:
                answer_parts.append(element)
            continue
        flush()
        question, answer_parts = (element, []) if kind == "question" else (None, [])
    flush()
    return records


def parse_html(content, metadata):
    soup = BeautifulSoup(content, "html.parser")
    site_parser = SITE_PARSERS.get(hostname(metadata["final_url"]))
    if site_parser is not None:
        return site_parser(soup, metadata), "site:" + hostname(metadata["final_url"])
    # Script text would otherwise count as page text when sizing the content area.
    for element in soup.select("script, style, noscript, template"):
        element.decompose()
    root = content_root(soup)
    remove_page_chrome(root)
    return records_from_blocks(page_blocks(root), metadata), "general"


def page_links(content, page_url):
    """Return (address, link text) for every link on an HTML page, with addresses made absolute."""
    links = []
    for tag in BeautifulSoup(content, "html.parser").find_all("a", href=True):
        address = urldefrag(urljoin(page_url, tag["href"].strip())).url
        if urlparse(address).scheme in ("http", "https"):
            links.append((address, " ".join(tag.get_text(" ", strip=True).split())))
    return links


def listed_urls():
    """Every address in sources.csv, normalized for comparing."""
    return {normalize_url(url) for _, _, url in load_sources()}


def faq_links(content, page_url, listed):
    """Links on a page that lead to FAQ pages on the same host, as {"url", "link_text"} dicts.

    A link counts when its address or its text contains "faq" in any case. The page itself and
    pages already in sources.csv (listed) are left out, and each address is returned once. A saved
    page with no questions and at least one of these links is a menu page: its questions are on the
    linked pages. Colorado's FAQsMain.html is one, with links such as VoterRegistrationFAQ.html.
    """
    own = normalize_url(page_url)
    links = {}
    for address, text in page_links(content, page_url):
        key = normalize_url(address)
        if (hostname(address) == hostname(page_url) and key != own and key not in listed
                and "faq" in f"{address} {text}".lower()):
            links.setdefault(key, {"url": address, "link_text": text})
    return list(links.values())


def linked_page_states(links, pages):
    """Add to each menu link what the batch holds for it: saved, failed with its error, or not downloaded."""
    by_url = {normalize_url(page["requested_url"]): page for page in pages if page["status"] != "superseded"}
    described = []
    for link in links:
        page = by_url.get(normalize_url(link["url"]))
        entry = dict(link, status=page["status"] if page else "not downloaded")
        if page and page["status"] == "failed":
            entry["error"] = page["error"]
        described.append(entry)
    return described


def parse_pdf(path, metadata):
    """Split numbered PDF FAQs ("1. ... ?") into records; the question ends at its first ?."""
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    # Drop private-use bullet characters that PDF fonts produce.
    text = re.sub(r"[-�•]", " ", text)
    pieces = PDF_QUESTION.split(text)
    records = []
    for index in range(1, len(pieces) - 1, 2):
        body = pieces[index + 1]
        if "?" not in body:
            continue
        question, answer = body.split("?", 1)
        question = re.sub(r"\s+", " ", question).strip() + "?"
        answer = re.sub(r"[ \t]*\n[ \t]*", " ", answer).strip()
        if is_question_text(question) and answer:
            records.append(make_entry(question, re.sub(r"\s{2,}", " ", answer), metadata))
    return records, "pdf"


def replaced_urls():
    """Map each replacement URL in sources.csv to the 2024 URL its note says it replaces."""
    import csv
    from collect_sc import SOURCES_CSV
    mapping = {}
    with open(SOURCES_CSV, newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            match = re.search(r"Replaces 2024 URL (\S+)", row.get("notes", ""))
            if match and row["url"].strip():
                mapping[normalize_url(row["url"])] = normalize_url(match.group(1))
    return mapping


def baseline_url_counts(baseline):
    """Count baseline state-site records per normalized source URL, per state."""
    counts = {}
    for state, records in baseline.items():
        counts[state] = Counter(normalize_url(record["s"]) for record in records
                                if record_source(record) == "state" and "://" in str(record["s"]))
    return counts


def parse_batch(batch_dir, baseline=None, states=None):
    """Parse every saved page in a state-site batch; return ({state: records}, page report)."""
    batch_dir = Path(batch_dir)
    manifest = json.loads((batch_dir / "batch_manifest.json").read_text(encoding="utf-8"))
    counts = baseline_url_counts(baseline or {})
    replacements = replaced_urls()
    listed = listed_urls()
    dataset, report = {}, []
    for state, pages in manifest["pages"].items():
        if states and state not in states:
            continue
        dataset.setdefault(state, [])
        for page in pages:
            if page["status"] != "saved":
                continue
            metadata = {"final_url": page.get("final_url") or page["requested_url"], "collected_at": page["collected_at"]}
            path = ROOT / page["snapshot"]
            if page["content_type"] == "application/pdf":
                records, parser = parse_pdf(path, metadata)
            else:
                records, parser = parse_html(path.read_bytes(), metadata)
            dataset[state].extend(records)
            keys = {normalize_url(page["requested_url"]), normalize_url(metadata["final_url"])}
            keys |= {replacements[key] for key in list(keys) if key in replacements}
            baseline_count = max((counts.get(state, {}).get(key, 0) for key in keys), default=0)
            flags, extra = [], {}
            if "linked_from" in page:
                extra["linked_from"] = page["linked_from"]
            # A page with no questions that links to FAQ pages is a menu, not a page that failed to load.
            links = faq_links(path.read_bytes(), metadata["final_url"], listed) if not records and parser != "pdf" else []
            if not records and parser == "pdf":
                flags.append("No numbered questions found in the PDF text")
            elif links and "linked_from" in page:
                # Menus are followed one level only, so the pages this one links to are not downloaded.
                flags.append(f"No questions on this page. It links to {len(links)} more FAQ page{'s' if len(links) != 1 else ''}, "
                             "not followed because this page was itself reached from a menu page")
            elif links:
                extra["menu_links"] = linked_page_states(links, pages)
                flags.append(f"No questions on this page. It is a menu: it links to {len(links)} FAQ page{'s' if len(links) != 1 else ''} "
                             "on the same site, and the questions are on those pages (listed under menu_page)")
            elif not records:
                flags.append("No Q&A text found in the saved page; the content may be loaded by JavaScript")
            elif baseline_count and len(records) < LOW_COUNT_RATIO * baseline_count:
                flags.append(f"{len(records)} records, well below the {baseline_count} the baseline had for this URL")
            report.append({"state": state, "url": page["requested_url"], "final_url": metadata["final_url"],
                           "snapshot": page["snapshot"], "capture_method": page["capture_method"],
                           "parser": parser, "records": len(records), "baseline_records": baseline_count,
                           "flags": flags, **extra})
    # Each menu link gets the question count of its saved page, now that every page has been parsed.
    found = {(row["state"], normalize_url(row["url"])): row["records"] for row in report}
    for row in report:
        for link in row.get("menu_links", []):
            if link["status"] == "saved":
                link["records"] = found.get((row["state"], normalize_url(link["url"])))
    return dataset, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="A state-site batch folder under data/<year>/state_sites/")
    parser.add_argument("states", nargs="*", help="Limit to these state codes")
    parser.add_argument("--baseline", type=Path, default=ROOT / "data" / "2024", help="Baseline dataset folder")
    parser.add_argument("--show", type=int, default=0, help="Print the first N records of each page")
    arguments = parser.parse_args()
    dataset, report = parse_batch(ROOT / arguments.batch, load_dataset(arguments.baseline), arguments.states)
    for page in report:
        print(f"{page['state'].upper()} {page['records']:>3} (baseline {page['baseline_records']:>3}) "
              f"{page['parser']:<8} {page['url']}" + "".join(f"\n    FLAG: {flag}" for flag in page["flags"]))
    if arguments.show:
        for state, records in dataset.items():
            for record in records[:arguments.show]:
                print(f"\n[{state}] Q: {record['q']}\nA: {record['a'][:300]}")
    print(f"{sum(map(len, dataset.values()))} records from {len(report)} pages")


if __name__ == "__main__":
    main()
