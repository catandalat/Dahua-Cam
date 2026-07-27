from io import BytesIO

from PIL import Image

from domain.speed_capture import stamp_speed_on_image


def test_stamp_speed_on_image_contains_jpeg():
    img = Image.new("RGB", (640, 360), color=(40, 60, 80))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    stamped = stamp_speed_on_image(
        buf.getvalue(),
        speed=112,
        limit_max=60,
        peak_speed=118,
        plate="30A12345",
        camera_name="Demo Entry",
    )
    assert stamped[:3] == b"\xff\xd8\xff"
    out = Image.open(BytesIO(stamped))
    assert out.size == (640, 360)
