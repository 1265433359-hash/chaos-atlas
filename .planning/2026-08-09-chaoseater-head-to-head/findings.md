# Design Constraints

- The current 20-candidate pool is a pilot only: it was partly selected from the M4 lineage and must not be the sole final benchmark.
- Blind selection must not expose runtime cards, classifications, candidate truth labels, or previous method selections.
- Official ChaosEater and the local adapter are separate conditions; if the official implementation cannot be run at a pinned commit, mark it blocked_external_reproduction.
- Atomic one-target mutations and composite workflows require separate tracks; forcing both into one schema would bias the comparison.
- Ground truth must distinguish weakness, below_threshold, defended, invalid/not_injected and not_applicable.
