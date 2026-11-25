# Indic decision-models smoke test

How do System One decision models, and general LLMs used as deciders, hold up on **Hindi and Tamil** versus **English**?

This is a **smoke test, n=80 items × 3 languages = 240 texts per model**, not a benchmark. Every later number in a results table must come from a run recorded in `results/`. This commit ships the harness, the fixed sample, and a **cost estimate**. No inference call has been made yet.

Proposed public repo name (not created, not pushed): **CitruzAI/indic-decision-models-smoke-test**.

## Thesis

A review that is Positive or Negative in English has a human-translated Hindi and Tamil counterpart, with the same label. If a model is a reliable decider, its accuracy should not drop much when the text is in Hindi or Tamil.

We measure, once a live run is approved:

- accuracy per language (en, hi, ta)
- the hi−en and ta−en accuracy drops
- p50 and p95 latency
- actual cost from OpenRouter `usage.cost` fields (never an invented post-hoc cost). Sarvam Prism is reported separately in INR, outside the OpenRouter total.
- Brier score, and accuracy at probability ≥ 0.9 versus below, **only** when the model returns a probability vector (decision-model `probabilities`, or a softmax over logprobs). Self-reported confidence in a JSON field is not comparable and is not used.

## What System One models are

System One models (TypeSafe’s name, after Kahneman’s fast judgements) do not write a reply. You send a **state** (the document to judge) and one or more typed **questions**. The model returns a structured answer and a probability for every allowed option.

The primitives used in the public docs are:

- **choice** — pick one of a named set of options, with a probability for each
- **noul** — yes/no, as the probability of true
- **score** — an ordered scale
- **box** — a region in an image (Jev 1.14; not used here)

That is a different interface from chatting with an LLM and asking it to “reply with Positive or Negative.” The LLMs in this test are used *as* deciders: constrained structured output, and logprobs where the provider actually supports them.

## Dataset

80 of the 998 labeled items in the **IndicSentiment** test split (AI4Bharat), seed 42, same source indices in English, Hindi, and Tamil. Choice: `Positive` / `Negative`. The sample has 42 Positive and 38 Negative reviews.

Verified counts in Hugging Face revision `dc8f3f66886531c6897fedffca1e938a68fc5013`:

- The paper lists a test size of 1,000. Each of `data/test/hi.json` and `data/test/ta.json` has 1,000 rows.
- 998 rows are labeled (`Positive` 506, `Negative` 492). 2 rows have `LABEL: null` (source indices 663 and 694) and were excluded before sampling.
- There is no `en.json`. English is the shared `ENGLISH REVIEW` field. Hindi and Tamil are perfectly row-aligned on English text and on the label.

License, documented rather than assumed:

- The Hugging Face card and Hub API for `ai4bharat/IndicSentiment` have **no license field**.
- arXiv:2212.05409 (ethics statement) and the [IndicBERT README](https://github.com/AI4Bharat/IndicBERT) both say the datasets from that work are released under **CC-0**.
- The MTEB mirror `mteb/IndicSentiment` declares `cc0-1.0`.

Full notes: [`data/SOURCE.md`](data/SOURCE.md). The sample is [`data/reviews.jsonl`](data/reviews.jsonl). CC-0 text: [`licenses/CC0-1.0.txt`](licenses/CC0-1.0.txt).

## Request formats (verified from public docs)

**OpenRouter decision models** use the Decisions API, not chat completions:

`POST https://openrouter.ai/api/alpha/decisions`

```json
{
  "model": "typesafe/jev-1.14",
  "state": "<review text>",
  "questions": {
    "sentiment": {
      "type": "choice",
      "instructions": "Classify the sentiment of this product review toward the product or service.",
      "criteria": {
        "Positive": "The review expresses a positive sentiment toward the product or service.",
        "Negative": "The review expresses a negative sentiment toward the product or service."
      }
    }
  }
}
```

The same payload is used for Jev, Microsoft Decision, the Perplexity `:free` deciders, and the OpenRouter ids `baseten/bison-1` and `baseten/groundhog-1`. Docs: [OpenRouter Decisions API](https://openrouter.ai/docs/guides/features/decisions). Decision models appear in `GET /api/v1/models?output_modalities=decisions`, not always in the unfiltered catalog.

A free endpoints recheck on 25 November 2026 (Asia/Calcutta) found one live BaseTen endpoint for each of `baseten/bison-1` and `baseten/groundhog-1` (provider status 0). Catalog and endpoint list prices match Valar’s claimed rates: bison-1 $0.10/1M in, $0 out; groundhog-1 $0.035/1M in, $0 out. Canonical slugs: `baseten/bison-1-20261120` and `baseten/groundhog-1-20261120`. These models are called only through OpenRouter. There is no direct Baseten API adapter and no `BASETEN_API_KEY` path.

**OpenRouter LLMs** use chat completions with a JSON schema enum:

`POST https://openrouter.ai/api/v1/chat/completions`

`response_format` is a strict `json_schema` with `label ∈ {Positive, Negative}`. `logprobs` / `top_logprobs` are requested only when the catalog lists `logprobs` (Qwen4 Max and DeepSeek V4.1 Flash 1017). Gemini 4 Hydrogen and the GPT-6 models do not list `logprobs`. Where reasoning can be turned off (`reasoning_effort=none`), the harness does so. Gemini 4 Hydrogen and GPT-6.2 Sol list reasoning as **mandatory**; those runs will bill reasoning tokens that we did not guess in the estimate. For those two, `max_tokens` is raised to 4096 so the structured answer is not clipped by reasoning tokens; the other chat models stay at 64.

**Sarvam Prism** (outside OpenRouter): `POST https://api.sarvam.ai/v2/systemone` with `model: "sarvam-prism"` and the same `state` / `questions` envelope. Auth: `api-subscription-key: $SARVAM_API_KEY` (Bearer is also documented). Docs: [Sarvam Prism](https://docs.sarvam.ai/api/token-factory/models/sarvam-prism). Cost is tracked in INR at the official ₹4/1M input rate applied to usage prompt tokens, under a separate cap, and is not part of the OpenRouter USD total.

Instructions stay in English for every language of the review, so a hi-vs-en drop is not confounded by a different question.

## Cost estimate (no inference)

Counted on 25 November 2026 with **tiktoken `o200k_base`**. That is an approximation for every model: it is OpenAI’s recent GPT tokenizer, not Gemini, Qwen, DeepSeek, or the System One billed tokenizers. Decision-model counts are tokens of the compact JSON payload (`state` + `questions`). Chat counts include the system prompt, the review, and the `json_schema`. Indic text in particular may tokenize differently on the provider’s side.

Prices are from a committed snapshot of the free OpenRouter GETs in [`catalog/openrouter_snapshot.json`](catalog/openrouter_snapshot.json), plus the official Sarvam docs. No per-request fees were listed for these models (unlike some other Decisions models, e.g. Parallel Decisions Fast at $0.001/request). Full figures: [`estimates/cost_estimate.json`](estimates/cost_estimate.json).

Approximate prompt tokens for 240 texts: **24,662** on the Decisions payload (en 7,061 / hi 8,483 / ta 9,118) and **36,574** on the chat payload (en 11,058 / hi 12,406 / ta 13,110).

| Model | API id | Prompt tokens (approx.) | Listed price (input / output) | Est. USD | Complete? |
| --- | --- | --- | --- | --- | --- |
| TypeSafe Jev 1.14 | `typesafe/jev-1.14` | 24,662 | $0.042 / 1M in, $0 / 1M out | $0.001036 | yes |
| Microsoft Decision 1.1 | `microsoft/microsoft-decision-1.1` | 24,662 | $0.042 / 1M in, $0 / 1M out | $0.001036 | yes |
| Perplexity Decider Flash v1.3 (free) | `perplexity/pplx-decider-flash-v1.3:free` | 24,662 | $0 / 1M in, $0 / 1M out | $0.000000 | yes |
| Perplexity Decider v1.3 (free) | `perplexity/pplx-decider-v1.3:free` | 24,662 | $0 / 1M in, $0 / 1M out | $0.000000 | yes |
| Gemini 4 Hydrogen | `google/gemini-4-hydrogen` | 36,574 | $1.50 / 1M in, $7.50 / 1M out | $0.054861 (prompt only) | no |
| GPT-6.2 Sol | `openai/gpt-6.2-sol` | 36,574 | $2.00 / 1M in, $10.00 / 1M out | $0.073148 (prompt only) | no |
| GPT-6 Luna | `openai/gpt-6-luna` | 36,574 | $0.10 / 1M in, $0.50 / 1M out | $0.004257 | yes |
| Qwen4 Max | `qwen/qwen4-max` | 36,574 | $1.425 / 1M in, $4.275 / 1M out | $0.057248 | yes |
| DeepSeek V4.1 Flash 1017 | `deepseek/deepseek-v4.1-flash-1017` | 36,574 | $0.036 / 1M in, $0.50 / 1M out | $0.001917 | yes |
| Baseten bison-1 | `baseten/bison-1` | 24,662 | $0.10 / 1M in, $0 / 1M out | $0.002466 | yes |
| Baseten groundhog-1 | `baseten/groundhog-1` | 24,662 | $0.035 / 1M in, $0 / 1M out | $0.000863 | yes |
| Sarvam Prism | `sarvam-prism` | 24,662 | ₹4 / 1M in, ₹0 out (no official USD) | — (₹0.098648) | no |

**Headline USD total: $0.196832.** That is the complete estimates plus the prompt-only cost of Gemini and GPT-6.2 Sol (reasoning is mandatory; reasoning tokens were not guessed, so the real bill for those two will be higher). It excludes Sarvam Prism (official price is in INR only, about ₹0.10 for 240 texts). The Perplexity `:free` variants are included at $0. It is not a cap and not a billed amount.

Luna, Qwen, and DeepSeek completion costs assume `reasoning_effort=none` and a 5-token structured body `{"label":"Positive"}` per request. No model in this set listed a per-request fee.

The unsuffixed Perplexity v1.3 ids have a model record on `GET /api/v1/models/<id>/endpoints` but **zero endpoints**. The Decisions catalog lists `perplexity/pplx-decider-flash-v1.3:free` and `perplexity/pplx-decider-v1.3:free` at **$0 / $0**, each with one Perplexity endpoint. Those `:free` ids are the ones in this lineup; the harness does not silently substitute them for the unsuffixed ids.

## Setup

Python 3.12+ (3.13 was used).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Keys, when a live run is approved, come only from the environment: `OPENROUTER_API_KEY` and, for Prism, `SARVAM_API_KEY`. See `.env.example`. Do not commit values. Baseten models use the OpenRouter key; there is no `BASETEN_API_KEY` path.

## How to run

Dry run (no spend):

```bash
python prepare_data.py          # rebuilds the committed 80-row sample; offline
python run.py --dry-run --estimate
```

`--dry-run` tokenizes the 240 texts, writes the estimate, and prints one sample request body per model. It does **not** POST to any inference endpoint. Inference POSTs are also hard-blocked in code unless `--live` is passed.

An approved live run can name one model, or `all` to walk the OpenRouter lineup in cheap-first order (Perplexity `:free`, groundhog, Jev, Microsoft Decision, DeepSeek, bison, Luna, Qwen, then Gemini and GPT-6.2 Sol last) and then Sarvam Prism. `--max-usd` is a **cumulative** cap across all OpenRouter models, tracked from each response’s `usage.cost` (falling back to tokens × list price only if that field is missing, and flagged). The runner stops before starting a request that is likely to push the running total past the cap, and will leave Gemini or Sol at a partial n rather than overspend. Sarvam is billed in INR under `--max-inr` (default 50) and is outside the USD cap. At most a couple of retries, and only on 429 / 5xx.

```bash
python run.py --live --model all --max-usd 2.00 --max-inr 50
python run.py --live --model jev --max-usd 1.00
```

Do not pass `--live` until spend is approved in Kamal’s own words.

## Results

*Placeholder. No model has been run. This commit ends at the estimate above.*

Smoke test, n=80 per language. Self-reported confidence is not comparable and is not used.

| Model | Status | n | Acc. en | Acc. hi | Acc. ta | hi−en | ta−en | p50 ms | p95 ms | Actual cost | Acc. at p≥0.9 (n) | Acc. at p<0.9 (n) | Brier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| — | not run | 80 × 3 | — | — | — | — | — | — | — | — | — | — | — |

## Blocked for a live run (current environment)

Looked for `SARVAM_API_KEY` only in the current process environment. `BASETEN_API_KEY` is not used.

| Model | Blocked because |
| --- | --- |
| — | None in the current environment. `OPENROUTER_API_KEY` and `SARVAM_API_KEY` are set. No inference POST has been made in this commit. |

The unsuffixed Perplexity v1.3 ids remain unroutable (0 endpoints) and are not in the runnable lineup.

## Caveats

- **Smoke test, n=80.** Language drops will have wide intervals.
- **Projected only in the sense of parallel text.** Labels are the original IndicSentiment gold labels, not a remap.
- **Tokenizer approximation.** `o200k_base` is not what Jev, Prism, or Gemini bill.
- **Mandatory reasoning.** Gemini 4 Hydrogen and GPT-6.2 Sol will cost more than the prompt-only line. We did not invent a reasoning-token count. They run last under the cumulative USD cap and may finish at a partial n.
- **Logprobs are uneven.** Calibration is possible for decision models and for LLMs that actually return logprobs. Gemini and the GPT-6 chat models are not expected to produce a comparable probability vector.
- **Self-reported confidence is not used.** Some models also return a `confidence` field that is a rescaled peak probability; we score the raw `probabilities` map instead. Those self-reported figures are not comparable across models.
- **OpenRouter Decisions is an alpha API.** The request shape may change.
- **License field missing on the HF card.** We follow the paper and IndicBERT README (CC-0) and record the gap.
- No keys, passwords, or token values are stored in this repo.

## License

Code is MIT (see `LICENSE`). The IndicSentiment excerpt is treated as CC-0; see `data/SOURCE.md`.
