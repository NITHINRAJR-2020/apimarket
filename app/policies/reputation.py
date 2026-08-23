"""Provider reputation scoring.

Deliberately simple and fully explainable -- this is NOT a fraud-detection
model. The score (0-100) is a weighted blend of four signals:

  - success rate      (60%): successful / (successful + failed)
  - latency            (15%): faster = better, capped at a 2s reference ceiling
  - refund rate        (15%): fewer refunds relative to volume = better
  - dispute rate       (10%): fewer disputes relative to volume = better

Providers with fewer than MIN_VOLUME_FOR_FULL_CONFIDENCE total transactions
get a neutral baseline blended in, so a brand-new provider with 1 success
doesn't score a misleading 100.
"""

import json
from dataclasses import dataclass

MIN_VOLUME_FOR_FULL_CONFIDENCE = 20
NEUTRAL_BASELINE_SCORE = 60.0
LATENCY_REFERENCE_CEILING_MS = 2000

# How many of the most recent upstream-call latencies we keep per listing.
# Recency bias comes for free: once the window is full, updating latency
# simply drops the oldest sample, so the score naturally favors recent
# performance over old performance without a separate decay model.
LATENCY_SAMPLE_WINDOW = 50

WEIGHT_SUCCESS_RATE = 0.60
WEIGHT_LATENCY = 0.15
WEIGHT_REFUND_RATE = 0.15
WEIGHT_DISPUTE_RATE = 0.10


@dataclass
class ReputationBreakdown:
    score: int
    success_rate: float
    latency_score: float
    refund_penalty: float
    dispute_penalty: float
    total_volume: int
    confidence_weight: float
    average_latency_ms: int
    p50_latency_ms: int
    p95_latency_ms: int
    refund_rate: float
    dispute_rate: float


def load_latency_samples(latency_samples_json: str | None) -> list[int]:
    if not latency_samples_json:
        return []
    try:
        samples = json.loads(latency_samples_json)
        return [int(s) for s in samples if isinstance(s, (int, float))]
    except (ValueError, TypeError):
        return []


def record_latency_sample(latency_samples_json: str | None, new_latency_ms: int) -> str:
    """Append a real, measured upstream-call latency to the ring buffer,
    dropping the oldest sample once LATENCY_SAMPLE_WINDOW is exceeded.
    Returns the new JSON-encoded buffer to store back on the Listing.
    """
    samples = load_latency_samples(latency_samples_json)
    samples.append(int(new_latency_ms))
    if len(samples) > LATENCY_SAMPLE_WINDOW:
        samples = samples[-LATENCY_SAMPLE_WINDOW:]
    return json.dumps(samples)


def _percentile(sorted_samples: list[int], pct: float) -> int:
    """Nearest-rank percentile: index = ceil(pct * n) - 1. Standard
    definition for p95/p50 that (unlike interpolating between the two
    middle-ish points) actually lands on the tail value for a spiky
    latency distribution, which is the point of tracking p95 at all."""
    import math

    if not sorted_samples:
        return 0
    n = len(sorted_samples)
    idx = min(n - 1, max(0, math.ceil(pct * n) - 1))
    return int(sorted_samples[idx])


def latency_percentiles(latency_samples_json: str | None, fallback_average_ms: int) -> tuple[int, int, int]:
    """Returns (average, p50, p95) latency in ms. Falls back to the
    listing's static average_latency_ms field when there are no real
    samples yet (e.g. a brand-new listing, or one created before this
    feature existed)."""
    samples = load_latency_samples(latency_samples_json)
    if not samples:
        return fallback_average_ms, fallback_average_ms, fallback_average_ms
    ordered = sorted(samples)
    average = round(sum(ordered) / len(ordered))
    return average, _percentile(ordered, 0.50), _percentile(ordered, 0.95)


def compute_reputation(
    *,
    successful_transactions: int,
    failed_transactions: int,
    average_latency_ms: int,
    refund_count: int,
    dispute_count: int,
    latency_samples_json: str | None = None,
) -> ReputationBreakdown:
    total_volume = successful_transactions + failed_transactions

    if total_volume == 0:
        success_rate = 1.0
    else:
        success_rate = successful_transactions / total_volume

    avg_latency, p50_latency, p95_latency = latency_percentiles(latency_samples_json, average_latency_ms)

    # p95 (not the average) drives the score: a provider that's fast most
    # of the time but has a long slow tail should not look as good as one
    # that's consistently fast, and p95 punishes that tail correctly.
    latency_score = max(0.0, 1.0 - min(p95_latency, LATENCY_REFERENCE_CEILING_MS) / LATENCY_REFERENCE_CEILING_MS)

    refund_rate = min(refund_count / max(total_volume, 1), 1.0)
    dispute_rate = min(dispute_count / max(total_volume, 1), 1.0)
    refund_penalty = 1.0 - refund_rate
    dispute_penalty = 1.0 - dispute_rate

    raw_score = (
        WEIGHT_SUCCESS_RATE * success_rate
        + WEIGHT_LATENCY * latency_score
        + WEIGHT_REFUND_RATE * refund_penalty
        + WEIGHT_DISPUTE_RATE * dispute_penalty
    ) * 100

    # Blend toward a neutral baseline for low-volume providers so early
    # transactions can't produce an overconfident extreme score.
    confidence_weight = min(total_volume / MIN_VOLUME_FOR_FULL_CONFIDENCE, 1.0)
    blended_score = confidence_weight * raw_score + (1 - confidence_weight) * NEUTRAL_BASELINE_SCORE

    return ReputationBreakdown(
        score=round(blended_score),
        success_rate=round(success_rate, 4),
        latency_score=round(latency_score, 4),
        refund_penalty=round(refund_penalty, 4),
        dispute_penalty=round(dispute_penalty, 4),
        total_volume=total_volume,
        confidence_weight=round(confidence_weight, 4),
        average_latency_ms=avg_latency,
        p50_latency_ms=p50_latency,
        p95_latency_ms=p95_latency,
        refund_rate=round(refund_rate, 4),
        dispute_rate=round(dispute_rate, 4),
    )
