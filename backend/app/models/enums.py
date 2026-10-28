from enum import StrEnum


class DepartmentType(StrEnum):
    PM = "PM"
    SP = "SP"
    FH = "FH"
    WWTP = "WWTP"
    EAI = "EAI"
    UTIL = "UTIL"


class AssetLevel(StrEnum):
    PRODUCTION_LINE = "production_line"
    UNIT = "unit"
    ASSEMBLY = "assembly"
    SUB_ASSEMBLY = "sub_assembly"
    COMPONENT = "component"


ASSET_LEVEL_ORDER = [lvl for lvl in AssetLevel]


class Criticality(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class AssetStatus(StrEnum):
    IN_SERVICE = "in_service"
    STANDBY = "standby"
    UNDER_MAINTENANCE = "under_maintenance"
    OUT_OF_SERVICE = "out_of_service"
    DECOMMISSIONED = "decommissioned"


class WOType(StrEnum):
    PREVENTIVE = "preventive"
    PREDICTIVE = "predictive"
    CORRECTIVE = "corrective"
    EMERGENCY = "emergency"
    INSPECTION = "inspection"
    IMPROVEMENT = "improvement"
    SHUTDOWN = "shutdown"
    LUBRICATION = "lubrication"


class WOStatus(StrEnum):
    TRIAGE = "triage"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    PLANNED = "planned"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    AWAITING_REVIEW = "awaiting_review"  # inspection / testing / supervisor review
    COMPLETED = "completed"
    CLOSED = "closed"  # technical closure
    CANCELLED = "cancelled"


OPEN_WO_STATUSES = [
    WOStatus.TRIAGE,
    WOStatus.AWAITING_APPROVAL,
    WOStatus.APPROVED,
    WOStatus.PLANNED,
    WOStatus.SCHEDULED,
    WOStatus.IN_PROGRESS,
    WOStatus.ON_HOLD,
    WOStatus.AWAITING_REVIEW,
]
DONE_WO_STATUSES = [WOStatus.COMPLETED, WOStatus.CLOSED]


class Priority(StrEnum):
    P1_EMERGENCY = "P1"
    P2_HIGH = "P2"
    P3_MEDIUM = "P3"
    P4_LOW = "P4"


class RequestStatus(StrEnum):
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class FailureCodeKind(StrEnum):
    SYMPTOM = "symptom"  # what is observed (noise, leak, trip): chosen when a request is raised
    PROBLEM = "problem"  # the failure mode (bearing failure, seal failure): confirmed by the technician
    CAUSE = "cause"
    REMEDY = "remedy"


class PMTrigger(StrEnum):
    CALENDAR = "calendar"
    METER = "meter"
    CONDITION = "condition"


class FrequencyUnit(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class ScheduleBasis(StrEnum):
    FIXED = "fixed"  # next due from the original schedule anchor
    FLOATING = "floating"  # next due from the last completion


class OccurrenceStatus(StrEnum):
    SCHEDULED = "scheduled"
    GENERATED = "generated"
    COMPLETED = "completed"
    DEFERRAL_REQUESTED = "deferral_requested"
    DEFERRED = "deferred"
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLED = "cancelled"


class ChecklistKind(StrEnum):
    CHECK = "check"
    READING = "reading"


class TxnType(StrEnum):
    RECEIPT = "receipt"
    ISSUE = "issue"
    RETURN = "return"
    ADJUSTMENT = "adjustment"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class POStatus(StrEnum):
    DRAFT = "draft"
    REQUESTED = "requested"  # purchase requisition
    ORDERED = "ordered"
    PARTIAL = "partial"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class Technique(StrEnum):
    VIBRATION = "vibration"
    TEMPERATURE = "temperature"
    MOTOR_CURRENT = "motor_current"
    POWER = "power"
    OIL_ANALYSIS = "oil_analysis"
    THERMOGRAPHY = "thermography"
    ULTRASOUND = "ultrasound"
    ALIGNMENT = "alignment"
    BALANCING = "balancing"
    PRESSURE = "pressure"
    FLOW = "flow"
    OTHER = "other"


class ConditionStatus(StrEnum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    WO_CREATED = "wo_created"
    RESOLVED = "resolved"


class LubeTaskStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    MISSED = "missed"


class ShiftKind(StrEnum):
    DAY = "day"
    EVENING = "evening"
    NIGHT = "night"
    GENERAL = "general"


class RosterKind(StrEnum):
    WORK = "work"
    OVERTIME = "overtime"
    CALLOUT = "callout"
    LEAVE = "leave"
    ABSENCE = "absence"


class HandoverStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"


class ShutdownStatus(StrEnum):
    PLANNING = "planning"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PackageStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DELAYED = "delayed"
    COMPLETED = "completed"


class ReadinessStatus(StrEnum):
    NOT_READY = "not_ready"
    PARTIAL = "partial"
    READY = "ready"
    NOT_REQUIRED = "not_required"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DISABLED = "disabled"
