#!/usr/bin/env python3
"""Build the fixed n=80 parallel request-routing sample from Amazon MASSIVE.

Amazon MASSIVE (CC BY 4.0): short assistant-style requests. Uses the committed
test splits in data/routing/upstream/, pinned in data/routing/SOURCE.md.
Downloads the official archive only if those files are missing. No inference.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from indic_smoke.routing.filter import item_has_wake_word
from indic_smoke.routing.load import (
    ARCHIVE_SHA256,
    ARCHIVE_URL,
    ARCHIVE_VERSION,
    HF_DATASET,
    HF_REVISION,
    LOCALES,
    UPSTREAM_DIR,
    load_parallel_test,
)
from indic_smoke.routing.mapping import (
    DROPPED_INTENTS,
    INTENT_TO_LABEL,
    LABEL_DESCRIPTIONS,
    LABELS,
    assert_mapping_complete,
    label_for_intent,
)

OUT = ROOT / "data" / "routing" / "requests.jsonl"
SEED = 42
N = 80


def balanced_counts(labels: tuple[str, ...], n: int, pool_sizes: dict[str, int]) -> dict[str, int]:
    """Share n as evenly as possible, extra going to the largest pools."""
    base, extra = divmod(n, len(labels))
    counts = {label: base for label in labels}
    # Deterministic: largest pool first, then label order on ties.
    ranked = sorted(labels, key=lambda lab: (-pool_sizes[lab], lab))
    for label in ranked[:extra]:
        counts[label] += 1
    for label in labels:
        if pool_sizes[label] < counts[label]:
            raise RuntimeError(
                f"{label} has only {pool_sizes[label]} eligible items, need {counts[label]}"
            )
    return counts


def build_sample(parallel: dict, seed: int, n: int) -> tuple[list[dict], dict]:
    known = {item["en"]["intent"] for item in parallel.values()}
    assert_mapping_complete(set(INTENT_TO_LABEL) | set(DROPPED_INTENTS) | known)

    pools: dict[str, list[str]] = defaultdict(list)
    dropped_intent = 0
    dropped_wake = 0
    wake_by_label: Counter[str] = Counter()
    for uid, item in parallel.items():
        label = label_for_intent(item["en"]["intent"])
        if label is None:
            dropped_intent += 1
            continue
        texts = (item["en"]["utt"], item["hi"]["utt"], item["ta"]["utt"])
        if item_has_wake_word(texts):
            dropped_wake += 1
            wake_by_label[label] += 1
            continue
        pools[label].append(uid)

    pool_sizes = {label: len(pools[label]) for label in LABELS}
    counts = balanced_counts(LABELS, n, pool_sizes)
    rng = random.Random(seed)
    chosen: list[str] = []
    for label in LABELS:
        pool = sorted(pools[label], key=lambda i: int(i))
        chosen.extend(rng.sample(pool, counts[label]))
    chosen = sorted(set(chosen), key=lambda i: int(i))
    if len(chosen) != n:
        raise RuntimeError(f"expected {n} ids, got {len(chosen)}")

    records = []
    for seq, uid in enumerate(chosen, start=1):
        item = parallel[uid]
        label = label_for_intent(item["en"]["intent"])
        records.append(
            {
                "id": f"r{seq:03d}",
                "source_id": uid,
                "label": label,
                "intent": item["en"]["intent"],
                "scenario": item["en"]["scenario"],
                "text_en": item["en"]["utt"],
                "text_hi": item["hi"]["utt"],
                "text_ta": item["ta"]["utt"],
                "source": {
                    "dataset": HF_DATASET,
                    "split": "test",
                    "locales": list(LOCALES),
                    "huggingface": f"https://huggingface.co/datasets/{HF_DATASET}",
                    "huggingface_revision": HF_REVISION,
                    "archive": ARCHIVE_URL,
                    "archive_version": ARCHIVE_VERSION,
                    "archive_sha256": ARCHIVE_SHA256,
                    "license": "CC BY 4.0",
                },
            }
        )
    stats = {
        "dropped_intent": dropped_intent,
        "dropped_wake": dropped_wake,
        "wake_by_label": dict(wake_by_label),
        "pool_sizes": pool_sizes,
        "sample_counts": dict(Counter(r["label"] for r in records)),
        "per_label_targets": counts,
        "test_total": len(parallel),
    }
    return records, stats


def print_sanity_examples(records: list[dict], seed: int, k: int = 3) -> None:
    rng = random.Random(seed)
    print("\nSanity check: {k} English examples per option, drawn from the sample with seed {seed}.".format(k=k, seed=seed))
    by = defaultdict(list)
    for rec in records:
        by[rec["label"]].append(rec)
    for label in LABELS:
        group = list(by[label])
        picks = rng.sample(group, min(k, len(group)))
        picks = sorted(picks, key=lambda r: r["id"])
        print(f"\n## {label}")
        print(LABEL_DESCRIPTIONS[label])
        for rec in picks:
            print(f"  {rec['id']}  intent={rec['intent']}  {rec['text_en']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=UPSTREAM_DIR)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--n", type=int, default=N)
    parser.add_argument(
        "--sanity",
        action="store_true",
        help="After writing the sample, print 3 English examples per option.",
    )
    args = parser.parse_args()

    parallel = load_parallel_test(args.upstream)
    records, stats = build_sample(parallel, args.seed, args.n)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} rows to {args.out}")
    print("sample counts:", stats["sample_counts"])
    print("per-label targets:", stats["per_label_targets"])
    print("eligible pool sizes after filters:", stats["pool_sizes"])
    print("test items:", stats["test_total"])
    print("dropped as unmapped intent:", stats["dropped_intent"])
    print("dropped by wake-word filter (among mapped intents):", stats["dropped_wake"], stats["wake_by_label"])
    print("source_id range:", records[0]["source_id"], "to", records[-1]["source_id"])
    print("intents in sample:", dict(Counter(r["intent"] for r in records)))
    if args.sanity:
        print_sanity_examples(records, args.seed, 3)


if __name__ == "__main__":
    main()
