from benchmarks.check_replicate_summary import DEFAULT_SUMMARIES, verify_summary


def test_replicate_packages_and_summaries_are_consistent() -> None:
    for summary in DEFAULT_SUMMARIES:
        assert verify_summary(summary, replay_reports=False) == []
