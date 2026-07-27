from __future__ import annotations

from enum import StrEnum


class DirectionRole(StrEnum):
    ENTRY = "entry"
    EXIT = "exit"
    BIDIRECTIONAL = "bidirectional"


class SessionStatus(StrEnum):
    INSIDE = "inside"
    COMPLETED = "completed"
    ORPHAN_EXIT = "orphan_exit"


class ViolationType(StrEnum):
    SEATBELT = "seatbelt"
    CALLING = "calling"
    SMOKING = "smoking"
    OVERSPEED = "overspeed"
    UNDERSPEED = "underspeed"
    RETROGRADE = "retrograde"
    PARKING = "parking"
    OVERLINE = "overline"
    PEDESTRIAN = "pedestrian"
    JAM = "jam"
    UNLICENSED = "unlicensed"
    NONMOTOR_UMBRELLA = "nonmotor_umbrella"
    NONMOTOR_LANE = "nonmotor_lane"
    NONMOTOR_OVERLOAD = "nonmotor_overload"
    NONMOTOR_SAFEHAT = "nonmotor_safehat"
    OTHER = "other"


class EventCode(StrEnum):
    TRAFFIC_JUNCTION = "TrafficJunction"
    TRAFFIC_CAR_MEASUREMENT = "TrafficCarMeasurement"
    TRAFFIC_OVERSPEED = "TrafficOverSpeed"
    TRAFFIC_UNDERSPEED = "TrafficUnderSpeed"
    TRAFFIC_RETROGRADE = "TrafficRetrograde"
    TRAFFIC_PARKING = "TrafficParking"
    TRAFFIC_OVERLINE = "TrafficOverLine"
    TRAFFIC_PEDESTRIAN = "TrafficPedestrain"
    TRAFFIC_FLOW_STAT = "TrafficFlowStat"
    TRAFFIC_JAM = "TrafficJam"
    NONMOTOR_HOLD_UMBRELLA = "TrafficNonMotorHoldUmbrella"
    NONMOTOR_IN_MOTOR_ROUTE = "TrafficNonMotorInMotorRoute"
    NONMOTOR_OVERLOAD = "TrafficNonMotorOverload"
    NONMOTOR_WITHOUT_SAFEHAT = "TrafficNonMotorWithoutSafehat"


# P0 codes always preferred when caps allow
P0_EVENT_CODES = [
    EventCode.TRAFFIC_JUNCTION,
    EventCode.TRAFFIC_CAR_MEASUREMENT,
]

P1_EVENT_CODES = [
    EventCode.TRAFFIC_OVERSPEED,
    EventCode.TRAFFIC_UNDERSPEED,
    EventCode.TRAFFIC_RETROGRADE,
    EventCode.TRAFFIC_PARKING,
    EventCode.TRAFFIC_OVERLINE,
    EventCode.TRAFFIC_PEDESTRIAN,
    EventCode.TRAFFIC_JAM,
    EventCode.NONMOTOR_HOLD_UMBRELLA,
    EventCode.NONMOTOR_IN_MOTOR_ROUTE,
    EventCode.NONMOTOR_OVERLOAD,
    EventCode.NONMOTOR_WITHOUT_SAFEHAT,
]

P2_EVENT_CODES = [
    EventCode.TRAFFIC_FLOW_STAT,
]

ALL_KNOWN_EVENT_CODES = P0_EVENT_CODES + P1_EVENT_CODES + P2_EVENT_CODES

EVENT_TO_VIOLATION: dict[str, ViolationType] = {
    EventCode.TRAFFIC_OVERSPEED: ViolationType.OVERSPEED,
    EventCode.TRAFFIC_UNDERSPEED: ViolationType.UNDERSPEED,
    EventCode.TRAFFIC_RETROGRADE: ViolationType.RETROGRADE,
    EventCode.TRAFFIC_PARKING: ViolationType.PARKING,
    EventCode.TRAFFIC_OVERLINE: ViolationType.OVERLINE,
    EventCode.TRAFFIC_PEDESTRIAN: ViolationType.PEDESTRIAN,
    EventCode.TRAFFIC_JAM: ViolationType.JAM,
    EventCode.NONMOTOR_HOLD_UMBRELLA: ViolationType.NONMOTOR_UMBRELLA,
    EventCode.NONMOTOR_IN_MOTOR_ROUTE: ViolationType.NONMOTOR_LANE,
    EventCode.NONMOTOR_OVERLOAD: ViolationType.NONMOTOR_OVERLOAD,
    EventCode.NONMOTOR_WITHOUT_SAFEHAT: ViolationType.NONMOTOR_SAFEHAT,
}
