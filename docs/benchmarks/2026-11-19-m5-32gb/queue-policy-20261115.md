# 32 GiB unified-memory queue policy

Hardware: Apple M5 MacBook Air, 32 GiB unified memory. The practical target is real-time meeting translation and occasional image understanding.

## Decision

- Keep 9B–14B Q4/Q8 configurations as the primary real-time candidates.
- Keep 27B Q4 results as an offline quality reference; do not add 27B Q8 to the active queue.
- Keep 32B Q4 and MoE entries such as Qwen3 30B-A3B Q4 as explicit upper-bound tests. They are useful for quality and feasibility comparisons, but the run showed about 4–5 tok/s and about 1.5 GiB swap use, so they are not the primary real-time candidates.
- Remove unfinished 70B configurations and all unfinished 27B-or-larger Q8 configurations from the active queue. Keep the DeepSeek-R1 32B Q4 entry for the requested 32B dense-model comparison.
- For image understanding, prioritize models whose metadata includes `vision` (currently Gemma 3 and Qwen3.5/Qwen3.6 entries) rather than increasing parameter count.

The active queue is stored in `data/queue.json`. Removed entries are preserved in the timestamped `excluded-models-*.json` record, and all completed result folders remain intact.
