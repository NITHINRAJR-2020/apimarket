from app.policies.reputation import compute_reputation, record_latency_sample, load_latency_samples


def test_zero_transactions_gets_neutral_baseline():
    r = compute_reputation(
        successful_transactions=0, failed_transactions=0, average_latency_ms=200,
        refund_count=0, dispute_count=0,
    )
    assert r.total_volume == 0
    assert r.score == 60  # neutral baseline, no data at all


def test_single_success_does_not_score_near_perfect():
    r = compute_reputation(
        successful_transactions=1, failed_transactions=0, average_latency_ms=100,
        refund_count=0, dispute_count=0,
    )
    # 1/20 confidence weight -> heavily blended toward the neutral baseline,
    # so a single success must NOT look like a mature 90+ provider.
    assert r.total_volume == 1
    assert r.score < 70


def test_ten_transactions_partial_confidence():
    r = compute_reputation(
        successful_transactions=10, failed_transactions=0, average_latency_ms=150,
        refund_count=0, dispute_count=0,
    )
    assert 0.0 < r.confidence_weight < 1.0
    assert r.score > 60  # better than baseline but not fully confident yet


def test_twenty_plus_transactions_full_confidence():
    r = compute_reputation(
        successful_transactions=20, failed_transactions=0, average_latency_ms=100,
        refund_count=0, dispute_count=0,
    )
    assert r.confidence_weight == 1.0


def test_failures_refunds_disputes_lower_score():
    good = compute_reputation(
        successful_transactions=18, failed_transactions=2, average_latency_ms=100,
        refund_count=0, dispute_count=0,
    )
    bad = compute_reputation(
        successful_transactions=10, failed_transactions=10, average_latency_ms=100,
        refund_count=5, dispute_count=3,
    )
    assert bad.score < good.score


def test_latency_affects_score_via_p95_not_just_average():
    samples_consistent = None
    for _ in range(20):
        samples_consistent = record_latency_sample(samples_consistent, 100)

    samples_spiky = None
    for lat in [50] * 18 + [3000, 3000]:
        samples_spiky = record_latency_sample(samples_spiky, lat)

    consistent = compute_reputation(
        successful_transactions=20, failed_transactions=0, average_latency_ms=100,
        refund_count=0, dispute_count=0, latency_samples_json=samples_consistent,
    )
    spiky = compute_reputation(
        successful_transactions=20, failed_transactions=0, average_latency_ms=100,
        refund_count=0, dispute_count=0, latency_samples_json=samples_spiky,
    )
    # Same average-ish inputs, but the spiky tail should score worse
    # because scoring uses p95, not just the average.
    assert spiky.p95_latency_ms > consistent.p95_latency_ms
    assert spiky.score <= consistent.score


def test_latency_sample_window_is_bounded_and_favors_recent():
    samples = None
    for lat in [2000] * 60:  # more than the window
        samples = record_latency_sample(samples, lat)
    for lat in [50] * 10:  # then a burst of fast recent calls
        samples = record_latency_sample(samples, lat)

    loaded = load_latency_samples(samples)
    assert len(loaded) <= 50
    # recent fast calls should now dominate the buffer
    assert loaded[-1] == 50


def test_explainable_breakdown_fields_present():
    r = compute_reputation(
        successful_transactions=99, failed_transactions=1, average_latency_ms=320,
        refund_count=1, dispute_count=0,
    )
    assert 0 <= r.score <= 100
    assert r.success_rate == 0.99
    assert r.average_latency_ms >= 0
    assert r.p95_latency_ms >= 0
