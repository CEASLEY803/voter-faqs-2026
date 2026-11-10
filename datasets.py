"""Read and write yearly Q&A datasets, including the quirks of the 2024 files."""

import json
from pathlib import Path
import re
import tomllib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from collect_sc import ROOT


# Codes some 2024 files use instead of the standard postal code.
STATE_CODE_ALIASES = {"dl": "de", "mx": "nm"}
# 2024 records whose source is a county or nonprofit page rather than the state election site.
NON_STATE_HOSTS = {
    "vote.indy.gov": "Marion County, Indiana elections",
    "my.lwv.org": "League of Women Voters chapter page",
    "utahcounty.gov": "Utah County elections",
    "ohiovoterrights.org": "Ohio Voter Rights Coalition",
}
SOURCES = ("state", "vote411")
SETTINGS_FILE = ROOT / "settings.toml"
# How a state's Vote411 records were extracted, as recorded in each cycle's manifest.json:
#   question_headings           one record per published question heading inside a section
#   section_titles              one record per section, its title (or a question made from it) as the question
#   mixed                       section titles for some sections, question headings for others
#   sections_without_questions  the page had no question headings; content kept as sections only
#   page_fragments              records are dates, headings and sentences from the page, not questions
#   none                        no Vote411 records for the state
VOTE411_METHODS = ("question_headings", "section_titles", "mixed", "sections_without_questions", "page_fragments", "none")
VOTE411_UNITS = ("section", "question")


def load_settings(path=SETTINGS_FILE):
    settings = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    unit = settings["comparison"]["vote411_unit"]
    if unit not in ("auto", "section", "question"):
        raise SystemExit(f"{Path(path).name}: vote411_unit must be auto, section or question, not {unit!r}")
    for state, override in settings["comparison"].get("vote411_unit_overrides", {}).items():
        if override not in VOTE411_UNITS or len(state) != 2 or state != state.lower():
            raise SystemExit(f"{Path(path).name}: vote411_unit_overrides needs lowercase state codes set to "
                             f"section or question, not {state} = {override!r}")
    for key in ("reworded_threshold", "answer_minor_threshold", "boilerplate_share"):
        if not 0 <= settings["comparison"][key] <= 1:
            raise SystemExit(f"{Path(path).name}: {key} must be between 0 and 1")
    return settings


def non_faq_rules(settings):
    return [(rule["name"], re.compile(rule["pattern"])) for rule in settings["non_faq_rules"]]


def vote411_section_rules(settings):
    return [(rule["title"], re.compile(rule["pattern"])) for rule in settings["vote411_sections"]]


def assign_vote411_section(question, rules):
    """The first section whose keyword rule matches the question, or None."""
    text = normalize_text(question)
    return next((title for title, pattern in rules if pattern.search(text)), None)


def load_manifest(year):
    path = dataset_dir(year) / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def vote411_method(manifest, state):
    """The recorded Vote411 extraction method for a state, or 'unknown' if the manifest has none."""
    return manifest.get("extraction", {}).get("vote411", {}).get("methods", {}).get(state, "unknown")


def dataset_dir(year):
    """A built dataset lives in data/<year>/combined/; the 2024 baseline sits in data/2024/."""
    combined = ROOT / "data" / str(year) / "combined"
    return combined if combined.is_dir() else ROOT / "data" / str(year)


def records_from_file(data):
    """Return the records of one state file, whichever of the three 2024 layouts it uses."""
    if isinstance(data.get("questions"), list):
        return data["questions"]
    if isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data.get("q"), list):
        # nm_qa.json stores parallel q, a and s lists with one shared timestamp.
        times = data["t"] if isinstance(data.get("t"), list) else [data.get("t", "")] * len(data["q"])
        return [{"q": q, "a": a, "s": s, "t": t} for q, a, s, t in zip(data["q"], data["a"], data["s"], times)]
    return []


def load_dataset(directory):
    """Return {state code: [records]} for every *_qa.json file in a folder."""
    dataset = {}
    for path in sorted(Path(directory).glob("*_qa.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        code = path.name[:2].lower()
        state = STATE_CODE_ALIASES.get(code, code)
        dataset[state] = [record for record in records_from_file(data) if str(record.get("q", "")).strip()]
    return dataset


def hostname(url):
    return (urlparse(url).hostname or "").removeprefix("www.")


def record_source(record):
    """Classify a record as 'state', 'vote411' or 'other' from its s field."""
    source = str(record.get("s", "")).strip().lower()
    if not source:
        return "other"
    # Some 2024 records give a site name such as Voting411.org or Voter411 instead of a URL.
    if "411" in source:
        return "vote411"
    host = hostname(source if "://" in source else "https://" + source)
    return "other" if host in NON_STATE_HOSTS else "state"


def normalize_url(url):
    """Compare page URLs without fragments, trailing slashes, www. or Louisiana's per-question faqid."""
    parts = urlparse(url.strip())
    query = urlencode([(key, value) for key, value in parse_qsl(parts.query) if key.lower() != "faqid"])
    host = (parts.hostname or "").removeprefix("www.")
    return urlunparse(("https", host, parts.path.rstrip("/").lower(), "", query, ""))


def normalize_text(text):
    """Lowercase, drop link destinations and Q:/A: labels, and collapse punctuation and spaces."""
    text = re.sub(r"\((?:https?|mailto|tel):[^)]*\)", " ", str(text))
    text = re.sub(r"(?:https?://|www\.)\S+", " ", text)
    text = re.sub(r"^\s*[QA]\s*[:.)]\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*\d+[.)]\s+", "", text)  # Missouri numbers its questions
    # Delete apostrophes, so "don't", "don’t" and 2024's broken "don�t" all become "dont".
    text = re.sub(r"['‘’`�]", "", text)
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def write_state_file(path, state, records, contributor):
    """Write one state's records in the same layout as the 2024 files."""
    dataset = {"state": state, "num_questions": len(records), "num_answers": len(records),
               "contributor": contributor, "questions": records}
    path.write_text(json.dumps(dataset, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def write_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
