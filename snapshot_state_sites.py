"""Save exact copies of every state election site page in sources.csv, without parsing."""

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from difflib import SequenceMatcher
from pathlib import Path
import re
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests

from collect_sc import ROOT, source_urls
from datasets import load_settings, normalize_url
from parse_state_sites import faq_links, listed_urls, page_links, parse_html, parse_pdf


USER_AGENT = "VoterFAQResearch/1.0"
DELAY_SECONDS = 1
RETRY_DELAY_SECONDS = 10
# Written into the batch folder by --find-replacements and read by quality_report.py.
CANDIDATES_FILE = "replacement_candidates.json"
CANDIDATES_KEPT = 3
# Words too common in addresses and link text to say that two pages are about the same thing.
COMMON_WORDS = {"and", "the", "for", "your", "page", "pages", "html", "aspx", "index", "default"}
# The Internet Archive's list of the copies it holds of an address, and how its copies are marked in the manifest.
ARCHIVE_CDX = "https://web.archive.org/cdx/search/cdx"
ARCHIVE_METHOD = "Internet Archive copy"
ARCHIVE_TRIES = 4
ARCHIVE_BUSY_CODES = {429, 500, 502, 503, 504}
ARCHIVE_COPIES_TRIED = 3
EXTENSIONS = {"text/html": ".html", "application/pdf": ".pdf"}
MANUAL_DIR = ROOT / "manual_saves"
# Pages that are gone from the site; there is nothing to save by hand.
REMOVED_PAGE_ERRORS = {"HTTP 404", "Redirected to a 404 page"}
# Some sites answer a script with a bot-check page and HTTP 200 instead of the real page.
# These scripts also appear on normal pages, so a page only counts as a bot check when it
# has one of them and almost no visible text.
BOT_CHECK_MARKERS = (b"_Incapsula_Resource", b"validate.perfdrive.com", b"/cdn-cgi/challenge-platform")
MIN_VISIBLE_TEXT = 500


def is_bot_check(content):
    if not any(marker in content for marker in BOT_CHECK_MARKERS):
        return False
    soup = BeautifulSoup(content, "html.parser")
    for hidden in soup.select("script, style, noscript"):
        hidden.decompose()
    return len(soup.get_text(" ", strip=True)) < MIN_VISIBLE_TEXT


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def snapshot_name(state, url):
    """Name files by URL so adding or reordering CSV rows never renames a page."""
    return f"{state}-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]}"


def same_site(first, second):
    """Compare hostnames, ignoring a leading www. and any port such as :443."""
    return urlparse(first).hostname.removeprefix("www.") == urlparse(second).hostname.removeprefix("www.")


def response_error(url, status_code, final_url, content_type, content):
    """Say why a response is not the page that was asked for, or return "" when it is."""
    if status_code != 200:
        return f"HTTP {status_code}"
    if not same_site(url, final_url):
        return "Redirected to another site"
    if "404" in urlparse(final_url).path:
        return "Redirected to a 404 page"
    if content_type not in EXTENSIONS:
        return f"Unexpected content type {content_type!r}"
    if content_type == "text/html" and is_bot_check(content):
        return "Bot-check page instead of content"
    return ""


def save_response(record, state, state_dir, status_code, final_url, content_type, content):
    """Apply the same checks to downloaded and browser-captured pages, then keep exact bytes."""
    url = record["requested_url"]
    content_type = content_type.split(";")[0].strip().lower()
    record |= {"final_url": final_url, "status_code": status_code, "content_type": content_type}
    error = response_error(url, status_code, final_url, content_type, content)
    if error:
        return record | {"status": "failed", "error": error}
    path = state_dir / (snapshot_name(state, url) + EXTENSIONS[content_type])
    path.write_bytes(content)
    return record | {"status": "saved", "snapshot": path.relative_to(ROOT).as_posix(),
                     "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def snapshot_page(state, url, state_dir):
    """Download one page; problems are recorded, not raised."""
    record = {"requested_url": url, "capture_method": "requests", "user_agent": USER_AGENT, "collected_at": now()}
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=40)
    except requests.RequestException as error:
        return record | {"status": "failed", "error": f"{type(error).__name__}: {error}"}
    return save_response(record, state, state_dir, response.status_code, response.url,
                         response.headers.get("Content-Type", ""), response.content)


def import_manual_page(state, url, path, state_dir):
    """Add a page a person saved from their own browser for a site that refuses scripted requests."""
    content = path.read_bytes()
    record = {"requested_url": url, "capture_method": "manual browser save", "saved_file_name": path.name,
              "collected_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
              "collected_at_source": "modified time of the saved file"}
    if path.suffix.lower() == ".pdf":
        return save_response(record, state, state_dir, 200, url, "application/pdf", content)
    # The page's own canonical address catches a file saved under another page's name.
    soup = BeautifulSoup(content, "html.parser")
    tag = soup.find("link", rel="canonical") or soup.find("meta", property="og:url")
    canonical = (tag.get("href") or tag.get("content") or "").strip() if tag else ""
    if canonical.startswith("http"):
        record["canonical_url"] = canonical
        if not same_site(url, canonical):
            return record | {"status": "failed", "error": "Saved page belongs to another site"}
    return save_response(record, state, state_dir, 200, url, "text/html", content)


def write_json(path, content):
    path.write_text(json.dumps(content, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def removed_pages(manifest, urls):
    """Return (state, record) for each failed page that is gone from its site and still in sources.csv."""
    return [(state, record) for state, records in manifest["pages"].items() for record in records
            if record["status"] == "failed" and record["error"] in REMOVED_PAGE_ERRORS
            and record["requested_url"] in urls.get(state, [])]


def read_page(url):
    """Download a page without saving it; return (final_url, content_type, content, error).

    A dropped connection is tried once more after a longer wait, because one bad moment would
    otherwise be reported as a candidate that cannot be read.
    """
    for wait in (DELAY_SECONDS, RETRY_DELAY_SECONDS):
        time.sleep(wait)
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=40)
            break
        except requests.RequestException as error:
            failure = f"Connection failed twice ({type(error).__name__})"
    else:
        return url, "", b"", failure
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    error = response_error(url, response.status_code, response.url, content_type, response.content)
    return response.url, content_type, response.content, error


def words(text):
    return {word for word in re.split(r"[^a-z0-9]+", text.lower()) if len(word) > 2 and word not in COMMON_WORDS}


def closeness(removed_url, url, link_text):
    """Score a link from 0 to 1 as a replacement for a removed page.

    The score is the average of two parts: how alike the two addresses are, letter by letter, and
    the share of the words in the removed page's own name that the link text also has.
    For /idr/hoosiers-vote/register/, a link to /idr/hoosiers-vote/register-to-vote with the text
    "Register to Vote" scores high on both parts.
    """
    old_path, new_path = (urlparse(address).path.rstrip("/").lower() for address in (removed_url, url))
    address_part = SequenceMatcher(None, old_path, new_path).ratio()
    name = words(old_path.rsplit("/", 1)[-1])
    text_part = len(name & words(link_text)) / len(name) if name else 0
    return round((address_part + text_part) / 2, 3)


def parent_address(url):
    """The address one level up: .../hoosiers-vote/register/ gives .../hoosiers-vote/."""
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/').rsplit('/', 1)[0]}/"


def find_candidates(state, record, manifest, urls, parents):
    """Look for up to three pages that may have replaced one removed page.

    Links come from the removed page's parent address and from the state's saved HTML pages in the
    batch. Each candidate is downloaded once to count the questions the parser finds on it; the
    download is not kept. parents holds parent pages already read, so two removed pages in one
    folder cost one download.
    """
    removed = record["requested_url"]
    parent = parent_address(removed)
    if parent not in parents:
        final_url, content_type, content, error = read_page(parent)
        parents[parent] = {"error": error, "links": page_links(content, final_url) if not error and content_type == "text/html" else []}
    found = [(address, text, parent) for address, text in parents[parent]["links"]]
    for page in manifest["pages"][state]:
        if page["status"] == "saved" and page["content_type"] == "text/html":
            for address, text in page_links((ROOT / page["snapshot"]).read_bytes(), page["final_url"]):
                found.append((address, text, page["requested_url"]))
    known = {normalize_url(url) for state_urls in urls.values() for url in state_urls}
    best = {}
    for address, text, found_on in found:
        key = normalize_url(address)
        if not same_site(removed, address) or key in known:
            continue
        score = closeness(removed, address, text)
        if key not in best or score > best[key]["closeness"]:
            best[key] = {"url": address, "link_text": text, "found_on": found_on, "closeness": score}
    candidates = sorted(best.values(), key=lambda link: (-link["closeness"], link["url"]))[:CANDIDATES_KEPT]
    for candidate in candidates:
        final_url, content_type, content, error = read_page(candidate["url"])
        candidate["final_url"] = final_url
        if not error and normalize_url(final_url) in known:
            error = "Leads to a page already in sources.csv"
        if error:
            candidate |= {"questions": None, "error": error}
        elif content_type != "text/html":
            candidate |= {"questions": None, "error": "PDF; questions are only counted on HTML pages"}
        else:
            records, _ = parse_html(content, {"final_url": final_url, "collected_at": now()})
            candidate["questions"] = len(records)
    return {"state": state, "removed_url": removed, "error": record["error"], "searched_at": now(), "parent_url": parent,
            "parent_error": parents[parent]["error"], "links_compared": len(best), "candidates": candidates}


def find_replacements(batch_dir, manifest, urls, states=None):
    """Search for replacements for every removed page still in sources.csv and save the candidates.

    The result is a list of suggestions for a person to check. sources.csv is never changed here.
    With states, only those states are searched again and the saved results for the others are kept.
    """
    path = batch_dir / CANDIDATES_FILE
    earlier = {}
    if states and path.is_file():
        earlier = {(page["state"], page["removed_url"]): page
                   for page in json.loads(path.read_text(encoding="utf-8"))["pages"]}
    parents, pages, searched = {}, [], 0
    for state, record in removed_pages(manifest, urls):
        if states and state not in states:
            # A page that is no longer removed, or no longer in sources.csv, never reaches this line, so it drops out.
            if (state, record["requested_url"]) in earlier:
                pages.append(earlier[(state, record["requested_url"])])
            continue
        searched += 1
        page = find_candidates(state, record, manifest, urls, parents)
        pages.append(page)
        print(f"{state.upper()} removed ({page['error']}): {page['removed_url']}")
        if page["parent_error"]:
            print(f"    parent address not read ({page['parent_error']}): {page['parent_url']}")
        for candidate in page["candidates"]:
            result = candidate.get("error") or f"{candidate['questions']} questions"
            print(f"    candidate, closeness {candidate['closeness']}: {candidate['url']} ({result})")
        if not page["candidates"]:
            print("    no candidate found")
    write_json(path, {
        "about": "Pages that may have replaced removed pages still in sources.csv. Suggestions only; "
                 "check each one and edit sources.csv by hand.",
        "pages": pages})
    return pages, searched


def still_wanted(state, record, urls):
    """True for a page in sources.csv, and for a page linked from a menu page that is in sources.csv."""
    listed = urls.get(state, [])
    return record["requested_url"] in listed or record.get("linked_from") in listed


def count_questions(record):
    """How many questions the parser finds on one saved page."""
    metadata = {"final_url": record["final_url"], "collected_at": record["collected_at"]}
    path = ROOT / record["snapshot"]
    if record["content_type"] == "application/pdf":
        return len(parse_pdf(path, metadata)[0])
    return len(parse_html(path.read_bytes(), metadata)[0])


def menu_pages(manifest, urls, states=None, only=None):
    """Return (state, record, links) for each saved page in sources.csv that is a menu page.

    A menu page has no questions of its own and links to FAQ pages on the same host (see faq_links).
    Pages that were themselves reached from a menu are never checked, so menus are followed one level only.
    states limits the check to those states; only limits it to the given (state, address) pairs.
    """
    listed = listed_urls()
    menus = []
    for state, records in manifest["pages"].items():
        if states and state not in states:
            continue
        for record in records:
            if only is not None and (state, record["requested_url"]) not in only:
                continue
            if (record["status"] != "saved" or record["content_type"] != "text/html"
                    or record["requested_url"] not in urls.get(state, []) or count_questions(record)):
                continue
            links = faq_links((ROOT / record["snapshot"]).read_bytes(), record["final_url"], listed)
            if links:
                menus.append((state, record, links))
    return menus


def follow_menus(batch_dir, manifest, urls, states=None, only=None):
    """Download the FAQ pages that each menu page links to into the batch; return what happened to each.

    A linked page is saved and checked exactly like a page from sources.csv, and its record also says
    which menu page it came from (linked_from) and the link's text. A linked page already saved in
    the batch is not downloaded again. sources.csv is never changed here.
    """
    results, fetched = [], 0
    for state, menu, links in menu_pages(manifest, urls, states, only):
        records = manifest["pages"][state]
        print(f"{state.upper()} menu page, {len(links)} linked FAQ pages: {menu['requested_url']}")
        for link in links:
            url = link["url"]
            record = next((old for old in records if old["requested_url"] == url and old["status"] == "saved"), None)
            if record is None:
                if fetched:
                    time.sleep(DELAY_SECONDS)
                fetched += 1
                record = snapshot_page(state, url, batch_dir / state)
                record |= {"linked_from": menu["requested_url"], "link_text": link["link_text"]}
                records[:] = [old for old in records if old["requested_url"] != url] + [record]
                write_json(batch_dir / state / "source_metadata.json", records)
                write_json(batch_dir / "batch_manifest.json", manifest)
            questions = count_questions(record) if record["status"] == "saved" else None
            results.append({"state": state, "menu": menu["requested_url"], "url": url, "status": record["status"],
                            "error": record.get("error", ""), "questions": questions})
            print(f"    {record['status']}" + (f", {questions} questions" if questions is not None else f" ({record['error']})")
                  + f": {url}")
    return results


def general_election_day(year):
    """The Tuesday after the first Monday in November: November 3 in 2026, November 7 in 2028."""
    first = date(year, 11, 1)
    first_monday = first + timedelta(days=(7 - first.weekday()) % 7)
    return first_monday + timedelta(days=1)


def archive_window(year, days):
    """(first day, last day) in which an archived copy counts as part of the cycle's collection.

    The window ends the day before election day and starts `days` days before election day.
    For 2026 and 60 days that is September 4 to November 2.
    """
    election_day = general_election_day(year)
    return election_day - timedelta(days=days), election_day - timedelta(days=1)


def archive_get(url, params=None):
    """Ask the Internet Archive for one address; return (response, "") or (None, why not).

    The archive often times out or answers "try later", so the request is repeated a few times
    with a longer pause each time.
    """
    failure = ""
    for attempt in range(ARCHIVE_TRIES):
        time.sleep(DELAY_SECONDS if attempt == 0 else RETRY_DELAY_SECONDS * attempt)
        try:
            response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=60)
        except requests.RequestException as error:
            failure = type(error).__name__
            continue
        if response.status_code in ARCHIVE_BUSY_CODES:
            failure = f"HTTP {response.status_code}"
            continue
        return response, ""
    return None, f"no answer after {ARCHIVE_TRIES} tries ({failure})"


def archive_copies(url, window):
    """Return ([(timestamp, address)], "") for the archive's copies of a page in the window, newest first.

    Only copies the archive saved with status 200 are asked for. A timestamp is 14 digits,
    such as 20261020064857 for October 20, 2026 at 06:48:57 UTC.
    """
    response, error = archive_get(ARCHIVE_CDX, {
        "url": url, "from": f"{window[0]:%Y%m%d}", "to": f"{window[1]:%Y%m%d}",
        "filter": "statuscode:200", "output": "json", "fl": "timestamp,original"})
    if error:
        return [], error
    if response.status_code != 200:
        return [], f"the Internet Archive lookup answered HTTP {response.status_code}"
    try:
        rows = response.json() if response.text.strip() else []
    except ValueError:
        return [], "the Internet Archive lookup answer could not be read"
    # The first row holds the column names.
    return sorted((tuple(row) for row in rows[1:]), reverse=True), ""


def fill_page_from_archive(state, record, state_dir, window):
    """Replace one blocked page's record with a saved Internet Archive copy, when the window has one.

    The newest copy is tried first, then up to two older ones if a copy turns out to be unusable
    (for example a bot-check page that the archive saved). The copy's capture time becomes
    collected_at, because that is when the page looked like this. Without a usable copy the
    record stays failed and gets an archive_lookup note saying why.
    """
    url = record["requested_url"]
    span = f"{window[0]} to {window[1]}"
    copies, note = archive_copies(url, window)
    if not copies and not note:
        note = f"no copy from {span}"
    for stamp, original in copies[:ARCHIVE_COPIES_TRIED]:
        # id_ after the timestamp asks for the page as the site sent it, without the archive's toolbar.
        response, error = archive_get(f"https://web.archive.org/web/{stamp}id_/{original}")
        if error:
            note = error
            continue
        # The archive can answer with a different copy than the one asked for, so the date is read from its answer.
        served = re.search(r"/web/(\d{14})", response.url)
        captured = datetime.strptime(served.group(1) if served else stamp, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        if not window[0] <= captured.date() <= window[1]:
            note = f"the archive answered with a copy from {captured.date()}, outside {span}"
            continue
        copy = {"requested_url": url, "capture_method": ARCHIVE_METHOD, "user_agent": USER_AGENT,
                "archive_url": response.url, "collected_at": captured.isoformat(timespec="seconds"),
                "collected_at_source": "capture time of the Internet Archive copy", "downloaded_at": now(),
                "error_before_archive": record["error"]}
        copy |= {key: record[key] for key in ("linked_from", "link_text") if key in record}
        copy = save_response(copy, state, state_dir, response.status_code, url,
                             response.headers.get("Content-Type", ""), response.content)
        if copy["status"] == "saved":
            return copy
        note = f"the copy of {captured.date()} could not be used ({copy['error']})"
    return record | {"archive_lookup": f"{note}; checked {now()[:10]}"}


def blocked_pages(manifest, urls, states=None, only=None):
    """Return (state, record) for each wanted page that failed because the site refused it, not because it is gone."""
    return [(state, record) for state, records in manifest["pages"].items() for record in records
            if record["status"] == "failed" and record["error"] not in REMOVED_PAGE_ERRORS
            and still_wanted(state, record, urls) and (not states or state in states)
            and (only is None or (state, record["requested_url"]) in only)]


def fill_from_archive(batch_dir, manifest, urls, year, window_days, states=None, only=None):
    """Fill blocked pages from the Internet Archive; return (pages filled, pages looked up, window).

    A filled page from sources.csv is then checked for a menu like any other saved page. Its linked
    pages are downloaded, and the ones the site refuses are looked up in the archive too.
    sources.csv is never changed here.
    """
    window = archive_window(year, window_days)
    looked_up = set()

    def fill(only):
        filled = []
        for state, record in blocked_pages(manifest, urls, states, only):
            url = record["requested_url"]
            if (state, url) in looked_up:
                continue
            looked_up.add((state, url))
            result = fill_page_from_archive(state, record, batch_dir / state, window)
            records = manifest["pages"][state]
            records[:] = [result if old is record else old for old in records]
            write_json(batch_dir / state / "source_metadata.json", records)
            write_json(batch_dir / "batch_manifest.json", manifest)
            if result["status"] == "saved":
                filled.append((state, url))
                print(f"{state.upper()} filled from the Internet Archive, copy of {result['collected_at'][:10]}, "
                      f"{count_questions(result)} questions: {url}")
            else:
                print(f"{state.upper()} not filled ({result['archive_lookup']}): {url}")
        return filled

    filled = fill(only)
    linked = follow_menus(batch_dir, manifest, urls, only=set(filled)) if filled else []
    refused = {(result["state"], result["url"]) for result in linked if result["status"] == "failed"}
    if refused:
        filled += fill(refused)
    return filled, len(looked_up), window


def close_batch(manifest, urls, manifest_path):
    """Set the batch's status from its pages and write the manifest."""
    for state, records in manifest["pages"].items():
        for record in records:
            # A failed URL later replaced in sources.csv stays as a record, but no longer counts as a failure.
            # The same goes for a page linked from a menu page that has left sources.csv.
            if record["status"] == "failed" and not still_wanted(state, record, urls):
                record["status"] = "superseded"
    all_records = [record for records in manifest["pages"].values() for record in records
                   if record["status"] != "superseded"]
    failed = [record for record in all_records if record["status"] != "saved"]
    manifest["status"] = "completed_with_failures" if failed else "completed"
    manifest["last_updated_at"] = now()
    write_json(manifest_path, manifest)
    print(f"{len(all_records) - len(failed)} pages saved; {len(failed)} failed. Manifest: {manifest_path}")


def write_checklist(manifest, urls):
    """List failed pages still wanted, with the file name each manual save should use.

    Callers run fill_from_archive first, so the list holds only pages the Internet Archive could not fill.
    """
    rows = []
    for state, records in manifest["pages"].items():
        for record in records:
            url = record["requested_url"]
            if record["status"] == "failed" and still_wanted(state, record, urls) and record["error"] not in REMOVED_PAGE_ERRORS:
                reason = record["error"][:80] + (f"; Internet Archive: {record['archive_lookup']}" if "archive_lookup" in record else "")
                rows.append({"state": state, "url": url, "save_as": snapshot_name(state, url) + ".html", "reason": reason})
    MANUAL_DIR.mkdir(exist_ok=True)
    with open(MANUAL_DIR / "checklist.csv", "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["state", "url", "save_as", "reason"])
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("states", nargs="*", help="State codes; default is every state with a state row")
    parser.add_argument("--year", type=int, default=datetime.now(timezone.utc).year, help="Collection cycle; default is the current year")
    parser.add_argument("--batch", type=Path, help="Continue an existing batch, fetching only pages not yet saved")
    parser.add_argument("--checklist", action="store_true",
                        help="With --batch, write manual_saves/checklist.csv of failed pages to save by hand, "
                             "after trying to fill them from the Internet Archive")
    parser.add_argument("--fill-from-archive", action="store_true",
                        help="With --batch, fill pages the site refused with the Internet Archive's newest copy "
                             "from the days before election day (settings.toml, [archive])")
    parser.add_argument("--import-manual", action="store_true",
                        help="With --batch, add pages saved by hand into manual_saves/ instead of downloading; "
                             "an imported menu page has its linked FAQ pages downloaded too")
    parser.add_argument("--find-replacements", action="store_true",
                        help=f"With --batch, look for pages that replaced removed pages and write {CANDIDATES_FILE} in the batch folder")
    parser.add_argument("--follow-menus", action="store_true",
                        help="With --batch, download the FAQ pages linked from saved pages that are only a menu of FAQ topics")
    arguments = parser.parse_args()
    if (arguments.checklist or arguments.import_manual or arguments.find_replacements or arguments.follow_menus
            or arguments.fill_from_archive) and not arguments.batch:
        parser.error("--checklist, --import-manual, --find-replacements, --follow-menus and --fill-from-archive need --batch.")
    urls = source_urls("state")
    for state in arguments.states:
        if state not in urls:
            parser.error(f"No state rows with a URL for: {state}")
    states = arguments.states or list(urls)
    if arguments.batch:
        batch_dir = (ROOT / arguments.batch).resolve()
        manifest = json.loads((batch_dir / "batch_manifest.json").read_text(encoding="utf-8"))
        # The batch sits in data/<year>/state_sites/, so its own year is used, not the year of the day it is run.
        year = int(batch_dir.parents[1].name) if batch_dir.parents[1].name.isdigit() else arguments.year
    else:
        batch_dir = ROOT / "data" / str(arguments.year) / "state_sites" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        batch_dir.mkdir(parents=True)
        manifest = {"coverage": "State election sites; exact page snapshots, not yet parsed",
                    "started_at": now(), "pages": {}}
        year = arguments.year
    manifest_path = batch_dir / "batch_manifest.json"
    window_days = load_settings()["archive"]["window_days"]
    if arguments.checklist or arguments.fill_from_archive:
        # The archive is tried before anyone is asked to save a page by hand.
        filled, looked_up, window = fill_from_archive(batch_dir, manifest, urls, year, window_days, arguments.states)
        print(f"{looked_up} blocked pages looked up in the Internet Archive; {len(filled)} filled with a copy "
              f"from {window[0]} to {window[1]}.")
        if arguments.checklist:
            rows = write_checklist(manifest, urls)
            print(f"{len(rows)} pages to save by hand. Checklist: {MANUAL_DIR / 'checklist.csv'}")
        if filled:
            close_batch(manifest, urls, manifest_path)
        return
    if arguments.find_replacements:
        # Returns before the manifest is touched: the search adds one file and changes nothing else.
        pages, searched = find_replacements(batch_dir, manifest, urls, arguments.states)
        print(f"{searched} removed pages searched; {sum(bool(page['candidates']) for page in pages)} of the "
              f"{len(pages)} on file have candidates. Candidates: {batch_dir / CANDIDATES_FILE}")
        return
    manifest["status"] = "running"
    write_json(manifest_path, manifest)
    if arguments.import_manual:
        with open(MANUAL_DIR / "checklist.csv", newline="", encoding="utf-8") as file:
            checklist = list(csv.DictReader(file))
        imported = set()
        for row in checklist:
            state, url = row["state"], row["url"]
            records = manifest["pages"].setdefault(state, [])
            if any(record["requested_url"] == url and record["status"] == "saved" for record in records):
                continue
            stem = Path(row["save_as"]).stem
            files = [path for path in MANUAL_DIR.glob(stem + ".*") if path.suffix.lower() in {".html", ".htm", ".pdf"}]
            if not files:
                print(f"{state.upper()} not saved yet: {url}")
                continue
            record = import_manual_page(state, url, files[0], batch_dir / state)
            # A page linked from a menu keeps the note of which menu it came from.
            earlier = next((old for old in records if old["requested_url"] == url), {})
            record |= {key: earlier[key] for key in ("linked_from", "link_text") if key in earlier}
            records[:] = [old for old in records if old["requested_url"] != url] + [record]
            print(f"{state.upper()} {record['status']} (manual): {url}" + (f" ({record['error']})" if "error" in record else ""))
            write_json(batch_dir / state / "source_metadata.json", records)
            if record["status"] == "saved":
                imported.add((state, url))
        # A menu page that had to be saved by hand is first seen here, so its linked pages are fetched now.
        # Its site usually refuses those downloads too; they then join the checklist for the next round.
        results = follow_menus(batch_dir, manifest, urls, only=imported) if imported else []
        refused = {(result["state"], result["url"]) for result in results if result["status"] == "failed"}
        if refused:
            # The archive is tried for the refused pages before the checklist asks for them.
            filled, _, _ = fill_from_archive(batch_dir, manifest, urls, year, window_days, only=refused)
            left = len(blocked_pages(manifest, urls, only=refused))
            write_checklist(manifest, urls)
            print(f"{len(refused)} pages linked from an imported menu page refused scripted downloads; {len(filled)} were "
                  "filled from the Internet Archive."
                  + (f" The other {left} are now in {MANUAL_DIR / 'checklist.csv'}: save them by hand and run "
                     "--import-manual again." if left else ""))
        states = []
    if arguments.follow_menus:
        results = follow_menus(batch_dir, manifest, urls, arguments.states)
        blocked = sum(result["status"] == "failed" and result["error"] not in REMOVED_PAGE_ERRORS for result in results)
        print(f"{len({result['menu'] for result in results})} menu pages; {len(results)} linked pages, "
              f"{sum(result['status'] == 'saved' for result in results)} saved."
              + (f" {blocked} refused scripted downloads; --checklist tries the Internet Archive for them and lists the rest to save by hand." if blocked else ""))
        states = []
    fetched = 0
    for state in states:
        state_dir = batch_dir / state
        state_dir.mkdir(exist_ok=True)
        records = manifest["pages"].setdefault(state, [])
        saved = {record["requested_url"] for record in records if record["status"] == "saved"}
        for url in urls[state]:
            if url in saved:
                continue
            if fetched:
                time.sleep(DELAY_SECONDS)
            fetched += 1
            record = snapshot_page(state, url, state_dir)
            records[:] = [old for old in records if old["requested_url"] != url] + [record]
            print(f"{state.upper()} {record['status']}: {url}" + (f" ({record['error']})" if "error" in record else ""))
            write_json(state_dir / "source_metadata.json", records)
            write_json(manifest_path, manifest)
    close_batch(manifest, urls, manifest_path)


if __name__ == "__main__":
    main()
