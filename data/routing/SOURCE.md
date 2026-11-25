# Request-routing sample source

Amazon MASSIVE (CC BY 4.0): short assistant-style requests.

- Hugging Face dataset: [`AmazonScience/massive`](https://huggingface.co/datasets/AmazonScience/massive)
- Pinned Hugging Face revision: `ff6bd8e4b27c3543e4f8fe2108f32bb95a6f8740` (checked 25 November 2026). The dataset card lists `license: cc-by-4.0`. The `LICENSE` file in that revision and in the official 1.1 archive is the Creative Commons Attribution 4.0 International Public License. A copy is at [`licenses/CC-BY-4.0.txt`](../../licenses/CC-BY-4.0.txt).
- Official 1.1 archive: `https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz`
- Archive sha256: `4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577`
- Locales used: `en-US`, `hi-IN`, `ta-IN`. Utterance ids, intents, scenarios, and partition labels match across the three locales for every test item (2,974 test ids, no mismatches).
- Split: `test` only.
- Paper: FitzGerald et al., 2022, arXiv:2204.08582. Copyright Amazon.com Inc. or its affiliates.

The committed files in `upstream/` are the test split only, with fields `id`, `locale`, `partition`, `scenario`, `intent`, and `utt`. Rebuild the 80-row sample with `python prepare_routing.py` (offline if those files are present). The loader will download the official archive and check its sha256 only if a locale file is missing.

Intents are mapped onto six request-routing options that follow MASSIVE's own scenario groups, or dropped when the intent is ambiguous. The mapping and the one-line description sent to every model live in `indic_smoke/routing/mapping.py`. Ambiguous intents are not forced into a queue.

Items are also dropped when any of the English, Hindi, or Tamil texts contains a product wake word or assistant name, including common Hindi and Tamil spellings, or a hey/ok-style prefix immediately followed by one of those names. Tokenization keeps letters and combining marks together so a name is matched only as a whole word. On the 2,974-item test split, 133 items matched this filter (English 124, Hindi 121, Tamil 88; an item can match in more than one language). 102 of those had an otherwise mapped intent and were removed before sampling. 31 already sat in an unmapped intent. Details are in `indic_smoke/routing/filter.py`.

The sample is `requests.jsonl`: 80 ids, seed 42, 14 Calendar, 14 Info, and 13 each for SmartHome, Media, Orders, and Email, the same ids in English, Hindi, and Tamil. Eligible pool sizes after both filters: Calendar 626, SmartHome 204, Media 468, Orders 108, Info 711, Email 265.
