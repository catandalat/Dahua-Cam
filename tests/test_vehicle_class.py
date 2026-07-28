from domain.vehicle_class import classify_vehicle, clean_camera_attr
from domain.plate import is_vn_motorcycle_plate, is_valid_vn_plate


def test_clean_unknown():
    assert clean_camera_attr("Unknown") is None
    assert clean_camera_attr("White") == "White"
    assert clean_camera_attr("") is None


def test_snap_motor_is_car_not_motorcycle():
    assert (
        classify_vehicle(
            None,
            snap_category="Motor",
            object_type="Vehicle",
            vehicle_size="Light-duty",
        )
        == "car"
    )


def test_tall_plate_bbox_overrides_light_duty_as_motorcycle():
    # Two-line VN moto plate from camera (taller than wide)
    pb = [1176, 3232, 1368, 3520]
    assert (
        classify_vehicle(
            None,
            snap_category="Motor",
            object_type="Vehicle",
            vehicle_size="Light-duty",
            plate_bbox=pb,
            plate_number="59H6409",
        )
        == "motorcycle"
    )


def test_vn_nine_char_plate_is_motorcycle():
    # Camera evidence: 41D074011
    assert (
        classify_vehicle(
            None,
            snap_category="Motor",
            vehicle_size="Light-duty",
            plate_number="41D074011",
        )
        == "motorcycle"
    )
    assert is_vn_motorcycle_plate("41D074011")
    assert is_vn_motorcycle_plate("59B123456")


def test_vn_eight_char_tall_is_motorcycle():
    # Camera evidence: 49C04891 exit Tail — tall 2-line bbox
    pb = [2072, 5424, 2360, 5840]
    assert is_vn_motorcycle_plate("49C04891", plate_bbox=pb)
    assert (
        classify_vehicle(
            None,
            snap_category="Motor",
            vehicle_size="Light-duty",
            plate_number="49C04891",
            plate_bbox=pb,
        )
        == "motorcycle"
    )


def test_vn_eight_char_wide_stays_car_without_tall_bbox():
    # Same number on entry with wide crop — treat as car unless bbox says moto
    pb = [4080, 4384, 4416, 4576]
    assert not is_vn_motorcycle_plate("49C04891", plate_bbox=pb)
    assert (
        classify_vehicle(
            None,
            snap_category="Motor",
            vehicle_size="Light-duty",
            plate_number="49C04891",
            plate_bbox=pb,
        )
        == "car"
    )


def test_wide_car_plate_stays_car():
    pb = [100, 100, 564, 232]
    assert (
        classify_vehicle(
            None,
            snap_category="Motor",
            vehicle_size="Light-duty",
            plate_bbox=pb,
            plate_number="51F12345",
        )
        == "car"
    )


def test_invalid_plates_rejected():
    assert not is_valid_vn_plate("OO8313")
    assert not is_valid_vn_plate("K8760454")
    assert is_valid_vn_plate("49A42576")


def test_snap_nonmotor_is_motorcycle():
    assert classify_vehicle(None, snap_category="NonMotor") == "motorcycle"


def test_normalcar_list_status_ignored():
    # TrafficCar.CarType=NormalCar is allow-list status, not body type
    assert classify_vehicle("NormalCar") == "unknown"
    assert classify_vehicle("Unknown", object_type="Vehicle") == "car"
