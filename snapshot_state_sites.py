"""Save exact copies of every state election site page in sources.csv, without parsing."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests

from collect_sc import ROOT, source_urls


USER_AGENT = "VoterFAQResearch/1.0"
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


def save_response(record, state, state_dir, status_code, final_url, content_type, content):
    """Apply the same checks to downloaded and browser-captured pages, then keep exact bytes."""
    url = record["requested_url"]
    content_type = content_type.split(";")[0].strip().lower()
    record |= {"final_url": final_url, "status_code": status_code, "content_type": content_type}
    if status_code != 200:
        return record | {"status": "failed", "error": f"HTTP {status_code}"}
    if not same_site(url, final_url):
        return record | {"status": "failed", "error": "Redirected to another site"}
    if "404" in urlparse(final_url).path:
        return record | {"status": "failed", "error": "Redirected to a 404 page"}
    if content_type not in EXTENSIONS:
        return record | {"status": "failed", "error": f"Unexpected content type {content_type!r}"}
    if content_type == "text/html" and is_bot_check(content):
        return record | {"status": "failed", "error": "Bot-check page instead of content"}
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


def write_checklist(manifest, urls):
    """List failed pages still in sources.csv, with the file name each manual save should use."""
    rows = []
    for state, records in manifest["pages"].items():
        for record in records:
            url = record["requested_url"]
            if record["status"] == "failed" and url in urls.get(state, []) and record["error"] not in REMOVED_PAGE_ERRORS:
                rows.append({"state": state, "url": url, "save_as": snapshot_name(state, url) + ".html",
                             "reason": record["error"][:80]})
    MANUAL_DIR.mkdir(exist_ok=True)
    with open(MANUAL_DIR / "checklist.csv", "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["state", "url", "save_as", "reason"])
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("states", nargs="*", help="State codes; default is every state with a state row")
    parser.add_argument("--batch", type=Path, help="Continue an existing batch, fetching only pages not yet saved")
    parser.add_argument("--checklist", action="store_true",
                        help="With --batch, write manual_saves/checklist.csv of failed pages to save by hand")
    parser.add_argument("--import-manual", action="store_true",
                        help="With --batch, add pages saved by hand into manual_saves/ instead of downloading")
    arguments = parser.parse_args()
    if (arguments.checklist or arguments.import_manual) and not arguments.batch:
        parser.error("--checklist and --import-manual need --batch.")
    urls = source_urls("state")
    for state in arguments.states:
        if state not in urls:
            parser.error(f"No state rows with a URL for: {state}")
    states = arguments.states or list(urls)
    if arguments.batch:
        batch_dir = (ROOT / arguments.batch).resolve()
        manifest = json.loads((batch_dir / "batch_manifest.json").read_text(encoding="utf-8"))
    else:
        batch_dir = ROOT / "data" / "2026" / "state_sites" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        batch_dir.mkdir(parents=True)
        manifest = {"coverage": "State election sites; exact page snapshots, not yet parsed",
                    "started_at": now(), "pages": {}}
    if arguments.checklist:
        rows = write_checklist(manifest, urls)
        print(f"{len(rows)} pages to save by hand. Checklist: {MANUAL_DIR / 'checklist.csv'}")
        return
    manifest["status"] = "running"
    manifest_path = batch_dir / "batch_manifest.json"
    write_json(manifest_path, manifest)
    if arguments.import_manual:
        with open(MANUAL_DIR / "checklist.csv", newline="", encoding="utf-8") as file:
            checklist = list(csv.DictReader(file))
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
            records[:] = [old for old in records if old["requested_url"] != url] + [record]
            print(f"{state.upper()} {record['status']} (manual): {url}" + (f" ({record['error']})" if "error" in record else ""))
            write_json(batch_dir / state / "source_metadata.json", records)
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
                time.sleep(1)
            fetched += 1
            record = snapshot_page(state, url, state_dir)
            records[:] = [old for old in records if old["requested_url"] != url] + [record]
            print(f"{state.upper()} {record['status']}: {url}" + (f" ({record['error']})" if "error" in record else ""))
            write_json(state_dir / "source_metadata.json", records)
            write_json(manifest_path, manifest)
    for state, records in manifest["pages"].items():
        for record in records:
            # A failed URL later replaced in sources.csv stays as a record, but no longer counts as a failure.
            if record["status"] == "failed" and record["requested_url"] not in urls.get(state, []):
                record["status"] = "superseded"
    all_records = [record for records in manifest["pages"].values() for record in records
                   if record["status"] != "superseded"]
    failed = [record for record in all_records if record["status"] != "saved"]
    manifest["status"] = "completed_with_failures" if failed else "completed"
    manifest["last_updated_at"] = now()
    write_json(manifest_path, manifest)
    print(f"{len(all_records) - len(failed)} pages saved; {len(failed)} failed. Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
