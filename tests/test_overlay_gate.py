from domain.overlay_gate import (
    detection_hits_overlay,
    is_noise_event_code,
    is_passage_event_code,
    overlay_gate_required,
)


LANE = {
    "id": "1",
    "type": "lane_line",
    # Matches Camera Cổng MobiFone synced DetectLine
    "points": [[41, 4827], [4735, 5361]],
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
    # Bike plate near corridor of lane y~5300
    assert detection_hits_overlay(
        [LANE],
        vehicle_bbox=[2664, 2808, 4776, 4552],
        plate_bbox=[3520, 4328, 3664, 4520],
        vehicle_class="motorcycle",
    )


def test_clothing_false_ocr_behind_line_rejects():
    # Runtime evidence: 57R6409 ManualSnap — tall plate on shirt, ~1418px before line.
    assert not detection_hits_overlay(
        [LANE],
        vehicle_bbox=[304, 1856, 3328, 3856],
        plate_bbox=[1168, 3240, 1360, 3528],
        vehicle_class="car",
    )


def test_approaching_car_wide_plate_accepts():
    # 92G15255 / 49A81434 — wide plate ManualSnap while approaching
    assert detection_hits_overlay(
        [LANE],
        vehicle_bbox=[496, 1848, 3312, 3880],
        plate_bbox=[2704, 3352, 3024, 3544],
        vehicle_class="car",
    )
    assert detection_hits_overlay(
        [LANE],
        plate_bbox=[3416, 3168, 3720, 3344],
        vehicle_class="car",
    )


def test_inbound_moto_plate_pattern_accepts_early():
    # Tall plate + VN 9-char moto number → allow approach ManualSnap (~1400px)
    assert detection_hits_overlay(
        [LANE],
        plate_bbox=[1176, 3240, 1368, 3520],
        vehicle_class="motorcycle",
        plate_number="59B123456",
    )
    # Tall 8-char valid plate (common moto OCR)
    assert detection_hits_overlay(
        [LANE],
        plate_bbox=[1176, 3240, 1368, 3520],
        plate_number="59R45429",
    )


def test_clothing_car_shaped_tall_plate_still_rejects():
    # 57R6409 clothing: tall bbox but car-shaped 7-char number, ~1418px out
    assert not detection_hits_overlay(
        [LANE],
        vehicle_bbox=[304, 1856, 3328, 3856],
        plate_bbox=[1168, 3240, 1360, 3528],
        plate_number="57R6409",
    )


def test_past_line_late_snap_accepts():
    # 49B02391 — plate already past the line (late snap)
    assert detection_hits_overlay(
        [LANE],
        plate_bbox=[2112, 6528, 2576, 6960],
        vehicle_class="car",
    )


def test_real_junction_on_line_accepts():
    assert detection_hits_overlay(
        [LANE],
        plate_bbox=[1376, 4992, 1776, 5360],
        vehicle_class="car",
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
    assert is_noise_event_code("TrafficVehicleInParkingSpace")
    assert not is_noise_event_code("TrafficManualSnap")
    assert not is_noise_event_code("TrafficJunction")
    assert is_passage_event_code("TrafficJunction")
    assert is_passage_event_code("TrafficCarMeasurement")
    assert is_passage_event_code("TrafficManualSnap")
