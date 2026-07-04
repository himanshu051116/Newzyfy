from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from newsintel.domain.access import AccessRole, AccessStatus


class IdentityClaims(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    provider_user_id: str = Field(min_length=1, max_length=255)
    verified_email: str | None = Field(default=None, max_length=320)
    email_verified: bool = False
    display_name: str | None = Field(default=None, max_length=300)
    avatar_url: str | None = None


class PlatformUserView(BaseModel):
    id: UUID
    auth_provider: str
    auth_provider_user_id: str
    verified_email: str | None
    display_name: str | None
    avatar_url: str | None
    access_status: AccessStatus
    role: AccessRole
    requested_at: datetime
    approved_at: datetime | None
    rejected_at: datetime | None
    rejection_reason: str | None
    suspended_at: datetime | None
    suspension_reason: str | None
    revoked_at: datetime | None
    revocation_reason: str | None
    access_expires_at: datetime | None
    last_login_at: datetime | None
    last_activity_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CurrentUser(PlatformUserView):
    permissions: frozenset[str]
    credential_source: str


class AccessRequestView(BaseModel):
    id: UUID
    user_id: UUID
    status: str
    purpose: str | None
    requested_at: datetime
    closed_at: datetime | None
    decision_reason: str | None
    created_at: datetime
    updated_at: datetime
    user: PlatformUserView | None = None


class AccessAuditLogView(BaseModel):
    id: UUID
    action: str
    actor_user_id: UUID | None
    affected_user_id: UUID
    previous_status: str | None
    new_status: str | None
    previous_role: str | None
    new_role: str | None
    reason: str | None
    created_at: datetime


class AccessDecisionCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    role: AccessRole = AccessRole.VIEWER
    reason: str | None = Field(default=None, max_length=2_000)
    user_visible_reason: str | None = Field(default=None, max_length=2_000)
    access_expires_at: datetime | None = None


class AccessReasonCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str | None = Field(default=None, max_length=2_000)
    user_visible_reason: str | None = Field(default=None, max_length=2_000)


class RoleChangeCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    role: AccessRole
    reason: str | None = Field(default=None, max_length=2_000)


class ExpiryChangeCommand(BaseModel):
    access_expires_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=2_000)
