"""Accuracy, language drops, latency, and calibration. Used once a live run exists."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

LANGS = ("en", "hi", "ta")


def _percentile(sorted_values: Sequence[float], p: float) -> float:
    if not sorted_values:
        raise ValueError("percentile of empty sequence")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (p / 100.0) * (len(sorted_values) - 1)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return float(sorted_values[lo])
    w = k - lo
    return float(sorted_values[lo]) * (1.0 - w) + float(sorted_values[hi]) * w


def accuracy(golds: Sequence[str], preds: Sequence[str]) -> float:
    if not golds or len(golds) != len(preds):
        raise ValueError("accuracy requires non-empty equal-length sequences")
    return sum(g == p for g, p in zip(golds, preds)) / len(golds)


def multiclass_brier(
    golds: Sequence[str],
    prob_maps: Sequence[Mapping[str, float]],
    labels: Sequence[str],
) -> float:
    total = 0.0
    for gold, probs in zip(golds, prob_maps):
        for label in labels:
            p = float(probs[label])
            y = 1.0 if label == gold else 0.0
            total += (p - y) ** 2
    return total / len(golds)


def accuracy_at_confidence(
    golds: Sequence[str],
    preds: Sequence[str],
    confidences: Sequence[float],
    threshold: float = 0.9,
) -> dict[str, Any]:
    high_ok = high_n = low_ok = low_n = 0
    for gold, pred, conf in zip(golds, preds, confidences):
        correct = gold == pred
        if conf >= threshold:
            high_n += 1
            high_ok += int(correct)
        else:
            low_n += 1
            low_ok += int(correct)
    return {
        "threshold": threshold,
        "ge_threshold": {
            "n": high_n,
            "correct": high_ok,
            "accuracy": (high_ok / high_n) if high_n else None,
        },
        "lt_threshold": {
            "n": low_n,
            "correct": low_ok,
            "accuracy": (low_ok / low_n) if low_n else None,
        },
    }


def summarize(rows: Iterable[Mapping[str, Any]], labels: Sequence[str]) -> dict[str, Any]:
    """rows must include id, lang, gold, pred, and optionally probs, confidence, latency_ms, cost_usd."""
    rows = list(rows)
    by_lang: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_lang[row["lang"]].append(row)

    acc_by_lang: dict[str, float] = {}
    for lang in LANGS:
        group = by_lang.get(lang) or []
        if group:
            acc_by_lang[lang] = accuracy([r["gold"] for r in group], [r["pred"] for r in group])

    drops = {}
    if "en" in acc_by_lang:
        if "hi" in acc_by_lang:
            drops["hi_minus_en"] = acc_by_lang["hi"] - acc_by_lang["en"]
        if "ta" in acc_by_lang:
            drops["ta_minus_en"] = acc_by_lang["ta"] - acc_by_lang["en"]

    latencies = [float(r["latency_ms"]) for r in rows if r.get("latency_ms") is not None]
    latency = None
    if latencies:
        ordered = sorted(latencies)
        latency = {
            "n": len(ordered),
            "p50_ms": _percentile(ordered, 50),
            "p95_ms": _percentile(ordered, 95),
            "min_ms": ordered[0],
            "max_ms": ordered[-1],
            "mean_ms": sum(ordered) / len(ordered),
            "definition": "Wall-clock time per request, after any client-side warmup, covering the network call.",
        }

    costs = [float(r["cost_usd"]) for r in rows if r.get("cost_usd") is not None]
    cost = None
    if costs:
        cost = {
            "n": len(costs),
            "total_usd": sum(costs),
            "source": "OpenRouter usage.cost (or equivalent billed field) from each response. Never estimated after the fact.",
        }

    # Calibration only when a probability vector is present (decision models or logprobs).
    # Self-reported verbal confidence is ignored.
    calib_rows = [r for r in rows if r.get("probs")]
    calibration = None
    if calib_rows:
        golds = [r["gold"] for r in calib_rows]
        preds = [r["pred"] for r in calib_rows]
        confs = [max(r["probs"].values()) for r in calib_rows]
        calibration = {
            "n": len(calib_rows),
            "probability_source": "model probability vector (decision-model probabilities, or softmax over logprobs). Self-reported confidence is not used.",
            "brier": multiclass_brier(golds, [r["probs"] for r in calib_rows], labels),
            "accuracy_at_p_0_9": accuracy_at_confidence(golds, preds, confs, 0.9),
        }

    return {
        "n_rows": len(rows),
        "accuracy_by_language": acc_by_lang,
        "drops": drops,
        "latency": latency,
        "cost": cost,
        "calibration": calibration,
    }
