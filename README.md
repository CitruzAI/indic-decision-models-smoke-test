# Indic decision-models smoke test

How do System One decision models, and general LLMs used as deciders, hold up on **Hindi and Tamil** versus **English**?

This is a **smoke test, n=80 items × 3 languages = 240 texts per model**, not a benchmark. Every later number in a results table must come from a run recorded in `results/`. Phase 1 (this commit) ships the harness, the fixed sample, and a **cost estimate**. No inference call has been made.

Proposed public repo name (not created, not pushed): **CitruzAI/indic-decision-models-smoke-test**.

## Thesis

A review that is Positive or Negative in English has a human-translated Hindi and Tamil counterpart, with the same label. If a model is a reliable decider, its accuracy should not drop much when the text is in Hindi or Tamil.

We measure, once a live run is approved:

- accuracy per language (en, hi, ta)
- the hi−en and ta−en accuracy drops
- p50 and p95 latency
- actual cost from OpenRouter `usage.cost` fields (never an invented post-hoc cost)
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

The same payload is used for Jev, Microsoft Decision, and the Perplexity deciders (when a runnable id is available). Docs: [OpenRouter Decisions API](https://openrouter.ai/docs/guides/features/decisions). Decision models appear in `GET /api/v1/models?output_modalities=decisions`, not always in the unfiltered catalog.

**OpenRouter LLMs** use chat completions with a JSON schema enum:

`POST https://openrouter.ai/api/v1/chat/completions`

`response_format` is a strict `json_schema` with `label ∈ {Positive, Negative}`. `logprobs` / `top_logprobs` are requested only when the catalog lists `logprobs` (Qwen4 Max and DeepSeek V4.1 Flash 1017). Gemini 4 Hydrogen and the GPT-6 models do not list `logprobs`. Where reasoning can be turned off (`reasoning_effort=none`), the harness does so. Gemini 4 Hydrogen and GPT-6.2 Sol list reasoning as **mandatory**; those runs will bill reasoning tokens that we did not guess in the estimate.

**Sarvam Prism** (outside OpenRouter): `POST https://api.sarvam.ai/v2/systemone` with `model: "sarvam-prism"` and the same `state` / `questions` envelope. Auth: `api-subscription-key: $SARVAM_API_KEY` (Bearer is also documented). Docs: [Sarvam Prism](https://docs.sarvam.ai/api/token-factory/models/sarvam-prism).

**Baseten bison-1** (outside OpenRouter): `POST https://inference.baseten.co/v1/systemone` with `model: "decision-models/baseten-bison-latest"` and the same envelope. The API reference uses `Authorization: Bearer $BASETEN_API_KEY`; the model-library curl example uses `Authorization: Api-Key`. The adapter sends Bearer. Docs: [Baseten System One](https://docs.baseten.co/reference/inference-api/system-one).

Instructions stay in English for every language of the review, so a hi-vs-en drop is not confounded by a different question.

## Cost estimate (no inference)

Counted on 25 November 2026 with **tiktoken `o200k_base`**. That is an approximation for every model: it is OpenAI’s recent GPT tokenizer, not Gemini, Qwen, DeepSeek, or the System One billed tokenizers. Decision-model counts are tokens of the compact JSON payload (`state` + `questions`). Chat counts include the system prompt, the review, and the `json_schema`. Indic text in particular may tokenize differently on the provider’s side.

Prices are from a committed snapshot of the free OpenRouter GETs in [`catalog/openrouter_snapshot.json`](catalog/openrouter_snapshot.json), plus the official Sarvam and Baseten docs. No per-request fees were listed for these models (unlike some other Decisions models, e.g. Parallel Decisions Fast at $0.001/request). Full figures: [`estimates/cost_estimate.json`](estimates/cost_estimate.json).

Approximate prompt tokens for 240 texts: **24,662** on the Decisions payload (en 7,061 / hi 8,483 / ta 9,118) and **36,574** on the chat payload (en 11,058 / hi 12,406 / ta 13,110).

| Model | API id | Prompt tokens (approx.) | Listed price (input / output) | Est. USD | Complete? |
| --- | --- | --- | --- | --- | --- |
| TypeSafe Jev 1.14 | `typesafe/jev-1.14` | 24,662 | $0.042 / 1M in, $0 / 1M out | $0.001036 | yes |
| Microsoft Decision 1.1 | `microsoft/microsoft-decision-1.1` | 24,662 | $0.042 / 1M in, $0 / 1M out | $0.001036 | yes |
| Perplexity Decider Flash v1.3 | `perplexity/pplx-decider-flash-v1.3` | 24,662 | not found | — | no |
| Perplexity Decider v1.3 | `perplexity/pplx-decider-v1.3` | 24,662 | not found | — | no |
| Gemini 4 Hydrogen | `google/gemini-4-hydrogen` | 36,574 | $1.50 / 1M in, $7.50 / 1M out | $0.054861 (prompt only) | no |
| GPT-6.2 Sol | `openai/gpt-6.2-sol` | 36,574 | $2.00 / 1M in, $10.00 / 1M out | $0.073148 (prompt only) | no |
| GPT-6 Luna | `openai/gpt-6-luna` | 36,574 | $0.10 / 1M in, $0.50 / 1M out | $0.004257 | yes |
| Qwen4 Max | `qwen/qwen4-max` | 36,574 | $1.425 / 1M in, $4.275 / 1M out | $0.057248 | yes |
| DeepSeek V4.1 Flash 1017 | `deepseek/deepseek-v4.1-flash-1017` | 36,574 | $0.036 / 1M in, $0.50 / 1M out | $0.001917 | yes |
| Sarvam Prism | `sarvam-prism` | 24,662 | ₹4 / 1M in, ₹0 out (no official USD) | — (₹0.098648) | no |
| Baseten bison-1 | `decision-models/baseten-bison-latest` | 24,662 | $0.10 / 1M in, $0 out | $0.002466 | yes |

**Headline USD total: $0.195969.** That is the complete estimates plus the prompt-only cost of Gemini and GPT-6.2 Sol (reasoning is mandatory; reasoning tokens were not guessed, so the real bill for those two will be higher). It excludes the two unsuffixed Perplexity ids (no priced endpoint) and Sarvam Prism (official price is in INR only). It is not a cap and not a billed amount.

Luna, Qwen, and DeepSeek completion costs assume `reasoning_effort=none` and a 5-token structured body `{"label":"Positive"}` per request. No model in this set listed a per-request fee.

The unsuffixed Perplexity v1.3 ids have a model record on `GET /api/v1/models/<id>/endpoints` but **zero endpoints**. The Decisions catalog instead lists `perplexity/pplx-decider-flash-v1.3:free` and `perplexity/pplx-decider-v1.3:free` at **$0 / $0**, each with one Perplexity endpoint. This harness does not silently substitute those `:free` ids.

## Setup

Python 3.12+ (3.13 was used).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Keys, when a live run is later approved, come only from the environment: `OPENROUTER_API_KEY`, `SARVAM_API_KEY`, `BASETEN_API_KEY`. See `.env.example`. Do not commit values.

## How to run

Phase 1 (no spend):

```bash
python prepare_data.py          # rebuilds the committed 80-row sample; offline
python run.py --dry-run --estimate
```

`--dry-run` tokenizes the 240 texts, writes the estimate, and prints one sample request body per model. It does **not** POST to any inference endpoint. Inference POSTs are also hard-blocked in code unless `--live` is passed.

A later, approved live run must name one model and a hard cap. The cap aborts the run if a complete estimate already exceeds it, and again if cumulative `usage.cost` would pass it:

```bash
python run.py --live --model jev --max-usd 1.00
```

Do not pass `--live` until spend is approved in Kamal’s own words.

## Results

*Placeholder. No model has been run. Phase 1 ends at the estimate above.*

| Model | Status | n | Acc. en | Acc. hi | Acc. ta | hi−en | ta−en | p50 ms | p95 ms | Actual USD | Acc. at p≥0.9 (n) | Acc. at p<0.9 (n) | Brier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| — | not run | 80 × 3 | — | — | — | — | — | — | — | — | — | — | — |

## Blocked for a live run (current environment)

Looked for `SARVAM_API_KEY` and `BASETEN_API_KEY` only in the current process environment.

| Model | Blocked because |
| --- | --- |
| `perplexity/pplx-decider-flash-v1.3` | Model record exists, but 0 endpoints. Related confirmed id: `:free` at $0, not auto-used. |
| `perplexity/pplx-decider-v1.3` | Same. |
| `sarvam-prism` | `SARVAM_API_KEY` is not set. |
| `decision-models/baseten-bison-latest` | `BASETEN_API_KEY` is not set. |

`OPENROUTER_API_KEY` is present, but it has not been used for any inference POST. The other OpenRouter ids in the table were confirmed by the free catalog and endpoints GETs.

## Caveats

- **Smoke test, n=80.** Language drops will have wide intervals.
- **Projected only in the sense of parallel text.** Labels are the original IndicSentiment gold labels, not a remap.
- **Tokenizer approximation.** `o200k_base` is not what Jev, Prism, or Gemini bill.
- **Mandatory reasoning.** Gemini 4 Hydrogen and GPT-6.2 Sol will cost more than the prompt-only line. We did not invent a reasoning-token count.
- **Logprobs are uneven.** Calibration is possible for decision models and for LLMs that actually return logprobs. Gemini and the GPT-6 chat models are not expected to produce a comparable probability vector.
- **Self-reported confidence is not used.** Some models also return a `confidence` field that is a rescaled peak probability; we score the raw `probabilities` map instead.
- **OpenRouter Decisions is an alpha API.** The request shape may change.
- **License field missing on the HF card.** We follow the paper and IndicBERT README (CC-0) and record the gap.
- No keys, passwords, or token values are stored in this repo.

## License

Code is MIT (see `LICENSE`). The IndicSentiment excerpt is treated as CC-0; see `data/SOURCE.md`.
