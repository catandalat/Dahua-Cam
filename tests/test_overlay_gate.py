from domain.overlay_gate import (
    detection_hits_overlay,
    is_noise_event_code,
    is_passage_event_code,
    overlay_gate_required,
    region_to_detect_quad,
)


LANE = {
    "id": "1",
    "type": "lane_line",
    # Matches Camera Cổng MobiFone synced DetectLine
    "points": [[41, 4827], [4735, 5361]],
}

# Gate corridor around the lane (region-first mode)
REGION = {
    "id": "r1",
    "type": "region",
    "points": [
        [0, 4500],
        [5000, 4500],
        [5000, 7500],
        [0, 7500],
    ],
}


def test_overlay_gate_required():
    assert overlay_gate_required([LANE]) is True
    assert overlay_gate_required([REGION]) is True
    assert overlay_gate_required([]) is False
    assert overlay_gate_required([{"type": "lane_line", "points": [[1, 2]]}]) is False


def test_lane_near_accepts():
    assert detection_hits_overlay(
        [LANE],
        plate_bbox=[1128, 5064, 1432, 5384],
    )


def test_car_body_without_plate_rejects():
    # Giant mid-frame car body must NOT invent a line hit
    assert not detection_hits_overlay(
        [LANE],
        vehicle_bbox=[536, 1952, 3256, 3840],
        vehicle_class="car",
    )


def test_car_plate_far_outside_rejects():
    # Approach-side car OCR ~1400–2000px out of corridor
    assert not detection_hits_overlay(
        [LANE],
        vehicle_bbox=[536, 1768, 3304, 3880],
        plate_bbox=[2520, 2632, 2872, 2824],
        vehicle_class="car",
        plate_number="84F09292",
    )


def test_clothing_false_ocr_behind_line_rejects():
    assert not detection_hits_overlay(
        [LANE],
        vehicle_bbox=[304, 1856, 3328, 3856],
        plate_bbox=[1168, 3240, 1360, 3528],
        vehicle_class="car",
        plate_number="57R6409",
    )


def test_real_junction_on_line_accepts():
    assert detection_hits_overlay(
        [LANE],
        plate_bbox=[1376, 4992, 1776, 5360],
        vehicle_class="car",
    )


def test_past_line_late_snap_accepts():
    assert detection_hits_overlay(
        [LANE],
        plate_bbox=[2112, 6528, 2576, 6960],
        vehicle_class="car",
    )


def test_inbound_moto_near_corridor_accepts():
    assert detection_hits_overlay(
        [LANE],
        plate_bbox=[3520, 4328, 3664, 4520],
        vehicle_class="motorcycle",
        plate_number="59B123456",
    )


def test_zero_plate_bbox_ignored():
    assert not detection_hits_overlay(
        [LANE],
        vehicle_bbox=[80, 2816, 1584, 4320],
        plate_bbox=[0, 0, 0, 0],
        vehicle_class="car",
        plate_number="49H30534",
    )


def test_no_shapes_passthrough():
    assert detection_hits_overlay([], plate_bbox=[1, 2, 3, 4]) is True


def test_region_inside_accepts():
    assert detection_hits_overlay(
        [REGION],
        plate_bbox=[1376, 4992, 1776, 5360],
        vehicle_class="car",
    )


def test_region_outside_rejects_even_near_line():
    # Plate far above region — rejected even if a lane line would have accepted it
    assert not detection_hits_overlay(
        [REGION, LANE],
        plate_bbox=[2520, 2632, 2872, 2824],
        vehicle_class="car",
        plate_number="84F09292",
    )


def test_region_ignores_giant_body_corner():
    # Body overlaps region but plate center is outside → reject
    assert not detection_hits_overlay(
        [REGION],
        vehicle_bbox=[1000, 2000, 4000, 6000],
        plate_bbox=[2520, 2632, 2872, 2824],
        vehicle_class="car",
        plate_number="84F09292",
    )


def test_region_car_without_plate_rejects():
    assert not detection_hits_overlay(
        [REGION],
        vehicle_bbox=[1000, 4800, 3000, 6000],
        vehicle_class="car",
    )


def test_region_bike_body_inside_accepts():
    assert detection_hits_overlay(
        [REGION],
        vehicle_bbox=[2000, 5000, 2800, 6200],
        vehicle_class="motorcycle",
    )


def test_region_to_detect_quad():
    q = region_to_detect_quad(REGION["points"])
    assert q == [[0, 4500], [5000, 4500], [5000, 7500], [0, 7500]]


def test_noise_and_passage_codes():
    assert is_noise_event_code("TrafficVehicleInParkingSpace")
    assert not is_noise_event_code("TrafficManualSnap")
    assert is_passage_event_code("TrafficJunction")
    assert is_passage_event_code("TrafficManualSnap")
