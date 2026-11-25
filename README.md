# Decision models and an Indic smoke test

This note explains how System One decision models work, then records numbers from two small smoke tests on English, Hindi, and Tamil: product-review sentiment, and request routing. It is exploratory. It is not a benchmark, and it is not a ranking of models or languages.

Every figure in the sentiment table comes from the live run in `results/`. Every figure in the request-routing table comes from the live run in `results/routing/`. Proposed public repo name, not created and not pushed: CitruzAI/indic-decision-models-smoke-test.

## What decision models are

System One is TypeSafe's name for models that return a structured judgement instead of writing a reply. The name refers to Kahneman's fast judgements.

You send two things:

- `state`: the document to judge. Here that is a product review.
- `questions`: one or more typed questions, each with a declared set of answers.

On a `choice` question you name the allowed options and a short criterion for each one. The model picks one option and returns a probability for every option. It does not free-write a sentence.

The public docs also describe other question types, which this smoke test does not use:

- `noul`: yes or no, as the probability of true
- `score`: an ordered scale
- `box`: a region in an image, on Jev 1.14

That interface is different from prompting a chat LLM to "reply with Positive or Negative." The chat models in this smoke test were still asked to decide, but through a constrained JSON label, not through a native probability over declared options. Details are below the example.

Docs: [OpenRouter Decisions API](https://openrouter.ai/docs/guides/features/decisions), [Sarvam Prism](https://docs.sarvam.ai/api/token-factory/models/sarvam-prism).

## A request and a response

Decision models on OpenRouter are called with `POST https://openrouter.ai/api/alpha/decisions`. The same `state` and `questions` body is used for TypeSafe Jev 1.14, Microsoft Decision 1.1, the Perplexity `:free` deciders, `baseten/bison-1`, and `baseten/groundhog-1`. Sarvam Prism uses the same envelope at `POST https://api.sarvam.ai/v2/systemone`. No API keys appear in these examples.

This request is the English text of item s053 from the smoke test, as sent to Jev:

```json
{
  "model": "typesafe/jev-1.14",
  "state": "It is not durable.",
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

The live response, from the returned id `typesafe/jev-1.14-20261014`, chose Negative, which matched the gold label, and returned this probability vector:

```json
{
  "model": "typesafe/jev-1.14-20261014",
  "answers": {
    "sentiment": {
      "type": "choice",
      "choice": "Negative",
      "probabilities": {
        "Positive": 0.0,
        "Negative": 1.0
      }
    }
  }
}
```

Some decision-model responses also include a `confidence` field. That value is often a rescaled peak probability. It is not comparable across models, and this repo does not use it. Scoring uses the raw `probabilities` map.

Instructions stay in English for every language of the review, so a Hindi or Tamil difference is not caused by a different question.

## How this differs from a chat LLM

A chat LLM is prompted to produce a label. In this smoke test that call is `POST https://openrouter.ai/api/v1/chat/completions` with a strict `json_schema` whose `label` must be `Positive` or `Negative`. The model still writes a reply. The schema only restricts the string.

A probability vector is available for a chat model only when the catalog lists `logprobs` and both labels appear in `top_logprobs`. In that case the runner takes a softmax over those logprobs. Qwen4 Max and DeepSeek V4.1 Flash 1017 list `logprobs`. Gemini 4 Hydrogen, GPT-6 Luna, and GPT-6.2 Sol do not, so those three have a label only. A self-reported confidence number inside the JSON body is not used.

Where reasoning can be turned off, the runner sets `reasoning_effort=none`. Gemini 4 Hydrogen and GPT-6.2 Sol list reasoning as mandatory, so those calls bill reasoning tokens. For those two, `max_tokens` is 4096 so the structured label is not clipped by reasoning tokens. The other chat models use `max_tokens` 64.

## What we tried

The texts are 80 of the 998 labeled items in the IndicSentiment test split from AI4Bharat, sampled with seed 42, and reused at the same source indices in English, Hindi, and Tamil. That is 240 texts per model. The choice is `Positive` or `Negative`. The sample has 42 Positive and 38 Negative reviews.

Verified counts in Hugging Face revision `dc8f3f66886531c6897fedffca1e938a68fc5013`:

- The paper lists a test size of 1,000. Each of `data/test/hi.json` and `data/test/ta.json` has 1,000 rows.
- 998 rows are labeled, 506 Positive and 492 Negative. 2 rows have `LABEL: null` (source indices 663 and 694) and were excluded before sampling.
- There is no `en.json`. English is the shared `ENGLISH REVIEW` field. Hindi and Tamil are row-aligned with the English text and with the label.

Full notes: [`data/SOURCE.md`](data/SOURCE.md). The sample is [`data/reviews.jsonl`](data/reviews.jsonl).

We ran seven decision models and five chat LLMs, each on all 240 texts. Decision models went through the Decisions API, or through Sarvam's System One endpoint for Prism. Chat models used the JSON-schema path above.

For each model we recorded accuracy on English, Hindi, and Tamil, the Hindi-minus-English and Tamil-minus-English accuracy differences, p50 and p95 latency, and actual cost. OpenRouter cost is the sum of `usage.cost` on each response. Sarvam Prism is reported in INR, at the official ₹4/1M input rate applied to usage prompt tokens, and is outside the OpenRouter total. Brier score, and accuracy at probability ≥ 0.9 versus below, are reported only when a probability vector exists.

The live run ran from 12:35:38 to 13:13:20 IST (Asia/Calcutta) on 25 November 2026, under an approved $2 cumulative cap on OpenRouter and a separate ₹50 cap for Sarvam. All 12 models finished 240 of 240 texts. OpenRouter billed $0.62655718. Sarvam Prism billed ₹0.09485200.

The unsuffixed Perplexity v1.3 ids have a model record but zero endpoints, so the runnable ids were `perplexity/pplx-decider-flash-v1.3:free` and `perplexity/pplx-decider-v1.3:free`. Baseten models were called only as `baseten/bison-1` and `baseten/groundhog-1` on OpenRouter, not with a `BASETEN_API_KEY`.

## What we saw

This is a smoke test, n=80 per language. Accuracies on this sample sat near the ceiling, so language differences are small and have wide intervals. They are not a finding about which language is easier. Some models scored slightly higher on Hindi or Tamil than on English. Some scored slightly lower. Self-reported confidence is not comparable and is not used.

The table is grouped by interface, then sorted alphabetically, not by score.

| Model | Status | n | Acc. en | Acc. hi | Acc. ta | hi-en | ta-en | p50 ms | p95 ms | Actual cost | Acc. at p≥0.9 (n) | Acc. at p<0.9 (n) | Brier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseten bison-1 (`baseten/bison-1`) | ran | 80 × 3 | 1.000 | 0.988 | 1.000 | -0.013 | 0.000 | 213.3 | 301.0 | $0.00367400 | 1.000 (n=211) | 0.966 (n=29) | 0.018 |
| Baseten groundhog-1 (`baseten/groundhog-1`) | ran | 80 × 3 | 1.000 | 1.000 | 0.975 | 0.000 | -0.025 | 206.0 | 242.1 | $0.00128590 | 1.000 (n=191) | 0.959 (n=49) | 0.025 |
| Microsoft Decision 1.1 (`microsoft/microsoft-decision-1.1`) | ran | 80 × 3 | 0.988 | 0.988 | 1.000 | 0.000 | 0.013 | 234.6 | 317.1 | $0.00095844 | 1.000 (n=225) | 0.867 (n=15) | 0.013 |
| Perplexity Decider Flash v1.3 (free) (`perplexity/pplx-decider-flash-v1.3:free`) | ran | 80 × 3 | 0.975 | 0.988 | 0.988 | 0.013 | 0.013 | 143.2 | 195.0 | $0.00000000 | 1.000 (n=215) | 0.840 (n=25) | 0.022 |
| Perplexity Decider v1.3 (free) (`perplexity/pplx-decider-v1.3:free`) | ran | 80 × 3 | 0.975 | 0.988 | 0.988 | 0.013 | 0.013 | 233.8 | 267.2 | $0.00000000 | 1.000 (n=225) | 0.733 (n=15) | 0.020 |
| Sarvam Prism (`sarvam-prism`) | ran | 80 × 3 | 1.000 | 0.988 | 0.988 | -0.013 | -0.013 | 1206.5 | 2036.0 | ₹0.09485200 (INR, outside $2 cap) | 1.000 (n=213) | 0.926 (n=27) | 0.022 |
| TypeSafe Jev 1.14 (`typesafe/jev-1.14`) | ran | 80 × 3 | 1.000 | 0.975 | 0.988 | -0.025 | -0.013 | 134.1 | 191.9 | $0.00423641 | 1.000 (n=230) | 0.700 (n=10) | 0.015 |
| DeepSeek V4.1 Flash 1017 (`deepseek/deepseek-v4.1-flash-1017`) | ran | 80 × 3 | 1.000 | 1.000 | 0.988 | 0.000 | -0.013 | 461.8 | 2360.7 | $0.00408200 | 1.000 (n=105) | 1.000 (n=2) | 0.002 |
| Gemini 4 Hydrogen (`google/gemini-4-hydrogen`) | ran | 80 × 3 | 0.988 | 0.988 | 1.000 | 0.000 | 0.013 | 1521.9 | 2473.7 | $0.43529400 | - | - | - |
| GPT-6 Luna (`openai/gpt-6-luna`) | ran | 80 × 3 | 1.000 | 1.000 | 0.988 | 0.000 | -0.013 | 766.0 | 1627.5 | $0.00468800 | - | - | - |
| GPT-6.2 Sol (`openai/gpt-6.2-sol`) | ran | 80 × 3 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1168.4 | 1543.0 | $0.10046000 | - | - | - |
| Qwen4 Max (`qwen/qwen4-max`) | ran | 80 × 3 | 0.988 | 0.988 | 0.988 | 0.000 | 0.000 | 1549.7 | 2165.4 | $0.07187843 | 1.000 (n=227) | 0.667 (n=9) | 0.014 |

Accuracy, differences, and Brier are rounded half-up from the exact fractions in `results/*.summary.json`. Luna, Gemini 4 Hydrogen, and GPT-6.2 Sol have a dash in the calibration columns because they have no probability vector.

A few details that sit behind those cells:

- GPT-6.2 Sol labeled all 240 texts correctly. Gemini 4 Hydrogen billed $0.43529400, above its prompt-only estimate of $0.054861, because reasoning is mandatory. GPT-6.2 Sol billed $0.10046000, against a prompt-only estimate of $0.073148.
- Some decision-model bills were higher than the pre-run token estimate. Jev billed $0.00423641 against an estimate of $0.001036. bison-1 billed $0.00367400 against $0.002466. groundhog-1 billed $0.00128590 against $0.000863. The estimate used tiktoken `o200k_base`, which is not the billed tokenizer.
- DeepSeek's Brier and accuracy-at-p figures use only the 107/240 items where both labels appeared in `top_logprobs`. The other 133 had a label but no comparable probability vector.
- Qwen's calibration uses 236/240 items. A `RemoteDisconnected` error interrupted the Qwen run at about 12:50:02 IST, after s028/ta. The run resumed at 12:50:46 IST from s029. Four items (s027/ta, s028/en, s028/hi, s028/ta) had already been billed. They were recovered from the log for accuracy and cost, without a saved probability vector or latency, and were not billed again. Qwen p50 and p95 are over the 236 timed items.
- Item s011, gold Negative, was a recurring miss, including on the English text for several models.
- The two Perplexity `:free` deciders have the same per-language accuracies and four misses each, but not the same miss set. Their labels agreed on 236 of 240 texts.

Returned model ids, as the APIs echoed them: `baseten/bison-1-20261120`, `baseten/groundhog-1-20261120`, `microsoft/microsoft-decision-1.1-20261117`, `perplexity/pplx-decider-flash-v1.3-20261112`, `perplexity/pplx-decider-v1.3-20261112`, `sarvam-prism`, `typesafe/jev-1.14-20261014`, `deepseek/deepseek-v4.1-flash-1017`, `google/gemini-4-hydrogen`, `openai/gpt-6-luna`, `openai/gpt-6.2-sol`, `qwen/qwen4-max`.

Per-model clocks in IST (Asia/Calcutta): Perplexity Flash from 12:35:38 to 12:36:13, Perplexity v1.3 from 12:36:13 to 12:37:10, groundhog from 12:37:10 to 12:37:59, Jev from 12:37:59 to 12:38:31, Microsoft Decision from 12:38:31 to 12:39:31, DeepSeek from 12:39:31 to 12:42:38, bison from 12:42:38 to 12:43:31, Luna from 12:43:31 to 12:47:09, Qwen from 12:47:09 to 12:55:39 with the gap noted above, Gemini from 12:55:39 to 13:02:43, Sol from 13:02:43 to 13:07:34, Sarvam from 13:07:34 to 13:13:20.

## Caveats

- Smoke test, n=80 per language. Language differences will have wide intervals.
- The task was easy on this sample. Accuracies sat near the ceiling, which leaves little room to see a language drop.
- Labels are the original IndicSentiment gold labels, not a remap. Parallel text here means the same item in three languages, not a new annotation.
- Cost figures in the results table are actual billed amounts as described above, not the pre-run estimate. The estimate is kept below for reference. `o200k_base` is not what Jev, Prism, or Gemini bill.
- Gemini 4 Hydrogen and GPT-6.2 Sol cost more than their prompt-only estimate lines because reasoning is mandatory. The estimate did not invent a reasoning-token count.
- Logprobs are uneven. Calibration is possible for decision models and for chat models that actually return logprobs covering both labels. Gemini and the GPT-6 chat models are not expected to produce a comparable probability vector.
- Self-reported confidence is not used and is not comparable across models.
- OpenRouter Decisions is an alpha API. The request shape may change.
- The Hugging Face card and Hub API for `ai4bharat/IndicSentiment` have no license field. arXiv:2212.05409 (ethics statement) and the [IndicBERT README](https://github.com/AI4Bharat/IndicBERT) both say the datasets from that work are released under CC-0. The MTEB mirror `mteb/IndicSentiment` declares `cc0-1.0`. We follow the paper and the IndicBERT README and record the gap. CC-0 text: [`licenses/CC0-1.0.txt`](licenses/CC0-1.0.txt).
- No keys, passwords, or token values are stored in this repo.

## Pre-run cost estimate

Counted on 25 November 2026 with tiktoken `o200k_base`. That is an approximation for every model. Decision-model counts are tokens of the compact JSON payload (`state` plus `questions`). Chat counts include the system prompt, the review, and the `json_schema`. Indic text may tokenize differently on the provider's side.

Prices are from a committed snapshot of the free OpenRouter GETs in [`catalog/openrouter_snapshot.json`](catalog/openrouter_snapshot.json), plus the official Sarvam docs. No per-request fees were listed for these models. Full figures: [`estimates/cost_estimate.json`](estimates/cost_estimate.json).

Approximate prompt tokens for 240 texts: 24,662 on the Decisions payload (en 7,061 / hi 8,483 / ta 9,118) and 36,574 on the chat payload (en 11,058 / hi 12,406 / ta 13,110).

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
| Sarvam Prism | `sarvam-prism` | 24,662 | ₹4 / 1M in, ₹0 out (no official USD) | - (₹0.098648) | no |

Headline USD total: $0.196832. That is the complete estimates plus the prompt-only cost of Gemini and GPT-6.2 Sol. It excludes Sarvam Prism, whose official price is in INR only, about ₹0.10 for 240 texts. The Perplexity `:free` variants are included at $0. It is not a cap and not a billed amount.

Luna, Qwen, and DeepSeek completion costs assume `reasoning_effort=none` and a 5-token structured body `{"label":"Positive"}` per request.

A free endpoints recheck on 25 November 2026 (Asia/Calcutta) found one live BaseTen endpoint for each of `baseten/bison-1` and `baseten/groundhog-1` (provider status 0). Catalog and endpoint list prices were $0.10/1M in and $0 out for bison-1, and $0.035/1M in and $0 out for groundhog-1. Canonical slugs: `baseten/bison-1-20261120` and `baseten/groundhog-1-20261120`.

## Request routing

A second use case on the same 12 models: route a short request to one of six queues. The interface is unchanged. Decision models still receive a `choice` question; the criteria are the six queue descriptions below. Chat models receive the same descriptions in the system prompt, and still return a constrained JSON label.

### The sample and the options

The texts are 80 items from Amazon MASSIVE (CC BY 4.0): short assistant-style requests, sampled with seed 42 from the test split, and reused at the same ids in English, Hindi, and Tamil. That is 240 texts per model.

Intents from the dataset are mapped onto six queues that follow MASSIVE's own scenario groups. Intents that did not clearly belong on one queue were dropped rather than forced in. The same one-line description of each queue was sent to every model:

- Calendar: Calendar and reminders: events, alarms, and personal to-do or shopping lists.
- SmartHome: Smart home: lights, plugs, appliances, and other household devices.
- Media: Media and volume: playing music, radio, podcasts, audiobooks, or games, and volume or playback settings.
- Orders: Orders and transport: takeaway food, travel tickets, and ride bookings.
- Info: Info lookup: facts, news, weather, time, conversions, recipes, currency, and stock prices.
- Email: Email and contacts: reading or sending email, and looking up or adding contacts.

The mapping lives in [`indic_smoke/routing/mapping.py`](indic_smoke/routing/mapping.py). Source notes: [`data/routing/SOURCE.md`](data/routing/SOURCE.md). The sample is [`data/routing/requests.jsonl`](data/routing/requests.jsonl). License text: [`licenses/CC-BY-4.0.txt`](licenses/CC-BY-4.0.txt).

Before sampling, an item was also dropped when any of the English, Hindi, or Tamil texts contained a product wake word or assistant name, including common Hindi and Tamil spellings, or a hey/ok-style prefix immediately followed by one of those names. Tokenization keeps letters and combining marks together so a name is matched only as a whole word. Of the 2,974 test items, 490 were dropped as unmapped. Of the rest, 102 were dropped by this filter. 31 further wake-word items already sat in an unmapped intent, so 133 test items matched the filter in at least one language. Eligible pool sizes after both filters: Calendar 626, SmartHome 204, Media 468, Orders 108, Info 711, Email 265. The 80-id sample, seed 42, is 14 Calendar, 14 Info, and 13 each for SmartHome, Media, Orders, and Email.

Before any live calls, three English examples per option were drawn from that sample and checked by eye. Most labels were a reasonable reading of the text. One Calendar item, r047 ("what are the upcoming concerts in dallas"), already looked like an Info lookup. It later became the most common miss, which is discussed below. The filter left no wake-word items in the sample.

### What we ran

The live run used the same 12 models and adapters as the sentiment run. It ran from 14:34:17 to 15:36:51 IST (Asia/Calcutta) on 25 November 2026, under a new approved $2 cumulative cap on OpenRouter and a separate ₹50 cap for Sarvam. Eleven models finished 240 of 240 texts. bison-1 recorded 240 rows, but one Hindi item (r031/hi) returned HTTP 429 after retries, so bison is scored on 239 texts and was not billed for that row. OpenRouter billed $0.68621082. Sarvam Prism billed ₹0.19332800, outside the USD total.

The pre-run headline estimate was $0.34773840 (complete estimates plus the prompt-only cost of Gemini 4 Hydrogen and GPT-6.2 Sol, excluding Sarvam). The gap is mostly Gemini, which billed $0.46048650 because reasoning is mandatory. Full figures: [`estimates/routing/cost_estimate.json`](estimates/routing/cost_estimate.json).

### What we saw

This is a six-way routing task, n=80 per language. It is harder than the binary sentiment set, and the accuracies spread out more, but it is still a smoke test. Language differences on this sample are not a finding about which language is easier. A handful of recurring misses look like label or translation artefacts, not like a clean model error. Those are listed after the table.

The table is grouped by interface, then sorted alphabetically, not by score.

| Model | Status | n | Acc. en | Acc. hi | Acc. ta | Acc. overall | hi-en | ta-en | p50 ms | p95 ms | Actual cost | Acc. at p≥0.9 (n) | Acc. at p<0.9 (n) | Brier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseten bison-1 (`baseten/bison-1`) | ran_with_errors | 239 / 240 | 0.988 | 0.975 | 0.938 | 0.967 | -0.013 | -0.050 | 216.0 | 272.7 | $0.00591970 | 0.995 (n=201) | 0.816 (n=38) | 0.055 |
| Baseten groundhog-1 (`baseten/groundhog-1`) | ran | 80 × 3 | 0.975 | 0.950 | 0.950 | 0.958 | -0.025 | -0.025 | 213.7 | 333.7 | $0.00208065 | 1.000 (n=192) | 0.792 (n=48) | 0.069 |
| Microsoft Decision 1.1 (`microsoft/microsoft-decision-1.1`) | ran | 80 × 3 | 0.988 | 0.950 | 0.950 | 0.963 | -0.038 | -0.038 | 251.6 | 398.5 | $0.00175085 | 0.995 (n=207) | 0.758 (n=33) | 0.058 |
| Perplexity Decider Flash v1.3 (free) (`perplexity/pplx-decider-flash-v1.3:free`) | ran | 80 × 3 | 0.975 | 0.963 | 0.900 | 0.946 | -0.012 | -0.075 | 145.6 | 194.5 | $0.00000000 | 0.995 (n=211) | 0.586 (n=29) | 0.070 |
| Perplexity Decider v1.3 (free) (`perplexity/pplx-decider-v1.3:free`) | ran | 80 × 3 | 0.988 | 1.000 | 0.950 | 0.979 | 0.012 | -0.038 | 239.7 | 278.8 | $0.00000000 | 0.995 (n=216) | 0.833 (n=24) | 0.039 |
| Sarvam Prism (`sarvam-prism`) | ran | 80 × 3 | 0.963 | 0.950 | 0.938 | 0.950 | -0.013 | -0.025 | 4971.7 | 9791.6 | ₹0.19332800 (INR, outside $2 cap) | 0.971 (n=205) | 0.829 (n=35) | 0.087 |
| TypeSafe Jev 1.14 (`typesafe/jev-1.14`) | ran | 80 × 3 | 0.950 | 0.925 | 0.900 | 0.925 | -0.025 | -0.050 | 138.2 | 210.6 | $0.00499355 | 0.985 (n=199) | 0.634 (n=41) | 0.088 |
| DeepSeek V4.1 Flash 1017 (`deepseek/deepseek-v4.1-flash-1017`) | ran | 80 × 3 | 0.938 | 0.938 | 0.925 | 0.933 | 0.000 | -0.012 | 424.9 | 986.2 | $0.00649984 | - | - | - |
| Gemini 4 Hydrogen (`google/gemini-4-hydrogen`) | ran | 80 × 3 | 0.975 | 0.950 | 0.963 | 0.963 | -0.025 | -0.012 | 1729.6 | 6989.0 | $0.46048650 | - | - | - |
| GPT-6 Luna (`openai/gpt-6-luna`) | ran | 80 × 3 | 0.938 | 0.938 | 0.838 | 0.904 | 0.000 | -0.100 | 767.3 | 1335.1 | $0.00749920 | - | - | - |
| GPT-6.2 Sol (`openai/gpt-6.2-sol`) | ran | 80 × 3 | 0.925 | 0.913 | 0.900 | 0.913 | -0.013 | -0.025 | 1332.0 | 2547.5 | $0.16470400 | - | - | - |
| Qwen4 Max (`qwen/qwen4-max`) | ran | 80 × 3 | 0.938 | 0.925 | 0.913 | 0.925 | -0.012 | -0.025 | 1507.5 | 2092.2 | $0.03227654 | - | - | - |

Accuracy, differences, and Brier are rounded half-up from the exact fractions in `results/routing/*.summary.json`. Calibration uses the raw probability vector, not a self-reported confidence field. Luna, Gemini 4 Hydrogen, and GPT-6.2 Sol have a dash in those columns because they have no probability vector. Qwen4 Max and DeepSeek V4.1 Flash 1017 list logprobs, but on this six-way task the returned `top_logprobs` did not cover every option, so no comparable vector was stored and those cells are also dashes.

When a decision model put probability 0.9 or higher on its choice, accuracy on those rows was between 0.971 and 1.000. Below 0.9, accuracy was lower: 0.586 on 29 rows for Perplexity Flash, 0.634 on 41 rows for Jev, and between 0.758 and 0.833 for the other decision models.

A few other details:

- Gemini 4 Hydrogen billed $0.46048650, and GPT-6.2 Sol billed $0.16470400, both above their prompt-only pre-run estimates, because reasoning is mandatory.
- bison-1's missing score is the r031/hi 429 already noted. The other 239 rows have labels and costs.
- Luna's Tamil accuracy is 0.838, a 0.100 drop from English on this sample. Several of those Tamil misses are texts that no longer match the English gold, as below.

Returned model ids, as the APIs echoed them, were the same slugs as in the sentiment run: `baseten/bison-1-20261120`, `baseten/groundhog-1-20261120`, `microsoft/microsoft-decision-1.1-20261117`, `perplexity/pplx-decider-flash-v1.3-20261112`, `perplexity/pplx-decider-v1.3-20261112`, `sarvam-prism`, `typesafe/jev-1.14-20261014`, `deepseek/deepseek-v4.1-flash-1017`, `google/gemini-4-hydrogen`, `openai/gpt-6-luna`, `openai/gpt-6.2-sol`, `qwen/qwen4-max`.

Per-model clocks in IST (Asia/Calcutta): Perplexity Flash from 14:34:17 to 14:34:55, Perplexity v1.3 from 14:34:55 to 14:35:53, groundhog from 14:35:53 to 14:36:51, Jev from 14:36:51 to 14:37:41, Microsoft Decision from 14:37:41 to 14:38:57, DeepSeek from 14:38:57 to 14:41:10, bison from 14:41:10 to 14:49:58, Luna from 14:49:58 to 14:53:31, Qwen from 14:53:31 to 14:59:46, Gemini from 14:59:46 to 15:10:00, Sol from 15:10:00 to 15:15:52, Sarvam from 15:15:52 to 15:36:51.

### Where the misses clustered

Across all 12 models there were 162 misses on 2,879 scored rows (bison's one 429 is excluded). The most common gold-to-predicted pairs were Orders to Info (32 misses, 4 ids), Calendar to Info (23 misses, all on r047), Email to Info (22 misses, mostly r070), SmartHome to Media (16 misses, mostly r021), and Info to Media (14 misses, mostly the Tamil text of r063).

The same items dominate the misses on TypeSafe Jev 1.14 (18 misses), Microsoft Decision 1.1 (9 misses), Qwen4 Max (18 misses), and GPT-6 Luna (23 misses). Jev and Microsoft Decision both sent r047 to Info in all three languages. Qwen and Luna did the same, and also often sent delivery-availability questions (r006, r022, r038) from Orders to Info. Luna's extra misses are concentrated in Tamil.

Some of those gaps look like label or translation artefacts, or like an overlap in the queue descriptions, rather than a clean model error. Five examples:

- r047, gold Calendar (`calendar_query`): "what are the upcoming concerts in dallas" (Hindi: concerts in Indore; Tamil: concerts in Chennai). A reasonable person can read this as Info. Eight of 12 models chose Info on English and Hindi, seven on Tamil. bison, both Perplexity deciders, and Sarvam kept Calendar. This was visible in the pre-spend sanity check.
- r063, gold Info (`qa_definition`). The English text is "suffering consequences". The Tamil text is "ஹிப் பாப் தமிழா", a question about hip hop, which is not a translation of the English line. All 12 models labeled the Tamil text Media. That is a dataset alignment problem, not a routing mistake.
- r001, gold Media (`play_music`). English is "play it again please". Hindi is "कृपया इसको फिर से चालू करो", which is naturally read as "please turn it on again." Ten of 12 models labeled the Hindi text SmartHome. English was labeled Media by every model.
- r070, gold Email (`email_querycontact`): "tell me about mary s." With no extra context this reads as an Info lookup about a person. The gold comes from MASSIVE's contact-query intent. Four models chose Info on English, seven on Hindi, nine on Tamil.
- r021, gold SmartHome (`iot_wemo_on`): "stop start the juice". The gold is a household-device intent, but the English text is garbled. Seven models called the English text Media; the Hindi line ("जूस को देना बंद करो") was twice read as Orders.

A milder overlap sits in the option wording itself. r006, "does pizza hut have delivery", is a takeaway query and so is gold Orders, but it is also a factual question, which is what Info is for. Qwen and Luna often chose Info here. The gold is defensible; so is the other reading.

These artefacts inflate some language drops, especially Luna's Tamil number, and they inflate Calendar-to-Info and Info-to-Media counts. They do not account for every miss, and this is still a small sample.

Request-routing caveats that add to the list below: n=80 per language; six queues, some of which a short request can fairly fit in two places; parallel text here means the same MASSIVE id in three locales, and as r063 shows, that is not always a faithful translation; Amazon MASSIVE is CC BY 4.0, see [`data/routing/SOURCE.md`](data/routing/SOURCE.md).

## Setup

Python 3.12+ (3.13 was used).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Keys come only from the environment: `OPENROUTER_API_KEY` and, for Prism, `SARVAM_API_KEY`. See `.env.example`. Do not commit values. Baseten models use the OpenRouter key.

## How to run

Dry run, no spend:

```bash
python prepare_data.py          # rebuilds the committed sentiment sample; offline
python prepare_routing.py       # rebuilds the committed routing sample; offline if upstream test files are present
python run.py --task sentiment --dry-run --estimate
python run.py --task routing --dry-run --estimate
```

`--task` selects sentiment or routing (data, results, and estimates paths). The default is sentiment. `--dry-run` tokenizes the 240 texts, writes the estimate, and prints one sample request body per model. It does not POST to any inference endpoint. Inference POSTs are also blocked in code unless `--live` is passed.

An approved live run can name one model, or `all` to walk the OpenRouter models in cheap-first order (Perplexity `:free`, groundhog, Jev, Microsoft Decision, DeepSeek, bison, Luna, Qwen, then Gemini and GPT-6.2 Sol last) and then Sarvam Prism. `--max-usd` is a cumulative cap across all OpenRouter models for that run, tracked from each response's `usage.cost`. If that field is missing, the runner falls back to tokens times list price and flags it. The runner stops before a request that is likely to push the running total past the cap. Sarvam is billed in INR under `--max-inr` (default 50) and is outside the USD cap. At most a couple of retries, and only on 429 or 5xx.

```bash
python run.py --task sentiment --live --model all --max-usd 2.00 --max-inr 50
python run.py --task routing --live --model all --max-usd 2.00 --max-inr 50
python run.py --task routing --live --model jev --max-usd 1.00
```

Do not pass `--live` until spend is approved in Kamal's own words.

## License

Code is MIT (see `LICENSE`). The IndicSentiment excerpt is treated as CC-0; see `data/SOURCE.md`. The request-routing excerpt is from Amazon MASSIVE, licensed CC BY 4.0; see `data/routing/SOURCE.md`.
