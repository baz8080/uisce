# Model and runtime benchmarks for duration inference

Findings from a benchmarking session on 2026-07-15, kept here so the reasoning isn't lost to chat history. The question was whether `uisce-infer` (see `src/uisce/inference.py`) could be made faster — by prompt caching, request concurrency, a different model, speculative decoding, or the MLX runtime. Short answer: no. Every avenue tested either lost accuracy, gained nothing, or was blocked by the runtime. The current setup — `gemma-4-12b-qat` (GGUF) on LM Studio, plain sequential requests — is the right one.

All accuracy comparisons below re-ran the same 567 records from the 2026-07-15 inference run (419 unique descriptions after the multi-pin dedupe), with the same prompt (version 1) and temperature 0, and diffed `end_source` / `local_date` / `local_time` per case against the gemma baseline.

## Where the time actually goes

- Prefill of the full ~1,000-token prompt+description costs only ~0.6s (~1,700 tok/s). Resending the static prompt with every request is **not** the bottleneck — don't bother restructuring the prompt for caching.
- Decode dominates: most of each ~1.9s request is generating the ~75-token JSON response at ~57 tok/s. The `notes`-first reasoning field is most of that output, and it's also what makes extraction reliable, so it isn't worth trimming.

## Concurrency: no win

LM Studio serializes requests by default (4 parallel requests = same wall time as 4 sequential). `lms load --parallel 4` does enable server-side slots, but: (a) the slots split the context window, so the context length must be raised (e.g. `-c 16384`) or requests fail with "Context size has been exceeded"; and (b) it only bought ~1.1x on this machine — decode is memory-bandwidth-bound on Apple Silicon, so parallel slots mostly queue on the same weights.

## qwen3.5-9b: faster, but wrong too often

1.15s/call (~40% faster than gemma), but only 61% full agreement, and on manual inspection of the disagreements gemma was right in nearly all of them. Qwen's failure modes were disqualifying, not cosmetic:

- Refused to extract the completion time from `**Update 9am 15/07/2026**` header blocks (150 cases — returned a null time while inconsistently still using the header *date*).
- Outright 12h→24h conversion errors: 1:36pm→16:36, 3:50pm→17:50, etc. (all 20 unique both-set time mismatches were qwen errors).
- Mislabelled completion updates as `lifted_immediate` or `not_found`; misread boil-water notices *issued* "with immediate effect" as lifted.
- The one category qwen won (8 cases): "nightly from 11:30pm until 5am between X and Y" → it extracted 05:00 as `scheduled_end_with_time` where gemma chose `scheduled_end_date_only`. That's a candidate prompt tweak, not a reason to switch.

Operational note: Qwen models in LM Studio default to thinking mode (~4,000 reasoning tokens, ~49s/call). The only thing that disables it through the API is a top-level `"reasoning_effort": "none"` in the request payload — `chat_template_kwargs` and `/no_think` do not work.

## Speculative decoding: blocked by the current GGUF

Would be the natural speed lever (formulaic JSON output → high draft acceptance, identical output at temperature 0), but every route is closed with the current model file:

- The gemma-4-12b-qat GGUF has no bundled MTP head, so `--speculative-draft-mtp` is rejected.
- Load-time `--speculative-draft-simple` is only supported by LM Studio's "llama.cpp engine protocol" runtime, not the native runtime in use.
- Prediction-time `"draft_model"` in the payload is recognized, but llama.cpp server refuses speculative decoding for multimodal models, and this GGUF bundles the vision tower. (A `"speculative_decoding": {...}` payload spelling is silently ignored — verified by timing.)

Making it work would need a text-only gemma-4-12b GGUF (~7GB).

## gemma-4-26B-A4B (MoE) on MLX: identical answers, slower

`lmstudio-community/gemma-4-26B-A4B-it-QAT-MLX-4bit` — the hope was MLX runtime speed plus only ~4B active params per token. Result:

- **100% agreement with gemma-4-12b-qat on all 567 records** — same values everywhere, including the same date-only call on the nightly-works cases. This task appears saturated at 12B; the bigger model adds nothing.
- **2.70s/call vs ~1.9s** on the real workload. Short requests tie (~1.35s), but the MoE loses on prefill-heavy long descriptions. MLX showed no runtime advantage over llama.cpp/GGUF on this machine.