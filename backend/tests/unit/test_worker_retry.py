from newsintel.workers.poller import database_retry_delay


def test_database_retry_delay_is_exponential_and_bounded() -> None:
    assert database_retry_delay(1, 30) == 2
    assert database_retry_delay(2, 30) == 4
    assert database_retry_delay(5, 30) == 30
    assert database_retry_delay(100, 30) == 30

