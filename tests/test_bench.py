"""The benchmark times the check on operations it allows and on approvals it accepts."""

from poia_agents.bench import measure


def test_benchmark_times_every_part():
    result = measure(100)
    assert list(result) == [
        "check per operation",
        "  agent signature alone",
        "template approval, ZT-Authenticator",
        "template approval, passkey",
    ]
    assert [values["runs"] for values in result.values()] == [100, 100, 10, 10]
    assert all(0 < values["median_us"] <= values["p99_us"] for values in result.values())
