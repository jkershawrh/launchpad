from enum import Enum


class TenantType(str, Enum):
    REDHAT_INTERNAL = "redhat_internal"
    INTEL_INTERNAL = "intel_internal"
    PARTNER = "partner"
    CLIENT = "client"
    DEMO = "demo"


class TenantStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class CatalogCategory(str, Enum):
    QUICK_START = "quick_start"
    GUIDED_BUILD = "guided_build"
    OPEN_SANDBOX = "open_sandbox"


class CatalogStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class LabRequestStatus(str, Enum):
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PROVISIONING = "provisioning"
    READY = "ready"
    FAILED = "failed"


class SessionStatus(str, Enum):
    REQUESTED = "requested"
    PROVISIONING = "provisioning"
    VALIDATING = "validating"
    READY = "ready"
    ACTIVE = "active"
    EXPIRED = "expired"
    RESETTING = "resetting"
    RECLAIMED = "reclaimed"
    FAILED = "failed"
    REJECTED = "rejected"
    VALIDATION_FAILED = "validation_failed"
    CLEANUP_FAILED = "cleanup_failed"


class WorkshopStatus(str, Enum):
    DRAFT = "draft"
    CAPACITY_CHECKING = "capacity_checking"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    QUEUED = "queued"
    PROVISIONING = "provisioning"
    PARTIALLY_READY = "partially_ready"
    READY = "ready"
    ACTIVE = "active"
    PREFLIGHT_FAILED = "preflight_failed"
    FAILED = "failed"
    RECLAIMING = "reclaiming"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"


class WorkshopSeatStatus(str, Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    VALIDATING = "validating"
    READY = "ready"
    ACTIVE = "active"
    FAILED = "failed"
    RECLAIMING = "reclaiming"
    RECLAIMED = "reclaimed"


class Persistence(str, Enum):
    EPHEMERAL = "ephemeral"
    PERSISTENT = "persistent"


class GaudiMode(str, Enum):
    NONE = "none"
    ENDPOINT = "endpoint"
    DIRECT = "direct"


class ValidationResultStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIPPED = "skipped"


class BrandingTheme(str, Enum):
    DEFAULT = "default"
    COCKPIT_DARK = "cockpit_dark"
    PARTNER_LIGHT = "partner_light"


class StackLevel(str, Enum):
    MINIMAL = "minimal"
    AI_DEV = "ai_dev"
    FULL_REDHAT_AI = "full_redhat_ai"


class AAPLevel(str, Enum):
    NONE = "none"
    PLAYBOOK_LIBRARY = "playbook_library"
    FULL_AAP = "full_aap"


class AccessMethod(str, Enum):
    WEB_CONSOLE = "web_console"
    SSH = "ssh"
    VSCODE = "vscode"
    JUPYTER = "jupyter"
    API = "api"
