from domain.overlay_gate import (
    detection_hits_overlay,
    is_noise_event_code,
    is_passage_event_code,
    overlay_gate_required,
)


LANE = {
    "id": "1",
    "type": "lane_line",
    "points": [[130, 5233], [4710, 5461]],
}


def test_overlay_gate_required():
    assert overlay_gate_required([LANE]) is True
    assert overlay_gate_required([]) is False
    assert overlay_gate_required([{"type": "lane_line", "points": [[1, 2]]}]) is False


def test_lane_near_accepts():
    # plate near lane y≈5233
    assert detection_hits_overlay(
        [LANE],
        plate_bbox=[1128, 5064, 1432, 5384],
    )


def test_motorcycle_approaching_line_accepts():
    # Real skip case: bike bottom ~4552, plate ~4416 — near corridor of lane y~5300
    assert detection_hits_overlay(
        [LANE],
        vehicle_bbox=[2664, 2808, 4776, 4552],
        plate_bbox=[3520, 4328, 3664, 4520],
        vehicle_class="motorcycle",
    )


def test_motorcycle_midframe_accepts_with_wide_threshold():
    assert detection_hits_overlay(
        [LANE],
        vehicle_bbox=[3000, 3500, 3800, 4300],
        vehicle_class="motorcycle",
    )


def test_lane_far_rejects():
    # plate far above lane (y≈3200)
    assert not detection_hits_overlay(
        [LANE],
        plate_bbox=[4592, 3136, 4736, 3392],
    )


def test_no_shapes_passthrough():
    assert detection_hits_overlay([], plate_bbox=[1, 2, 3, 4]) is True


def test_region_contains():
    region = {
        "type": "region",
        "points": [[0, 0], [8000, 0], [8000, 8000], [0, 8000]],
    }
    assert detection_hits_overlay([region], vehicle_bbox=[100, 100, 200, 200])
    assert not detection_hits_overlay(
        [{"type": "region", "points": [[0, 0], [100, 0], [100, 100], [0, 100]]}],
        vehicle_bbox=[5000, 5000, 5100, 5100],
    )


def test_noise_and_passage_codes():
    assert is_noise_event_code("TrafficVehiclePosition")
    assert is_noise_event_code("TrafficManualSnap")
    assert not is_noise_event_code("TrafficJunction")
    assert is_passage_event_code("TrafficJunction")
    assert is_passage_event_code("TrafficCarMeasurement")
    assert not is_passage_event_code("TrafficManualSnap")
