"""Recover a pinned upstream dataset without changing the downloaded pilot."""

import hashlib
import io
import json
from pathlib import Path
import zipfile

import requests


ROOT = Path(__file__).resolve().parent
COMMIT = "27105405530734ac5466826829d0446e48dda079"
URL = f"https://codeload.github.com/ai4society/election-dataset-us/zip/{COMMIT}"


def main():
    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    recovered = {}
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        for member in archive.namelist():
            relative = Path(*Path(member).parts[1:])
            if relative.parts and relative.parts[0] == "data-us" and relative.suffix == ".json":
                destination = ROOT / "data" / "2024" / relative.relative_to("data-us")
            elif str(relative).replace("\\", "/") in {"LICENSE", "README.md", "code-us/validate_json.ipynb"}:
                destination = ROOT / "reference" / relative
            else:
                continue
            content = archive.read(member)
            if destination.exists() and destination.read_bytes() != content:
                raise ValueError(f"Refusing to overwrite different baseline bytes: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            recovered[destination.relative_to(ROOT).as_posix()] = hashlib.sha256(content).hexdigest()
    metadata = {"repository": "https://github.com/ai4society/election-dataset-us", "commit": COMMIT,
                "archive_url": URL, "sha256": recovered}
    (ROOT / "reference" / "baseline_provenance.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    baseline = json.loads((ROOT / "data/2024/sc_qa.json").read_text(encoding="utf-8"))
    print(f"Recovered {len(list((ROOT / 'data/2024').glob('*_qa.json')))} state files.")
    print(f"South Carolina baseline: {len(baseline['questions'])} entries.")


if __name__ == "__main__":
    main()
