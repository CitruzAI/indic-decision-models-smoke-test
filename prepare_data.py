#!/usr/bin/env python3
"""Build the fixed n=80 parallel sample (en, hi, ta) from IndicSentiment test.

Uses the unaltered upstream files in data/upstream/, pinned to the Hugging Face
revision recorded in data/SOURCE.md. No network call is required.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UPSTREAM_HI = ROOT / "data" / "upstream" / "hi.json"
UPSTREAM_TA = ROOT / "data" / "upstream" / "ta.json"
OUT = ROOT / "data" / "reviews.jsonl"

SEED = 42
N = 80
DATASET_SHA = "dc8f3f66886531c6897fedffca1e938a68fc5013"

SOURCE = {
    "dataset": "ai4bharat/IndicSentiment",
    "split": "test",
    "huggingface": "https://huggingface.co/datasets/ai4bharat/IndicSentiment",
    "huggingface_revision": DATASET_SHA,
    "paper": "Doddapaneni et al., 2023, Towards Leaving No Indic Language Behind, ACL 2023 (arXiv:2212.05409)",
    "license_note": "See data/SOURCE.md. The HF card has no license field; the paper and IndicBERT README release the datasets under CC-0.",
}


def load_rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if text.strip().startswith("["):
        rows = json.loads(text)
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if len(rows) != 1000:
        raise RuntimeError(f"{path} has {len(rows)} rows, expected 1000")
    return rows


def is_labeled(row: dict) -> bool:
    return row.get("LABEL") in {"Positive", "Negative"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hi", type=Path, default=UPSTREAM_HI)
    parser.add_argument("--ta", type=Path, default=UPSTREAM_TA)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--n", type=int, default=N)
    args = parser.parse_args()

    hi = load_rows(args.hi)
    ta = load_rows(args.ta)
    if len(hi) != len(ta):
        raise RuntimeError("hi and ta test files have different lengths")
    for i, (a, b) in enumerate(zip(hi, ta)):
        if a.get("ENGLISH REVIEW") != b.get("ENGLISH REVIEW") or a.get("LABEL") != b.get("LABEL"):
            raise RuntimeError(f"en/label mismatch at source_index {i}")

    labeled_indices = [i for i, row in enumerate(hi) if is_labeled(row)]
    none_indices = [i for i, row in enumerate(hi) if not is_labeled(row)]
    if len(labeled_indices) != 998:
        raise RuntimeError(f"expected 998 labeled rows, found {len(labeled_indices)}")
    if len(none_indices) != 2:
        raise RuntimeError(f"expected 2 unlabeled rows, found {len(none_indices)}")

    rng = random.Random(args.seed)
    chosen = sorted(rng.sample(labeled_indices, args.n))
    # Assign ids in source_index order so the file is stable to read; sampling is still seed 42.
    records = []
    for seq, index in enumerate(chosen, start=1):
        h, t = hi[index], ta[index]
        records.append(
            {
                "id": f"s{seq:03d}",
                "source_index": index,
                "label": h["LABEL"],
                "text_en": h["ENGLISH REVIEW"],
                "text_hi": h["INDIC REVIEW"],
                "text_ta": t["INDIC REVIEW"],
                "source": {
                    **SOURCE,
                    "hi_file": "data/upstream/hi.json",
                    "ta_file": "data/upstream/ta.json",
                },
            }
        )

    labels = Counter(r["label"] for r in records)
    if sum(labels.values()) != args.n:
        raise RuntimeError("sample size mismatch")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} rows to {args.out}")
    print("label counts:", dict(labels))
    print("source_index range:", records[0]["source_index"], "–", records[-1]["source_index"])
    print("unlabeled source_index excluded:", none_indices)


if __name__ == "__main__":
    main()
