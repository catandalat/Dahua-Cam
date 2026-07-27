import pytest
from domain.plate import normalize_plate


def test_watch_plate_normalize_match():
    assert normalize_plate("30A-123.45") == normalize_plate("30A12345")


@pytest.mark.asyncio
async def test_watch_match_logic_imports():
    from domain.watch import alert_to_payload, find_matching_watches

    assert callable(find_matching_watches)
    assert callable(alert_to_payload)
