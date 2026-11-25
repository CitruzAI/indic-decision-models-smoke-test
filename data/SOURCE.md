# Dataset source

The smoke-test items in `reviews.jsonl` are a fixed sample of the
**IndicSentiment** test split from AI4Bharat.

- Dataset: IndicSentiment, a 13-way parallel product-review sentiment set
  (English written first, then manually translated). Labels are Positive or
  Negative. The Hugging Face card also mentions a Neutral polarity, but the
  released test files used here only contain Positive, Negative, and two
  unlabeled (`null`) rows.
- Paper: Sumanth Doddapaneni, Rahul Aralikatte, Gowtham Ramesh, Shreya Goyal,
  Mitesh M. Khapra, Anoop Kunchukuttan, and Pratyush Kumar. 2023. *Towards
  Leaving No Indic Language Behind: Building Monolingual Corpora, Benchmark
  and Models for Indic Languages*. ACL 2023. https://arxiv.org/abs/2212.05409
- Hugging Face: https://huggingface.co/datasets/ai4bharat/IndicSentiment
  revision `dc8f3f66886531c6897fedffca1e938a68fc5013` (last modified 2024-05-06).
- Files used: `data/test/hi.json` and `data/test/ta.json`. There is no `en.json`;
  English is the `ENGLISH REVIEW` field, shared across languages. Hindi and
  Tamil text is `INDIC REVIEW`. The two files are row-aligned on English text
  and on the label.

## Counts we verified

The paper’s IndicXTREME table lists IndicSentiment as 156 dev / **1000 test**,
human-annotated, 13 languages, accuracy metric, reviews domain.

In the revision above:

- Each of `hi.json` and `ta.json` has **1000** rows.
- **998** rows have a label of `Positive` (506) or `Negative` (492).
- **2** rows have `LABEL: null` (source indices 663 and 694). Those were
  excluded, as specified, before sampling.
- Hindi and Tamil are perfectly aligned: all 1000 English reviews and labels
  match at the same source index.
- Among the 998 labeled rows, 2 English reviews appear twice (996 unique
  English texts). Item identity in this repo is `source_index`, not the English
  string, so the parallel hi/ta texts stay correctly paired.

The sample is 80 of those 998 labeled rows, drawn with `random.Random(42).sample`
in `prepare_data.py`. The same 80 source indices are used for English, Hindi,
and Tamil (240 texts per model).

## License

What we found, without resolving the legal question for anyone else:

- The Hugging Face dataset card and the Hub API for `ai4bharat/IndicSentiment`
  have **no license field**. `cardData` only contains `language`. There is no
  LICENSE file in the dataset repo.
- The paper’s ethics statement (arXiv:2212.05409) says the dataset will be
  released under a **CC-0** license. Code and models are MIT.
- The [AI4Bharat/IndicBERT README](https://github.com/AI4Bharat/IndicBERT/blob/main/README.md),
  which hosts IndicSentiment as part of IndicXTREME, says: “All the datasets
  created as part of this work will be released under a CC-0 license and all
  models & code will be release under an MIT license.”
- The MTEB mirror `mteb/IndicSentiment` declares `cc0-1.0`.

We treat the sample as CC-0 on the strength of the paper and the IndicBERT
README, and we record the missing HF license field as a caveat. The CC-0 1.0
text is in `licenses/CC0-1.0.txt`.
