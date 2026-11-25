#!/usr/bin/env python3
"""Indic decision-models smoke test runner.

Phase 1 default is a dry run: tokenize, estimate cost, write request previews.
No inference POST is sent unless you pass both --live and --max-usd after spend
is approved in Kamal's own words.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from indic_smoke.backends import baseten, openrouter_chat, openrouter_decisions, sarvam
from indic_smoke.config import ModelSpec, by_key, registry
from indic_smoke.estimate import estimate_all, load_reviews, money
from indic_smoke.http import env_key
from indic_smoke.metrics import summarize
from indic_smoke.prompts import LABELS
from indic_smoke.tokenize_approx import token_report

DATA_PATH = ROOT / "data" / "reviews.jsonl"
ESTIMATE_PATH = ROOT / "estimates" / "cost_estimate.json"
RESULTS_DIR = ROOT / "results"

ADAPTERS = {
    ("openrouter", "decisions"): openrouter_decisions,
    ("openrouter", "chat"): openrouter_chat,
    ("sarvam", "decisions"): sarvam,
    ("baseten", "decisions"): baseten,
}


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def blocked_reason(spec: ModelSpec) -> str | None:
    if not spec.runnable_id_confirmed:
        return (
            f"OpenRouter id {spec.model_id!r} was not confirmed as runnable "
            "(model record exists but the endpoints list is empty)."
        )
    if not env_key(spec.auth_env):
        return f"{spec.auth_env} is not set in the current environment."
    return None


def dry_run(reviews: list[dict[str, Any]], specs: list[ModelSpec], out_dir: Path) -> dict[str, Any]:
    previews = []
    for spec in specs:
        # One English preview is enough to show the request shape without dumping 240 bodies.
        sample_text = reviews[0]["text_en"]
        adapter = ADAPTERS[(spec.provider, spec.family)]
        body = adapter.build_request(spec, sample_text)
        # Strip nothing from the body; it contains only the public review text.
        report = token_report(sample_text)
        previews.append(
            {
                "key": spec.key,
                "model_id": spec.model_id,
                "endpoint": spec.endpoint,
                "blocked": blocked_reason(spec),
                "sample_request_preview": body,
                "sample_token_approx_en": report,
            }
        )
    estimate = estimate_all(reviews)
    write_json(out_dir / "cost_estimate.json", estimate)
    write_json(out_dir / "dry_run_previews.json", {"previews": previews})
    return {"estimate": estimate, "previews": previews}


def live_run(
    reviews: list[dict[str, Any]],
    spec: ModelSpec,
    max_usd: Decimal,
    out_dir: Path,
) -> dict[str, Any]:
    import indic_smoke.http as http

    reason = blocked_reason(spec)
    if reason:
        raise SystemExit(f"Cannot live-run {spec.model_id}: {reason}")
    if not spec.price_found and spec.provider == "openrouter":
        raise SystemExit(
            f"Refusing to live-run {spec.model_id}: no confirmed USD price, cannot enforce --max-usd."
        )

    # Conservative preflight: if we have a complete or prompt-only estimate, require it to fit.
    estimate = estimate_all(reviews)
    model_est = next(m for m in estimate["models"] if m["model_id"] == spec.model_id)
    if model_est["total_usd"] is not None:
        est = Decimal(model_est["total_usd"])
        if model_est["estimate_complete"] and est > max_usd:
            raise SystemExit(
                f"Abort: complete estimate ${est} for {spec.model_id} exceeds --max-usd {max_usd}."
            )
        if (not model_est["estimate_complete"]) and est > max_usd:
            raise SystemExit(
                f"Abort: even the prompt-only estimate ${est} for {spec.model_id} exceeds --max-usd {max_usd}."
            )

    http.INFERENCE_POSTS_ENABLED = True
    adapter = ADAPTERS[(spec.provider, spec.family)]
    spent = Decimal("0")
    rows: list[dict[str, Any]] = []
    try:
        for item in reviews:
            for lang, field in (("en", "text_en"), ("hi", "text_hi"), ("ta", "text_ta")):
                if spent >= max_usd:
                    raise SystemExit(
                        f"Abort: spend cap reached (${money(spent)} / ${money(max_usd)}) before "
                        f"{item['id']}/{lang}."
                    )
                result = adapter.infer(spec, item[field])
                cost = result.get("cost_usd")
                if cost is not None:
                    spent += Decimal(str(cost))
                    if spent > max_usd:
                        raise SystemExit(
                            f"Abort: spend cap exceeded during {item['id']}/{lang} "
                            f"(${money(spent)} / ${money(max_usd)})."
                        )
                rows.append(
                    {
                        "id": item["id"],
                        "lang": lang,
                        "gold": item["label"],
                        "text": item[field],
                        "pred": result.get("pred"),
                        "probs": result.get("probs"),
                        "latency_ms": result.get("latency_ms"),
                        "cost_usd": cost,
                        "error": result.get("error"),
                        "http_status": result.get("http_status"),
                    }
                )
                mark = "ok" if result.get("pred") == item["label"] else "miss"
                print(
                    f"  {item['id']}/{lang} {mark} gold={item['label']} pred={result.get('pred')} "
                    f"spent=${money(spent)}"
                )
    finally:
        http.INFERENCE_POSTS_ENABLED = False

    metrics = summarize(rows, LABELS)
    bundle = {
        "model_id": spec.model_id,
        "max_usd": money(max_usd),
        "spent_usd_from_usage_fields": money(spent),
        "metrics": metrics,
        "rows_path": f"results/{spec.key}.jsonl",
    }
    out_jsonl = out_dir / f"{spec.key}.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_json(out_dir / f"{spec.key}.summary.json", bundle)
    return bundle


def format_estimate_table(estimate: dict[str, Any]) -> str:
    headers = [
        "Model",
        "OpenRouter / API id",
        "Prompt tokens (approx.)",
        "Listed price (input / output)",
        "Est. USD",
        "Complete?",
        "Notes",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for m in estimate["models"]:
        if m["prompt_usd_per_1m"] is not None:
            price = f"${m['prompt_usd_per_1m']}/1M in, ${m['completion_usd_per_1m']}/1M out"
        elif m["key"] == "sarvam":
            price = "₹4/1M in, ₹0 out (no official USD)"
        else:
            price = "not found"
        est = "—" if m["total_usd"] is None else f"${m['total_usd']}"
        if m["total_usd"] is not None and not m["estimate_complete"]:
            est += " (prompt only)"
        complete = "yes" if m["estimate_complete"] else "no"
        note = m.get("incomplete_reason") or (m["notes"][0] if m["notes"] else "")
        lines.append(
            "| "
            + " | ".join(
                [
                    m["display_name"],
                    m["model_id"],
                    str(m["prompt_tokens_total"]),
                    price,
                    est,
                    complete,
                    note.replace("|", "/"),
                ]
            )
            + " |"
        )
    totals = estimate["totals"]
    lines.append("")
    lines.append(
        f"Headline USD total (complete estimates + prompt-only for incomplete priced models): "
        f"${totals['usd_headline_complete_plus_prompt_of_incomplete']}."
    )
    lines.append(
        f"Excluded from that total: {', '.join(totals['excluded_from_usd_total']) or 'none'}."
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--dry-run", action="store_true", help="No inference POSTs. Default if --live is absent.")
    parser.add_argument("--estimate", action="store_true", help="Write the cost estimate (implied by --dry-run).")
    parser.add_argument("--live", action="store_true", help="Make billed inference calls. Requires --max-usd.")
    parser.add_argument("--max-usd", type=Decimal, default=None, help="Hard spend cap. Aborts the run if exceeded.")
    parser.add_argument("--model", default="all", help="Model key or id, or 'all' for dry-run/estimate.")
    args = parser.parse_args()

    reviews = load_reviews(args.data)
    if len(reviews) != 80:
        raise SystemExit(f"expected 80 reviews, found {len(reviews)}")

    if args.live:
        if args.max_usd is None:
            raise SystemExit("Refusing --live without --max-usd.")
        if args.model == "all":
            raise SystemExit("Refusing --live --model all. Choose one model at a time.")
        spec = by_key(args.model)
        print(f"Live run of {spec.model_id} with cap ${money(args.max_usd)}")
        bundle = live_run(reviews, spec, args.max_usd, RESULTS_DIR)
        print(json.dumps(bundle["metrics"], indent=2))
        return

    # Dry run / estimate (phase 1).
    specs = registry() if args.model == "all" else [by_key(args.model)]
    result = dry_run(reviews, specs, ROOT / "estimates")
    table = format_estimate_table(result["estimate"])
    print(table)
    print(f"\nWrote {ESTIMATE_PATH}")
    for preview in result["previews"]:
        if preview["blocked"]:
            print(f"blocked: {preview['model_id']}: {preview['blocked']}")


if __name__ == "__main__":
    main()
