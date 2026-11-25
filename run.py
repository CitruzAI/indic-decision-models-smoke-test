#!/usr/bin/env python3
"""Indic decision-models smoke test runner.

Default is a dry run: tokenize, estimate cost, write request previews.
No inference POST is sent unless you pass both --live and --max-usd after spend
is approved in Kamal's own words. --max-usd is a cumulative cap across OpenRouter
models. Sarvam Prism is billed in INR under --max-inr and is outside the USD cap.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from indic_smoke.backends import openrouter_chat, openrouter_decisions, sarvam
from indic_smoke.config import ModelSpec, by_key, registry
from indic_smoke.estimate import estimate_all, load_reviews, money
from indic_smoke.http import env_key
from indic_smoke.metrics import summarize
from indic_smoke.prompts import LABELS
from indic_smoke.tokenize_approx import token_report

DATA_PATH = ROOT / "data" / "reviews.jsonl"
ESTIMATE_PATH = ROOT / "estimates" / "cost_estimate.json"
RESULTS_DIR = ROOT / "results"
IST = timezone(timedelta(hours=5, minutes=30))

# Cheap first; mandatory-reasoning chat models last. Sarvam is not in this
# list; it runs separately in INR after the OpenRouter lineup.
LIVE_ORDER = (
    "pplx-flash",
    "pplx-full",
    "groundhog",
    "jev",
    "msdecision",
    "deepseek",
    "bison",
    "gpt-luna",
    "qwen",
    "gemini",
    "gpt-sol",
)

ADAPTERS = {
    ("openrouter", "decisions"): openrouter_decisions,
    ("openrouter", "chat"): openrouter_chat,
    ("sarvam", "decisions"): sarvam,
}

LANG_FIELDS = (("en", "text_en"), ("hi", "text_hi"), ("ta", "text_ta"))
DEFAULT_MAX_INR = Decimal("50")


def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST (Asia/Calcutta)")


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


def work_items(reviews: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str, str]]:
    items = []
    for row in reviews:
        for lang, field in LANG_FIELDS:
            items.append((row, lang, field))
    return items


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def prior_openrouter_spend(out_dir: Path, specs: list[ModelSpec]) -> Decimal:
    spent = Decimal("0")
    for spec in specs:
        for row in load_jsonl(out_dir / f"{spec.key}.jsonl"):
            if row.get("cost_usd") is not None:
                spent += Decimal(str(row["cost_usd"]))
    return spent


def fallback_cost(spec: ModelSpec, usage: dict[str, Any] | None) -> tuple[Decimal | None, str]:
    """Use usage.cost when present. Otherwise price listed tokens, flagged as fallback."""
    if usage and usage.get("cost") is not None:
        return Decimal(str(usage["cost"])), "usage.cost"
    if not usage or spec.prompt_usd_per_token is None:
        return None, "missing"
    prompt_toks = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    completion_toks = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    cost = spec.prompt_usd_per_token * Decimal(int(prompt_toks))
    if spec.completion_usd_per_token is not None:
        cost += spec.completion_usd_per_token * Decimal(int(completion_toks))
    reasoning_toks = 0
    details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
    if isinstance(details, dict):
        reasoning_toks = int(details.get("reasoning_tokens") or 0)
    # reasoning tokens are typically already inside completion_tokens; do not double-count.
    _ = reasoning_toks
    cost += spec.request_usd
    return cost, "tokens_x_list_price"


def dry_run(reviews: list[dict[str, Any]], specs: list[ModelSpec], out_dir: Path) -> dict[str, Any]:
    previews = []
    for spec in specs:
        sample_text = reviews[0]["text_en"]
        adapter = ADAPTERS[(spec.provider, spec.family)]
        body = adapter.build_request(spec, sample_text)
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


def _call_with_retries(adapter: Any, spec: ModelSpec, text: str, *, max_retries: int) -> dict[str, Any]:
    result: dict[str, Any] | None = None
    attempts = max_retries + 1
    for attempt in range(1, attempts + 1):
        result = adapter.infer(spec, text)
        status = result.get("http_status")
        if status == 429 or (status is not None and status >= 500):
            if attempt >= attempts:
                break
            wait = min(30, 2 ** attempt)
            print(f"  http {status}, retry in {wait}s (attempt {attempt}/{attempts})")
            time.sleep(wait)
            continue
        break
    assert result is not None
    return result


def live_run_model(
    reviews: list[dict[str, Any]],
    spec: ModelSpec,
    max_usd: Decimal,
    spent: Decimal,
    out_dir: Path,
    estimates: dict[str, Any],
) -> tuple[dict[str, Any], Decimal]:
    """Run one OpenRouter model under a shared cumulative USD cap."""
    reason = blocked_reason(spec)
    if reason:
        summary = {
            "status": "skipped",
            "model_id": spec.model_id,
            "key": spec.key,
            "reason": reason,
            "spent_usd_before": money(spent),
        }
        write_json(out_dir / f"{spec.key}.summary.json", summary)
        return summary, spent

    remaining = max_usd - spent
    model_est = next((m for m in estimates["models"] if m["model_id"] == spec.model_id), None)
    mandatory_reasoning = bool((spec.reasoning or {}).get("mandatory"))
    jsonl_path = out_dir / f"{spec.key}.jsonl"
    existing = load_jsonl(jsonl_path)
    items = work_items(reviews)
    done = {(row["id"], row["lang"]) for row in existing}
    todo = [(row, lang, field) for row, lang, field in items if (row["id"], lang) not in done]

    if todo and model_est and model_est.get("total_usd") is not None:
        est = Decimal(model_est["total_usd"])
        if est > remaining:
            summary = {
                "status": "skipped",
                "model_id": spec.model_id,
                "key": spec.key,
                "reason": (
                    f"Remaining budget ${money(remaining)} is below the "
                    f"{'complete' if model_est['estimate_complete'] else 'prompt-only'} "
                    f"estimate ${money(est)}."
                ),
                "spent_usd_before": money(spent),
                "partial": False,
            }
            write_json(out_dir / f"{spec.key}.summary.json", summary)
            return summary, spent
    if todo and mandatory_reasoning and remaining < Decimal("0.05"):
        summary = {
            "status": "skipped",
            "model_id": spec.model_id,
            "key": spec.key,
            "reason": (
                f"Remaining budget ${money(remaining)} is too small to start "
                "a mandatory-reasoning model safely."
            ),
            "spent_usd_before": money(spent),
            "partial": False,
        }
        write_json(out_dir / f"{spec.key}.summary.json", summary)
        return summary, spent

    adapter = ADAPTERS[(spec.provider, spec.family)]
    started_at = now_ist()
    rows = list(existing)
    model_spend = sum(
        (Decimal(str(r["cost_usd"])) for r in existing if r.get("cost_usd") is not None),
        Decimal("0"),
    )
    last_item_cost: Decimal | None = None
    returned_ids: set[str] = set()
    for r in existing:
        if r.get("returned_model"):
            returned_ids.add(str(r["returned_model"]))
    aborted: str | None = None

    for row, lang, field in todo:
        remaining = max_usd - spent
        if last_item_cost is not None:
            buffer = last_item_cost * Decimal("1.5")
        elif mandatory_reasoning:
            buffer = Decimal("0.10")
        else:
            buffer = Decimal("0.002")
        if remaining <= buffer:
            aborted = (
                f"Stopped before {row['id']}/{lang}: remaining ${money(remaining)} "
                f"is at or below the safety buffer ${money(buffer)} (cap ${money(max_usd)})."
            )
            break

        result = _call_with_retries(adapter, spec, row[field], max_retries=4)
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else None
        cost, cost_source = fallback_cost(spec, usage)
        if result.get("cost_usd") is not None:
            cost = Decimal(str(result["cost_usd"]))
            cost_source = "usage.cost"
        if cost is None and spec.prompt_usd_per_token == Decimal("0"):
            cost = Decimal("0")
            cost_source = "listed_free"
        if cost is not None:
            spent += cost
            model_spend += cost
            last_item_cost = cost

        returned = result.get("model") or (usage or {}).get("model")
        rec = {
            "id": row["id"],
            "lang": lang,
            "gold": row["label"],
            "text": row[field],
            "pred": result.get("pred"),
            "probs": result.get("probs"),
            "latency_ms": result.get("latency_ms"),
            "cost_usd": float(cost) if cost is not None else None,
            "cost_source": cost_source,
            "error": result.get("error"),
            "http_status": result.get("http_status"),
            "returned_model": returned,
        }
        rows.append(rec)
        if returned:
            returned_ids.add(str(returned))
        mark = "ok" if rec["pred"] == rec["gold"] else "miss"
        print(
            f"  {spec.key} {row['id']}/{lang} {mark} gold={row['label']} pred={rec['pred']} "
            f"item=${money(cost) if cost is not None else 'n/a'} "
            f"spent=${money(spent)}/{money(max_usd)}"
        )
        if len(rows) % 5 == 0:
            write_jsonl(jsonl_path, rows)
        if cost is not None and spent >= max_usd:
            aborted = (
                f"Stopped after {row['id']}/{lang}: cumulative spend ${money(spent)} "
                f"reached the ${money(max_usd)} cap. Actual billed cost is included."
            )
            break

    write_jsonl(jsonl_path, rows)
    scored = [r for r in rows if r.get("pred") is not None and not r.get("error")]
    metrics = summarize(scored, LABELS) if scored else None
    n_planned = len(items)
    n_done = len(rows)
    n_scored = len(scored)
    if aborted and n_done < n_planned:
        status = "partial"
    elif any(r.get("error") for r in rows) or n_scored < n_done:
        status = "ran_with_errors"
    else:
        status = "ran"
    summary = {
        "status": status,
        "model_id": spec.model_id,
        "key": spec.key,
        "returned_model_ids": sorted(returned_ids),
        "started_at_ist": started_at,
        "finished_at_ist": now_ist(),
        "n_planned": n_planned,
        "n_recorded": n_done,
        "n_scored": n_scored,
        "partial": n_done < n_planned,
        "abort_reason": aborted,
        "spent_usd_this_model": money(model_spend),
        "spent_usd_cumulative_after": money(spent),
        "max_usd": money(max_usd),
        "metrics": metrics,
        "rows_path": f"results/{spec.key}.jsonl",
    }
    write_json(out_dir / f"{spec.key}.summary.json", summary)
    return summary, spent


def live_run_sarvam(
    reviews: list[dict[str, Any]],
    spec: ModelSpec,
    max_inr: Decimal,
    out_dir: Path,
) -> dict[str, Any]:
    """Run Sarvam Prism under a separate INR cap. Outside the OpenRouter USD total."""
    reason = blocked_reason(spec)
    if reason:
        summary = {
            "status": "skipped",
            "model_id": spec.model_id,
            "key": spec.key,
            "reason": reason,
            "currency": "INR",
        }
        write_json(out_dir / f"{spec.key}.summary.json", summary)
        return summary

    adapter = ADAPTERS[(spec.provider, spec.family)]
    jsonl_path = out_dir / f"{spec.key}.jsonl"
    existing = load_jsonl(jsonl_path)
    items = work_items(reviews)
    done = {(row["id"], row["lang"]) for row in existing}
    todo = [(row, lang, field) for row, lang, field in items if (row["id"], lang) not in done]
    rows = list(existing)
    spent = sum(
        (Decimal(str(r["cost_inr"])) for r in existing if r.get("cost_inr") is not None),
        Decimal("0"),
    )
    last_item_cost: Decimal | None = None
    returned_ids: set[str] = set()
    for r in existing:
        if r.get("returned_model"):
            returned_ids.add(str(r["returned_model"]))
    aborted: str | None = None
    started_at = now_ist()

    for row, lang, field in todo:
        remaining = max_inr - spent
        buffer = last_item_cost * Decimal("1.5") if last_item_cost is not None else Decimal("1")
        if remaining <= buffer or spent >= max_inr:
            aborted = (
                f"Stopped before {row['id']}/{lang}: remaining ₹{money(remaining)} "
                f"is at or below the safety buffer ₹{money(buffer)} (cap ₹{money(max_inr)})."
            )
            break

        # At most a couple of retries, and only on 429 / 5xx.
        result = _call_with_retries(adapter, spec, row[field], max_retries=2)
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else None
        cost = None
        cost_source = "missing"
        if result.get("cost_inr") is not None:
            cost = Decimal(str(result["cost_inr"]))
            cost_source = result.get("cost_source") or "usage_tokens_x_listed_inr_4_per_1m"
        if cost is not None:
            spent += cost
            last_item_cost = cost
        returned = result.get("model")
        rec = {
            "id": row["id"],
            "lang": lang,
            "gold": row["label"],
            "text": row[field],
            "pred": result.get("pred"),
            "probs": result.get("probs"),
            "latency_ms": result.get("latency_ms"),
            "cost_usd": None,
            "cost_inr": float(cost) if cost is not None else None,
            "cost_source": cost_source,
            "error": result.get("error"),
            "http_status": result.get("http_status"),
            "returned_model": returned,
            "usage": usage,
        }
        rows.append(rec)
        if returned:
            returned_ids.add(str(returned))
        mark = "ok" if rec["pred"] == rec["gold"] else "miss"
        print(
            f"  sarvam {row['id']}/{lang} {mark} gold={row['label']} pred={rec['pred']} "
            f"item=₹{money(cost) if cost is not None else 'n/a'} "
            f"spent=₹{money(spent)}/{money(max_inr)} status={rec.get('http_status')}"
            + (f" error={rec['error']}" if rec.get("error") else "")
        )
        write_jsonl(jsonl_path, rows)
        # 4xx (except 429) is a hard failure: do not keep hammering.
        status = rec.get("http_status")
        if rec.get("error") and status is not None and status != 429 and status < 500:
            aborted = f"Stopped after {row['id']}/{lang}: {rec['error']}"
            break
        if spent >= max_inr:
            aborted = (
                f"Stopped after {row['id']}/{lang}: cumulative spend ₹{money(spent)} "
                f"reached the ₹{money(max_inr)} cap."
            )
            break

    write_jsonl(jsonl_path, rows)
    scored = [r for r in rows if r.get("pred") is not None and not r.get("error")]
    metrics = summarize(scored, LABELS) if scored else None
    n_planned = len(items)
    n_done = len(rows)
    if aborted and n_done < n_planned:
        status_s = "partial" if scored else "error"
    elif any(r.get("error") for r in rows):
        status_s = "ran_with_errors"
    else:
        status_s = "ran"
    summary = {
        "status": status_s,
        "model_id": spec.model_id,
        "key": spec.key,
        "currency": "INR",
        "returned_model_ids": sorted(returned_ids),
        "started_at_ist": started_at,
        "finished_at_ist": now_ist(),
        "n_planned": n_planned,
        "n_recorded": n_done,
        "n_scored": len(scored),
        "partial": n_done < n_planned,
        "abort_reason": aborted,
        "spent_inr": money(spent),
        "max_inr": money(max_inr),
        "cost_note": "Listed rate ₹4/1M input applied to usage prompt tokens. Outside the OpenRouter $2 cap.",
        "metrics": metrics,
        "rows_path": f"results/{spec.key}.jsonl",
    }
    write_json(out_dir / f"{spec.key}.summary.json", summary)
    return summary


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


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    q = Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return format(q, "f")


def _ms(value: float | None) -> str:
    if value is None:
        return "—"
    q = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(q, "f")


def format_results_table(summaries: list[dict[str, Any]], specs_by_key: dict[str, ModelSpec]) -> str:
    headers = [
        "Model",
        "Status",
        "n",
        "Acc. en",
        "Acc. hi",
        "Acc. ta",
        "hi−en",
        "ta−en",
        "p50 ms",
        "p95 ms",
        "Actual cost",
        "Acc. at p≥0.9 (n)",
        "Acc. at p<0.9 (n)",
        "Brier",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for s in summaries:
        spec = specs_by_key.get(s.get("key") or "")
        name = spec.display_name if spec else s.get("model_id") or s.get("key")
        mid = s.get("model_id") or ""
        label = f"{name} (`{mid}`)"
        metrics = s.get("metrics") or {}
        acc = metrics.get("accuracy_by_language") or {}
        drops = metrics.get("drops") or {}
        lat = metrics.get("latency") or {}
        calib = metrics.get("calibration")
        n_plan = s.get("n_planned") or 240
        n_rec = s.get("n_scored") if s.get("n_scored") is not None else s.get("n_recorded")
        if n_rec is None:
            n_cell = "—"
        elif n_rec == n_plan and n_plan == 240:
            n_cell = "80 × 3"
        else:
            n_cell = f"{n_rec} / {n_plan}"
        if s.get("currency") == "INR":
            cost_cell = f"₹{s.get('spent_inr')} (INR, outside $2 cap)" if s.get("spent_inr") is not None else "—"
        elif s.get("spent_usd_this_model") is not None:
            cost_cell = f"${s.get('spent_usd_this_model')}"
        else:
            cost_cell = "—"
        if calib:
            high = calib["accuracy_at_p_0_9"]["ge_threshold"]
            low = calib["accuracy_at_p_0_9"]["lt_threshold"]
            high_cell = "—" if not high["n"] else f"{_pct(high['accuracy'])} (n={high['n']})"
            low_cell = "—" if not low["n"] else f"{_pct(low['accuracy'])} (n={low['n']})"
            brier_cell = _pct(calib.get("brier"))
        else:
            high_cell = "—"
            low_cell = "—"
            brier_cell = "—"
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    s.get("status") or "—",
                    n_cell,
                    _pct(acc.get("en")),
                    _pct(acc.get("hi")),
                    _pct(acc.get("ta")),
                    _pct(drops.get("hi_minus_en")),
                    _pct(drops.get("ta_minus_en")),
                    _ms(lat.get("p50_ms")),
                    _ms(lat.get("p95_ms")),
                    cost_cell,
                    high_cell,
                    low_cell,
                    brier_cell,
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--dry-run", action="store_true", help="No inference POSTs. Default if --live is absent.")
    parser.add_argument("--estimate", action="store_true", help="Write the cost estimate (implied by --dry-run).")
    parser.add_argument("--live", action="store_true", help="Make billed inference calls. Requires --max-usd.")
    parser.add_argument("--max-usd", type=Decimal, default=None, help="Hard cumulative OpenRouter spend cap.")
    parser.add_argument(
        "--max-inr",
        type=Decimal,
        default=DEFAULT_MAX_INR,
        help="Hard Sarvam INR cap (default 50). Outside the OpenRouter USD cap.",
    )
    parser.add_argument(
        "--model",
        default="all",
        help="Model key or id, or 'all' (dry-run, or live in cheap-first order plus Sarvam).",
    )
    args = parser.parse_args()

    reviews = load_reviews(args.data)
    if len(reviews) != 80:
        raise SystemExit(f"expected 80 reviews, found {len(reviews)}")

    if args.live:
        if args.max_usd is None:
            raise SystemExit("Refusing --live without --max-usd.")
        import indic_smoke.http as http

        estimates = estimate_all(reviews)
        if args.model == "all":
            or_specs = [by_key(k) for k in LIVE_ORDER]
            run_sarvam = True
        else:
            spec = by_key(args.model)
            or_specs = [] if spec.provider == "sarvam" else [spec]
            run_sarvam = spec.provider == "sarvam"

        spent = prior_openrouter_spend(RESULTS_DIR, or_specs if or_specs else [by_key(k) for k in LIVE_ORDER])
        summaries: list[dict[str, Any]] = []
        started = now_ist()
        http.INFERENCE_POSTS_ENABLED = True
        try:
            for spec in or_specs:
                print(f"== {spec.model_id}  spent=${money(spent)}/{money(args.max_usd)}  {now_ist()} ==")
                summary, spent = live_run_model(
                    reviews, spec, args.max_usd, spent, RESULTS_DIR, estimates
                )
                summaries.append(summary)
                print(
                    f"   status={summary.get('status')} model_spend={summary.get('spent_usd_this_model')} "
                    f"reason={summary.get('reason') or summary.get('abort_reason')}"
                )
            if run_sarvam:
                sarvam_spec = by_key("sarvam")
                print(f"== {sarvam_spec.model_id}  INR cap ₹{money(args.max_inr)}  {now_ist()} ==")
                s_summary = live_run_sarvam(reviews, sarvam_spec, args.max_inr, RESULTS_DIR)
                summaries.append(s_summary)
                print(
                    f"   status={s_summary.get('status')} spend_inr={s_summary.get('spent_inr')} "
                    f"reason={s_summary.get('reason') or s_summary.get('abort_reason')}"
                )
        finally:
            http.INFERENCE_POSTS_ENABLED = False
        bundle = {
            "started_at_ist": started,
            "finished_at_ist": now_ist(),
            "max_usd": money(args.max_usd),
            "spent_usd_cumulative_openrouter": money(spent),
            "max_inr_sarvam": money(args.max_inr),
            "models": summaries,
        }
        write_json(RESULTS_DIR / "run_summary.json", bundle)
        print(json.dumps({k: bundle[k] for k in bundle if k != "models"}, indent=2))
        for s in summaries:
            if s.get("currency") == "INR":
                print(
                    f"- {s.get('model_id')}: {s.get('status')} n={s.get('n_recorded')}/{s.get('n_planned')} "
                    f"cost=₹{s.get('spent_inr')}"
                )
            else:
                print(
                    f"- {s.get('model_id')}: {s.get('status')} n={s.get('n_recorded')}/{s.get('n_planned')} "
                    f"cost=${s.get('spent_usd_this_model')}"
                )
        print("\nResults table:\n")
        print(format_results_table(summaries, {s.key: s for s in registry()}))
        return

    specs = registry() if args.model == "all" else [by_key(args.model)]
    result = dry_run(reviews, specs, ROOT / "estimates")
    table = format_estimate_table(result["estimate"])
    print(table)
    print(f"\nWrote {ESTIMATE_PATH}")
    for preview in result["previews"]:
        if preview["blocked"]:
            print(f"blocked: {preview['model_id']}: {preview['blocked']}")
        else:
            print(f"ready: {preview['model_id']}")


if __name__ == "__main__":
    main()
