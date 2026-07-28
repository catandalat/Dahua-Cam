from domain.vehicle_class import classify_vehicle, clean_camera_attr
from domain.plate import is_vn_motorcycle_plate, is_valid_vn_plate
from domain.colors import resolve_vehicle_color, color_label_vi, rgb_to_color_name


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


def test_medium_duty_is_truck_not_motorcycle():
    assert (
        classify_vehicle(
            None,
            snap_category="Motor",
            vehicle_size="Medium-duty",
            plate_bbox=[100, 100, 200, 300],
        )
        == "truck"
    )


def test_tall_plate_on_wide_body_is_car_not_moto():
    # Tall plate crop but very wide vehicle body → car (not moto)
    tall_pb = [100, 100, 200, 280]
    wide_vb = [0, 2000, 4000, 4500]  # w=4000, h=2500, ratio 1.6
    assert (
        classify_vehicle(
            None,
            snap_category="Motor",
            vehicle_size="Light-duty",
            plate_bbox=tall_pb,
            vehicle_bbox=wide_vb,
        )
        == "car"
    )


def test_vn_nine_char_plate_is_motorcycle():
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


def test_vn_eight_char_tall_is_motorcycle():
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


def test_colors():
    assert resolve_vehicle_color("Unknown", rgb=[255, 0, 0]) == "Red"
    assert resolve_vehicle_color("Blue") == "Blue"
    assert color_label_vi("White") == "Trắng"
    assert rgb_to_color_name([255, 255, 255, 0]) == "White"
    assert is_valid_vn_plate("49A42576")
    assert not is_valid_vn_plate("K8760454")


def test_snap_nonmotor_is_motorcycle():
    assert classify_vehicle(None, snap_category="NonMotor") == "motorcycle"


def test_normalcar_list_status_ignored():
    assert classify_vehicle("NormalCar") == "unknown"
    assert classify_vehicle("Unknown", object_type="Vehicle") == "car"
