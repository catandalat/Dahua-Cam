from domain.vehicle_class import classify_vehicle, clean_camera_attr


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
    assert (
        classify_vehicle(
            None,
            snap_category="Motor",
            vehicle_size="Light-duty",
            plate_number="59B123456",
        )
        == "motorcycle"
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


def test_snap_nonmotor_is_motorcycle():
    assert classify_vehicle(None, snap_category="NonMotor") == "motorcycle"


def test_normalcar_list_status_ignored():
    # TrafficCar.CarType=NormalCar is allow-list status, not body type
    assert classify_vehicle("NormalCar") == "unknown"
    assert classify_vehicle("Unknown", object_type="Vehicle") == "car"
