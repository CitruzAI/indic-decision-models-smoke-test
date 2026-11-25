"""Load pinned Amazon MASSIVE test splits for en-US, hi-IN, and ta-IN.

Prefers the committed files in data/routing/upstream/. If those are missing,
downloads the official 1.1 archive, checks its sha256, and extracts the
test split. Parallel items share the same utterance id across locales.
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import urllib.request
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_DIR = ROOT / "data" / "routing" / "upstream"

HF_DATASET = "AmazonScience/massive"
HF_REVISION = "ff6bd8e4b27c3543e4f8fe2108f32bb95a6f8740"
ARCHIVE_VERSION = "1.1"
ARCHIVE_URL = "https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz"
ARCHIVE_SHA256 = "4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577"
LOCALES = ("en-US", "hi-IN", "ta-IN")
KEEP_FIELDS = ("id", "locale", "partition", "scenario", "intent", "utt")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_locale_test(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("partition") != "test":
                continue
            rows[str(row["id"])] = row
    return rows


def write_test_slim(rows: Iterable[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            slim = {k: row[k] for k in KEEP_FIELDS}
            fh.write(json.dumps(slim, ensure_ascii=False) + "\n")


def download_archive(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and _sha256(dest) == ARCHIVE_SHA256:
        return dest
    urllib.request.urlretrieve(ARCHIVE_URL, dest)
    digest = _sha256(dest)
    if digest != ARCHIVE_SHA256:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"archive sha256 mismatch: got {digest}, expected {ARCHIVE_SHA256}")
    return dest


def extract_test_from_archive(archive: Path, out_dir: Path) -> None:
    digest = _sha256(archive)
    if digest != ARCHIVE_SHA256:
        raise RuntimeError(f"archive sha256 mismatch: got {digest}")
    wanted = {f"1.1/data/{loc}.jsonl": loc for loc in LOCALES}
    found: dict[str, list[dict[str, Any]]] = {loc: [] for loc in LOCALES}
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            name = member.name
            if name not in wanted:
                continue
            loc = wanted[name]
            fh = tar.extractfile(member)
            if fh is None:
                raise RuntimeError(f"could not read {name}")
            for line in fh.read().decode("utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("partition") == "test":
                    found[loc].append(row)
    for loc in LOCALES:
        if not found[loc]:
            raise RuntimeError(f"no test rows for {loc} in archive")
        write_test_slim(found[loc], out_dir / f"{loc}.jsonl")


def ensure_upstream(upstream_dir: Path = UPSTREAM_DIR, archive_path: Path | None = None) -> Path:
    """Return the upstream directory, downloading the archive if files are missing."""
    paths = [upstream_dir / f"{loc}.jsonl" for loc in LOCALES]
    if all(p.exists() for p in paths):
        return upstream_dir
    archive = archive_path or (upstream_dir / "amazon-massive-dataset-1.1.tar.gz")
    download_archive(archive)
    extract_test_from_archive(archive, upstream_dir)
    return upstream_dir


def load_parallel_test(upstream_dir: Path = UPSTREAM_DIR) -> dict[str, dict[str, dict[str, Any]]]:
    """id -> {en, hi, ta} test rows. Intents and scenarios must match across locales."""
    ensure_upstream(upstream_dir)
    by_locale = {loc: load_locale_test(upstream_dir / f"{loc}.jsonl") for loc in LOCALES}
    en, hi, ta = by_locale["en-US"], by_locale["hi-IN"], by_locale["ta-IN"]
    if set(en) != set(hi) or set(en) != set(ta):
        raise RuntimeError("utterance ids are not aligned across en-US, hi-IN, and ta-IN")
    for uid, row in en.items():
        if hi[uid]["intent"] != row["intent"] or ta[uid]["intent"] != row["intent"]:
            raise RuntimeError(f"intent mismatch at id {uid}")
        if hi[uid]["scenario"] != row["scenario"] or ta[uid]["scenario"] != row["scenario"]:
            raise RuntimeError(f"scenario mismatch at id {uid}")
        for loc, item in (("en-US", row), ("hi-IN", hi[uid]), ("ta-IN", ta[uid])):
            if not (item.get("utt") or "").strip():
                raise RuntimeError(f"empty utterance at {loc} id {uid}")
    return {uid: {"en": en[uid], "hi": hi[uid], "ta": ta[uid]} for uid in en}
