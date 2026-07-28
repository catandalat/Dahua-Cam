from dahua_client.kv_parser import dig, kv_lines_to_dict
from dahua_client.extract import extract_detection, extract_violations
from dahua_client.multipart import MultipartEvent, parse_multipart_buffer
from domain.plate import normalize_plate
from domain.session import resolve_passage_direction
from domain.schemas import DirectionRole


def test_normalize_plate():
    assert normalize_plate(" 30A-123.45 ") == "30A12345"
    assert normalize_plate(None) is None


def test_classify_vehicle():
    from domain.vehicle_class import classify_vehicle

    assert classify_vehicle("Car") == "car"
    assert classify_vehicle("Truck") == "truck"
    assert classify_vehicle("Motorcycle") == "motorcycle"
    assert classify_vehicle("LightMotorcycle") == "motorcycle"
    assert classify_vehicle("Bicycle") == "motorcycle"
    assert classify_vehicle(None, event_code="TrafficNonMotorWithoutSafehat") == "motorcycle"


def test_kv_parser_nested():
    text = """
Events[0].EventBaseInfo.Code=TrafficJunction
Events[0].TrafficCar.PlateNumber=30A12345
Events[0].CommInfo.Seat[0].Type=Main
Events[0].CommInfo.Seat[0].SafeBelt=WithoutSafeBelt
Events[0].CommInfo.Seat[0].Status[0]=Calling
Events[0].Speed=42
"""
    data = kv_lines_to_dict(text)
    assert dig(data, "Events[0].EventBaseInfo.Code") == "TrafficJunction"
    assert dig(data, "Events[0].TrafficCar.PlateNumber") == "30A12345"
    assert dig(data, "Events[0].CommInfo.Seat[0].SafeBelt") == "WithoutSafeBelt"


def test_extract_detection_and_violations():
    text = """
Events[0].EventBaseInfo.Code=TrafficJunction
Events[0].TrafficCar.PlateNumber=51F-987.65
Events[0].Vehicle.Text=Toyota
Events[0].Vehicle.SubText=Vios
Events[0].MainSeat=WithoutSafeBelt
Events[0].UTC=1700000000
"""
    event = MultipartEvent(text=text, data=kv_lines_to_dict(text))
    det = extract_detection(event)
    assert det["plate_number"] == "51F98765"
    assert det["vehicle_brand"] == "Toyota"
    viols = extract_violations(det)
    assert any(v["violation_type"] == "seatbelt" for v in viols)


def test_resolve_direction():
    assert resolve_passage_direction(DirectionRole.ENTRY, None) == "entry"
    assert resolve_passage_direction(DirectionRole.EXIT, 0) == "exit"
    assert resolve_passage_direction(DirectionRole.BIDIRECTIONAL, 0) == "entry"
    assert resolve_passage_direction(DirectionRole.BIDIRECTIONAL, 1) == "exit"


def test_extract_unlicensed_and_bbox():
    text = """
Events[0].EventBaseInfo.Code=TrafficJunction
Events[0].Vehicle.Text=Honda
Events[0].Vehicle.BoundingBox[0]=1
Events[0].Vehicle.BoundingBox[1]=2
Events[0].Vehicle.BoundingBox[2]=3
Events[0].Vehicle.BoundingBox[3]=4
Events[0].UTC=1700000000
"""
    event = MultipartEvent(text=text, data=kv_lines_to_dict(text))
    det = extract_detection(event)
    assert det["unlicensed"] is True
    assert det["vehicle_bbox"] == [1, 2, 3, 4]
    viols = extract_violations(det)
    assert any(v["violation_type"] == "unlicensed" for v in viols)


def test_extract_jam():
    from dahua_client.extract import extract_jam_event

    text = """
Events[0].EventBaseInfo.Code=TrafficJam
Events[0].JamLenght=55
Events[0].JamRealLength=120
Events[0].Lane=1
"""
    event = MultipartEvent(text=text, data=kv_lines_to_dict(text))
    jam = extract_jam_event(event)
    assert jam is not None
    assert jam["jam_length_pct"] == 55
    assert jam["jam_real_length_m"] == 120


def test_multipart_heartbeat():
    boundary = b"myboundary"
    body = (
        b"--myboundary\r\n"
        b"Content-Type: text/plain\r\n\r\n"
        b"Heartbeat\r\n"
        b"--myboundary\r\n"
        b"Content-Type: text/plain\r\n\r\n"
        b"Events[0].EventBaseInfo.Code=TrafficCarMeasurement\r\n"
        b"Events[0].TrafficCar.PlateNumber=29A11111\r\n"
        b"Events[0].TriggerOccur=0\r\n"
        b"--myboundary--"
    )
    events = parse_multipart_buffer(body, boundary)
    assert events[0].is_heartbeat
    assert events[1].event_code == "TrafficCarMeasurement"


def test_code_data_json_block_with_plate():
    text = """Code=TrafficJunction;action=Pulse;index=0;data={
   "Name" : "TrafficJunction",
   "TrafficCar" : {
      "PlateNumber" : "51F-123.45",
      "VehicleColor" : "White"
   },
   "Vehicle" : {
      "Category" : "Car",
      "Text" : "Toyota"
   },
   "Speed" : 42,
   "UTC" : 1700000000
}
"""
    data = kv_lines_to_dict(text)
    assert dig(data, "Code") == "TrafficJunction"
    assert dig(data, "Events[0].TrafficCar.PlateNumber") == "51F-123.45"
    assert dig(data, "Events[0].Vehicle.Category") == "Car"
    event = MultipartEvent(text=text, data=data)
    det = extract_detection(event)
    assert det["event_code"] == "TrafficJunction"
    assert det["plate_number"] == "51F12345"
    assert det["vehicle_class"] == "car"
    assert det["vehicle_category"] == "Car"
    assert det["speed"] == 42


def test_code_data_json_block_without_plate_motorcycle():
    text = """Code=TrafficJunction;action=Pulse;index=0;data={
   "NonMotor" : {
      "Category" : "Motorcycle",
      "Color" : "Black"
   },
   "UTC" : 1700000000
}
"""
    data = kv_lines_to_dict(text)
    event = MultipartEvent(text=text, data=data)
    det = extract_detection(event)
    assert det["plate_number"] is None
    assert det["vehicle_class"] == "motorcycle"
    assert det["vehicle_category"] == "Motorcycle"
    assert det["unlicensed"] is True


def test_extract_detections_splits_car_and_motorcycle():
    from dahua_client.extract import extract_detections

    text = """Code=TrafficManualSnap;action=Pulse;index=0;data={
   "TrafficCar" : {
      "PlateNumber" : "51A12345",
      "VehicleSize" : "Light-duty"
   },
   "Vehicle" : {
      "BoundingBox" : [100, 2000, 4000, 5000],
      "Category" : "Car"
   },
   "Object" : {
      "PlateNumber" : "51A12345",
      "BoundingBox" : [2000, 4500, 2400, 4700],
      "Confidence" : 90
   },
   "NonMotor" : {
      "Category" : "Motorcycle",
      "Color" : "Red",
      "BoundingBox" : [500, 4000, 1800, 5500],
      "PlateNumber" : "49B123456",
      "Object" : {
         "BoundingBox" : [900, 5000, 1100, 5300],
         "Confidence" : 80
      }
   },
   "CommInfo" : { "SnapCategory" : "Motor" },
   "UTC" : 1700000000
}
"""
    data = kv_lines_to_dict(text)
    event = MultipartEvent(text=text, data=data)
    dets = extract_detections(event)
    classes = {d["vehicle_class"] for d in dets}
    plates = {d["plate_number"] for d in dets}
    assert "car" in classes
    assert "motorcycle" in classes
    assert "51A12345" in plates
    assert "49B123456" in plates
    assert len(dets) == 2

