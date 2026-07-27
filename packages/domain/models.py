from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    gates: Mapped[list[Gate]] = relationship(back_populates="site", cascade="all, delete-orphan")


class Gate(Base):
    __tablename__ = "gates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    site: Mapped[Site] = relationship(back_populates="gates")
    lanes: Mapped[list[Lane]] = relationship(back_populates="gate", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("site_id", "name", name="uq_gate_site_name"),)


class Lane(Base):
    __tablename__ = "lanes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gates.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    lane_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    gate: Mapped[Gate] = relationship(back_populates="lanes")
    cameras: Mapped[list[Camera]] = relationship(back_populates="lane", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("gate_id", "name", name="uq_lane_gate_name"),)


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lane_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lanes.id", ondelete="SET NULL"), nullable=True
    )
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=80)
    use_https: Mapped[bool] = mapped_column(Boolean, default=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password: Mapped[str] = mapped_column(String(256), nullable=False)
    direction_role: Mapped[str] = mapped_column(String(32), default="entry")  # entry|exit|bidirectional
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    subscribe_codes: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    listener_status: Mapped[str] = mapped_column(String(32), default="unknown")  # connected|disconnected|error
    listener_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    map_icon: Mapped[str] = mapped_column(String(32), default="camera")  # camera|gate|radar|dome|ptz
    map_note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lane: Mapped[Lane | None] = relationship(back_populates="cameras")
    caps: Mapped[CameraCaps | None] = relationship(
        back_populates="camera", uselist=False, cascade="all, delete-orphan"
    )


class CameraCaps(Base):
    __tablename__ = "camera_caps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    raw_caps: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    supported_codes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    probed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    camera: Mapped[Camera] = relationship(back_populates="caps")


class RawEvent(Base):
    __tablename__ = "raw_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    event_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    image_paths: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_raw_events_camera_utc", "camera_id", "event_utc"),)


class VehicleDetection(Base):
    __tablename__ = "vehicle_detections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("raw_events.id", ondelete="SET NULL"), nullable=True
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    gate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("gates.id", ondelete="SET NULL"), nullable=True)
    lane_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lanes.id", ondelete="SET NULL"), nullable=True)
    event_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    plate_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plate_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    plate_color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plate_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vehicle_brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vehicle_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vehicle_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vehicle_class: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)  # car|motorcycle|other|unknown
    vehicle_color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    lane_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vehicle_direction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    junction_direction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger_occur: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passage_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)  # entry|exit
    group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    seatbelt_main: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seatbelt_sub: Mapped[str | None] = mapped_column(String(64), nullable=True)
    calling: Mapped[bool] = mapped_column(Boolean, default=False)
    smoking: Mapped[bool] = mapped_column(Boolean, default=False)
    image_paths: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_detections_site_utc", "site_id", "event_utc"),
        Index("ix_detections_plate_utc", "plate_number", "event_utc"),
    )


class VehicleSession(Base):
    __tablename__ = "vehicle_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    plate_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inside")
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_detection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicle_detections.id", ondelete="SET NULL"), nullable=True
    )
    exit_detection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicle_detections.id", ondelete="SET NULL"), nullable=True
    )
    entry_gate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("gates.id", ondelete="SET NULL"), nullable=True
    )
    exit_gate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("gates.id", ondelete="SET NULL"), nullable=True
    )
    vehicle_brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vehicle_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vehicle_color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_speed: Mapped[float | None] = mapped_column(Float, nullable=True)  # km/h lúc vào
    exit_speed: Mapped[float | None] = mapped_column(Float, nullable=True)  # km/h lúc ra
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_sessions_site_status", "site_id", "status"),
        Index("ix_sessions_plate_status", "plate_number", "status"),
    )


class ViolationEvent(Base):
    __tablename__ = "violation_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    detection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicle_detections.id", ondelete="SET NULL"), nullable=True
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    violation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plate_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    image_paths: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OverspeedSighting(Base):
    """Theo dõi tốc độ vượt cao nhất của một biển số trong một lần xuất hiện (tầm nhìn camera)."""

    __tablename__ = "overspeed_sightings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    plate_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    limit_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_speed: Mapped[float] = mapped_column(Float, nullable=False)
    first_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_event_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    peak_event_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    peak_detection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicle_detections.id", ondelete="SET NULL"), nullable=True
    )
    violation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("violation_events.id", ondelete="SET NULL"), nullable=True
    )
    image_paths: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_overspeed_sightings_cam_plate_active", "camera_id", "plate_number", "active"),
    )


class TrafficFlowSample(Base):
    __tablename__ = "traffic_flow_samples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    event_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lane_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vehicles_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queue_len: Mapped[int | None] = mapped_column(Integer, nullable=True)
    direction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_flow_camera_utc", "camera_id", "event_utc"),)


class JamEvent(Base):
    __tablename__ = "jam_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    event_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lane_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jam_length_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    jam_real_length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VehicleRegistry(Base):
    """Local mirror of camera Vehicle Manager (10.7) / site vehicle groups."""

    __tablename__ = "vehicle_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    group_name: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    plate_number: Mapped[str] = mapped_column(String(64), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    camera_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synced_to_camera: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("site_id", "group_name", "plate_number", name="uq_vehicle_registry"),
    )


class ParkingSpaceSnapshot(Base):
    __tablename__ = "parking_space_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CameraSpeedPolicy(Base):
    """Ngưỡng tốc độ theo camera — dùng để cảnh báo vượt/dưới tốc phía server."""

    __tablename__ = "camera_speed_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    min_speed: Mapped[int] = mapped_column(Integer, default=0)
    max_speed: Mapped[int] = mapped_column(Integer, default=80)
    alert_overspeed: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_underspeed: Mapped[bool] = mapped_column(Boolean, default=False)
    push_to_camera: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlateListEntry(Base):
    __tablename__ = "plate_lists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    list_type: Mapped[str] = mapped_column(String(32), nullable=False)  # allow|block
    plate_number: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    begin_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_to_camera: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("site_id", "list_type", "plate_number", name="uq_plate_list"),
    )


class CameraOverlay(Base):
    """Vạch / vùng quan sát vẽ trên ảnh camera (hệ toạ độ Dahua 0–8192)."""

    __tablename__ = "camera_overlays"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # { "shapes": [ { "id", "type": "lane_line"|"stop_line"|"region", "label", "points": [[x,y],...] } ] }
    shapes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlateWatch(Base):
    """Biển số cần truy vết — khi camera nhận diện sẽ tạo WatchAlert."""

    __tablename__ = "plate_watches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), nullable=True
    )  # None = theo dõi mọi site
    plate_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)  # lý do / tên đối tượng
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal")  # low|normal|high|critical
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_dashboard: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("site_id", "plate_number", name="uq_plate_watch_site_plate"),
        Index("ix_plate_watches_active_plate", "active", "plate_number"),
    )


class WatchAlert(Base):
    __tablename__ = "watch_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plate_watches.id", ondelete="CASCADE"), nullable=False
    )
    detection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicle_detections.id", ondelete="SET NULL"), nullable=True
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    plate_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    event_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    image_paths: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_watch_alerts_read_created", "read", "created_at"),)
