from __future__ import annotations

"""Confidence and novelty state used by category-scoped Full discovery.

The stop rule is a bounded discovery heuristic: it requires a minimum number
of hypotheses, enough motif coverage, and a low posterior upper bound for new
hypotheses.  It does not estimate the probability that a mutation is a real
business weakness; that probability is measured only by completed runtime
replicates.
"""

from dataclasses import asdict, dataclass, field
from statistics import NormalDist
from typing import Any


@dataclass(frozen=True)
class StopDecision:
    stop: bool
    reason: str
    generated: int
    novel_count: int
    duplicate_count: int
    upper95: float
    feature_coverage: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NoveltyDecision:
    novel: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def beta_upper95(alpha: float, beta: float) -> float:
    """Approximate the 95% posterior upper bound for a Beta distribution."""
    mean = alpha / (alpha + beta)
    variance = (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1))
    upper = mean + NormalDist().inv_cdf(0.95) * (variance ** 0.5)
    return round(max(0.0, min(1.0, upper)), 6)


@dataclass
class ConfidenceState:
    category: str
    min_hypotheses: int
    max_hypotheses: int
    tau: float
    coverage_target: float
    novel_count: int = 0
    duplicate_count: int = 0
    covered_motifs: set[str] = field(default_factory=set)
    trace: list[dict[str, Any]] = field(default_factory=list)

    @property
    def generated(self) -> int:
        return self.novel_count + self.duplicate_count

    def observe(
        self,
        novel: bool,
        covered_motifs: set[str],
        required_motifs: set[str],
    ) -> StopDecision:
        if novel:
            self.novel_count += 1
        else:
            self.duplicate_count += 1

        self.covered_motifs.update(covered_motifs)
        alpha = 1 + self.novel_count
        beta = 1 + self.duplicate_count
        upper95 = beta_upper95(alpha, beta)
        coverage = (
            len(self.covered_motifs & required_motifs) / len(required_motifs)
            if required_motifs
            else 1.0
        )

        reason = "continue"
        stop = False
        if self.generated >= self.max_hypotheses:
            stop = True
            reason = "max_hypotheses"
        elif (
            self.generated >= self.min_hypotheses
            and coverage >= self.coverage_target
            and upper95 < self.tau
        ):
            stop = True
            reason = "confidence_saturated"

        decision = StopDecision(
            stop=stop,
            reason=reason,
            generated=self.generated,
            novel_count=self.novel_count,
            duplicate_count=self.duplicate_count,
            upper95=upper95,
            feature_coverage=round(coverage, 6),
        )
        self.trace.append(decision.to_dict())
        return decision


def judge_novelty(
    hypothesis: dict[str, Any],
    seen: list[dict[str, Any]],
    required_motifs: set[str],
) -> NoveltyDecision:
    reasons: list[str] = []
    seen_services = {item.get("target_service") for item in seen}
    seen_actions = {item.get("action_or_target") for item in seen}
    seen_positions = {item.get("call_chain_position") for item in seen}
    seen_motifs = {
        motif
        for item in seen
        for motif in item.get("motifs", [])
    }

    motifs = set(hypothesis.get("motifs", []))
    if hypothesis.get("target_service") not in seen_services:
        reasons.append("new_target_service")
    if hypothesis.get("action_or_target") not in seen_actions:
        reasons.append("new_action_or_target")
    if hypothesis.get("call_chain_position") not in seen_positions:
        reasons.append("new_call_chain_position")
    if (motifs & required_motifs) - seen_motifs:
        reasons.append("new_required_motif")

    return NoveltyDecision(novel=bool(reasons), reasons=reasons)
