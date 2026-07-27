# Dahua DHI-ITC413-PW4D-IZ3 — Tài liệu tham chiếu tính năng & API

> Nguồn: đối chiếu nhãn thiết bị thực tế + tài liệu chính thức "Dahua HTTP API V4.04"
> Model: **DHI-ITC413-PW4D-IZ3** — Smart ANPR Camera (dòng ITC — Intelligent Traffic Camera)
> Tài liệu này tổng hợp mọi tính năng camera **có thể hỗ trợ theo API** — cần xác nhận thực tế bằng `action=getCaps` trên firmware đang chạy (xem mục 8).

---

## 1. Tổng quan phân loại camera

Đây là camera **ANPR chuyên dụng cho giao thông**, không phải camera đa dụng (WizSense) và **không hỗ trợ nhận diện khuôn mặt** ở cấp phần cứng/thuật toán (xem so sánh dòng `-FR` nếu cần face recognition).

Camera thuộc nhóm tính năng: **Intelligent Traffic APIs** (mục 10 trong tài liệu gốc), gồm:

| Nhóm | Mục tài liệu |
|---|---|
| Sự kiện giao thông thời gian thực | 10.1 |
| Thống kê lưu lượng | 10.2 |
| Bản ghi (blocklist/allowlist) | 10.3 |
| Vận hành chụp ảnh & cấu hình giới hạn tốc độ | 10.4 |
| Bãi đỗ xe (nếu tích hợp) | 10.5 |
| Phân phối dữ liệu phương tiện | 10.6 |
| Quản lý nhóm phương tiện | 10.7 |

---

## 2. Xác thực (Authentication)

Dahua CGI dùng **HTTP Digest Authentication** trực tiếp trên từng request — không cần login session riêng cho các API cơ bản.

```
Digest Auth: username = admin (hoặc tài khoản cấu hình), password = mật khẩu camera
```

---

## 3. Cơ chế nhận sự kiện thời gian thực (Event Subscription)

**Endpoint:**
```
GET /cgi-bin/eventManager.cgi?action=attach&codes=[<EventCode1>,<EventCode2>,...]&heartbeat=5
```

- Kết nối HTTP giữ mở (long-lived), server trả về `multipart/x-mixed-replace`.
- Mỗi block: `Events[0].EventBaseInfo.Code=...`, `Events[0].EventBaseInfo.Action=Start/Stop/Pulse`, kèm các field dữ liệu dạng `key=value`.
- Ảnh (nếu có) nằm trong phần **binary** của cùng block, không phải trong text `data=`.

**Kiểm tra event code thực tế camera hỗ trợ:**
```
GET /cgi-bin/eventManager.cgi?action=getCaps
```

---

## 4. Danh mục đầy đủ sự kiện Traffic (mục 10.1)

| # | Event Code | Mô tả | Trang tài liệu |
|---|---|---|---|
| 10.1.1 | `TrafficJunction` | Sự kiện tổng hợp tại ngã tư/chốt — **giàu metadata nhất**, chứa đầy đủ thông tin biển số, phương tiện, hành vi lái xe/hành khách | 800 |
| 10.1.2 | `TrafficRetrograde` | Xe đi ngược chiều | 802 |
| 10.1.3 | `TrafficJam` | Kẹt xe (theo %, theo mét) | 803 |
| 10.1.4 | `TrafficUnderSpeed` | Xe chạy dưới tốc độ tối thiểu | 804 |
| 10.1.5 | `TrafficOverSpeed` | Xe vượt tốc độ giới hạn | 805 |
| 10.1.6 | `TrafficPedestrain` | Người đi bộ vi phạm làn/vạch | 806 |
| 10.1.7 | `TrafficParking` | Đỗ xe sai quy định | 807 |
| 10.1.8 | `TrafficCarMeasurement` (Traffic ANPR Measurement) | **Sự kiện ANPR thuần** — đo & nhận diện biển số + kích thước xe | 808 |
| 10.1.9 | Non Motor Hold Umbrella | Xe máy che ô khi lái | 815 |
| 10.1.10 | Non Motor In Motor Route | Xe không động cơ đi vào làn xe cơ giới | 816 |
| 10.1.11 | Non Motor Overload | Xe máy chở quá tải | 818 |
| 10.1.12 | Non Motor Without Safehat | Không đội mũ bảo hiểm | 819 |
| 10.1.13 | Traffic Over Line | Lấn vạch/lấn làn | 820 |

> Lưu ý: các sự kiện Non-Motor (10.1.9–10.1.12) và vi phạm hành vi (seatbelt, gọi điện...) phụ thuộc cấu hình AI-model được nạp trên camera — cần xác nhận qua `getCaps`.

---

## 5. Metadata chi tiết — trường dữ liệu quan trọng nhất

### 5.1 Biển số (Object / PlateInfo)
```
PlateNumber          — số biển số đã OCR
PlateType            — loại biển (thường/nền vàng/xanh...)
PlateColor           — Blue/Yellow/White/Black/Green/YellowBottomBlackText...
BoundingBox           — toạ độ khung biển số
Country               — quốc gia biển số
FrontPlateNumber / FrontPlateColor   — biển số phía đầu xe (nếu bắt được)
BackPlateNumber  / BackPlateColor    — biển số phía đuôi xe (nếu bắt được)
```

### 5.2 Phương tiện (Vehicle)
```
Category              — loại xe: Car, Bus, Truck...
VehicleColor / VehicleColorRGB
Text / SubText / SubBrand / BrandYear  — hãng xe, dòng xe, năm sản xuất (nhận diện logo)
Speed (km/h), Lane, PhysicalLane, Direction (8 hướng + custom)
BoundingBox           — khung toàn xe
VehicleDirection      — "Head" (đầu xe) / "Tail" (đuôi xe) / "VehBodySide" (hông xe) / "Unknow"
TriggerOccur          — 0 = enter (vào), 1 = leave (ra) → dùng cho bài toán cổng/vào-ra
JunctionDirection     — "Obverse" (cùng chiều) / "Reverse" (ngược chiều camera)
```

### 5.3 Hành vi lái xe/hành khách (CommInfo.Seat[] — chỉ trong TrafficJunction và event dùng chung cấu trúc)
```
Type          — Main (tài xế) / Slave (hành khách)
Status[]      — "Calling" (đang gọi điện) / "Smoking" (đang hút thuốc)
SafeBelt      — WithSafeBelt / WithoutSafeBelt (không thắt dây an toàn)
SunShade      — WithSunShade / ...
ShadePos[]    — toạ độ khung che nắng
```

### 5.4 Vi phạm / đo lường
```
RedLightUTC             — thời điểm đèn đỏ bật (tính vượt đèn đỏ)
SpeedLimit[min,max]     — ngưỡng tốc độ cấu hình
OverSpeedingPercentage / UnderSpeedingPercentage
JamLength (%) / JamRealLength (mét)
```

### 5.5 Ảnh đính kèm (binary trong multipart — KHÔNG nằm trong JSON text)
```
Object.Image        — ảnh cắt riêng biển số
OriginalVehicle      — ảnh cắt riêng toàn xe
SceneImage           — ảnh toàn cảnh hiện trường
```
> Muốn lưu ảnh: phải parse phần `Content-Length` nhị phân theo `Offset`/`Length` khai báo kèm theo, tách riêng khỏi phần text `data=`.

### 5.6 Thời gian & định danh
```
PTS, UTC, UTCMS                          — timestamp chính xác đến millisecond
RecNo, EventID
GroupID / CountInGroup / IndexInGroup    — gộp nhiều event cùng 1 lượt xe qua
```

---

## 6. API thống kê & truy vấn lại dữ liệu (offline)

| Mục | Chức năng |
|---|---|
| 10.2.1 `TrafficFlowStat` | Sự kiện thống kê lưu lượng theo thời gian thực |
| 10.2.2 Find Traffic Flow History | Tra cứu lịch sử lưu lượng |
| 10.2.3–10.2.5 | Bắt đầu/lấy/kết thúc phiên tìm kiếm thống kê |
| 10.3.1–10.3.7 | Thêm/sửa/xoá/tra cứu **Blocklist/Allowlist** biển số (danh sách đen/trắng ngay trên camera) |
| 10.3.8 Export Traffic Flow | Xuất dữ liệu lưu lượng |
| 10.3.9 Export Traffic Snap Event Info | Xuất dữ liệu sự kiện chụp ảnh |
| **4.10.9** Find Media Files with TrafficCar info | Tra cứu lại các lượt chụp biển số đã lưu trên thẻ nhớ/NVR, lọc theo `PlateNumber`, `Speed`, `VehicleColor`, khoảng thời gian |

---

## 7. API vận hành & cấu hình chụp ảnh (mục 10.4)

| Mục | Chức năng |
|---|---|
| 10.4.1 Open Strobe / 10.4.2 Close Strobe | Bật/tắt đèn chớp hỗ trợ chụp biển số ban đêm |
| 10.4.3 Open/Close Unlicensed Vehicle Detection | Bật/tắt phát hiện xe không biển số |
| 10.4.4 Manual Snap | Kích hoạt chụp ảnh thủ công qua API |
| 10.4.5 / 10.4.6 Get/Set Speed Limit | Đọc/ghi ngưỡng tốc độ giới hạn |
| 10.4.7 Set Enable Under Speed or Not | Bật/tắt phát hiện dưới tốc độ tối thiểu |
| 10.4.8 [Config] Traffic Strobe Setting | Cấu hình đèn chớp |
| 10.4.9 Set Rule Config | Cấu hình vùng phát hiện / vạch / làn (calibration) |
| 10.4.10 Traffic Network Snap | Chụp ảnh qua mạng |
| 10.4.11 Get Traffic Device Info | Lấy thông tin thiết bị (phiên bản, khả năng hỗ trợ) |

**Snapshot liên tục kèm metadata (endpoint riêng, không thuộc mục 10):**
```
GET /cgi-bin/snapManager.cgi?action=attachFileProc&channel=1&heartbeat=5
```

---

## 8. Xác nhận tính năng thực tế trên thiết bị (BẮT BUỘC trước khi code)

Vì tài liệu API là **chung cho toàn bộ dòng sản phẩm Dahua**, không phải mọi event/field đều chạy được trên một model cụ thể. Trước khi build hệ thống, cần:

1. Gọi `GET /cgi-bin/eventManager.cgi?action=getCaps` — lấy danh sách event code camera thực sự hỗ trợ.
2. Vào Web UI camera → **Setting → Event / Setting → Intelligent Traffic** — xem trực tiếp các tính năng đã bật/khả dụng theo license & firmware.
3. Test bằng cách subscribe từng `codes=[...]` một, quan sát log thực tế đổ về — vì một số field (VD `CommInfo.Seat`, Non-Motor detection) phụ thuộc gói AI-model được cấp phép trên thiết bị, không phải camera nào cũng chạy đủ.

---

## 9. Kiến trúc đề xuất khi build ứng dụng riêng

```
Camera ITC413 --(HTTP Digest Auth)--> Listener service (Python/Node)
                                              │
                                    parse multipart + JSON
                                              │
                                    lưu PlateNumber, Speed, VehicleDirection,
                                    TriggerOccur, ảnh, timestamp
                                              │
                                          PostgreSQL/MySQL
                                              │
                                        Dashboard / API nội bộ
```

Script khởi điểm (Python, HTTP Digest + parse multipart event `TrafficCarMeasurement`) đã có sẵn: `dahua_anpr_listener.py` (gửi ở phần trước trong hội thoại này) — dùng làm nền tảng, mở rộng thêm parser cho các event khác trong bảng mục 4 ở trên bằng cách thêm code vào `EVENT_CODES` và cập nhật hàm `extract_plate_info()`.

---

## 10. Giới hạn quan trọng cần nhớ khi thiết kế hệ thống

- **Không có nhận diện khuôn mặt** — camera này chỉ xử lý phương tiện/biển số.
- **1 ống kính, 1 hướng nhìn cố định** — `VehicleDirection` (Head/Tail) là phân loại ảnh chụp được, không phải camera nhìn được cả 2 phía cùng lúc. Muốn giám sát ra + vào tại 1 cổng, cần 2 camera đối xứng.
- Không có tài liệu xác nhận **relay/barrier I/O tích hợp sẵn** — nếu cần điều khiển trực tiếp barrier bãi đỗ xe, phải kiểm tra chân I/O vật lý trên datasheet mua hàng hoặc dùng relay board riêng nhận lệnh từ hệ thống qua `TriggerOccur`.
- Toàn bộ field vi phạm hành vi (seatbelt, gọi điện, hút thuốc, non-motor) phụ thuộc **license/AI-package** được cấp trên firmware — không mặc định có sẵn trên mọi đơn hàng.
