from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from newsintel.api.dependencies import AccessAdminAuth, AuthServiceDependency
from newsintel.application.auth.dto import (
    AccessAuditLogView,
    AccessDecisionCommand,
    AccessReasonCommand,
    AccessRequestView,
    ExpiryChangeCommand,
    PlatformUserView,
    RoleChangeCommand,
)
from newsintel.application.auth.service import AccessManagementError

router = APIRouter(prefix="/admin/access", tags=["access-admin"])


@router.get("/requests", response_model=list[AccessRequestView])
async def pending_requests(
    _auth: AccessAdminAuth,
    service: AuthServiceDependency,
) -> list[AccessRequestView]:
    return await service.list_pending_requests()


@router.get("/users", response_model=list[PlatformUserView])
async def list_users(
    _auth: AccessAdminAuth,
    service: AuthServiceDependency,
    q: str | None = Query(default=None, max_length=200),
) -> list[PlatformUserView]:
    return await service.list_users(query=q)


@router.get("/users/{user_id}/audit", response_model=list[AccessAuditLogView])
async def audit_timeline(
    user_id: UUID,
    _auth: AccessAdminAuth,
    service: AuthServiceDependency,
) -> list[AccessAuditLogView]:
    return await service.audit_timeline(user_id)


@router.post("/users/{user_id}/approve", response_model=PlatformUserView)
async def approve_user(
    user_id: UUID,
    command: AccessDecisionCommand,
    actor: AccessAdminAuth,
    service: AuthServiceDependency,
) -> PlatformUserView:
    try:
        return await service.approve_user(
            user_id=user_id,
            actor=actor,
            role=command.role,
            reason=command.reason,
            access_expires_at=command.access_expires_at,
        )
    except AccessManagementError as exc:
        raise _bad_request(exc) from exc


@router.post("/users/{user_id}/reject", response_model=PlatformUserView)
async def reject_user(
    user_id: UUID,
    command: AccessReasonCommand,
    actor: AccessAdminAuth,
    service: AuthServiceDependency,
) -> PlatformUserView:
    try:
        return await service.reject_user(
            user_id=user_id,
            actor=actor,
            reason=command.reason,
            user_visible_reason=command.user_visible_reason,
        )
    except AccessManagementError as exc:
        raise _bad_request(exc) from exc


@router.post("/users/{user_id}/suspend", response_model=PlatformUserView)
async def suspend_user(
    user_id: UUID,
    command: AccessReasonCommand,
    actor: AccessAdminAuth,
    service: AuthServiceDependency,
) -> PlatformUserView:
    try:
        return await service.suspend_user(
            user_id=user_id,
            actor=actor,
            reason=command.reason,
            user_visible_reason=command.user_visible_reason,
        )
    except AccessManagementError as exc:
        raise _bad_request(exc) from exc


@router.post("/users/{user_id}/restore", response_model=PlatformUserView)
async def restore_user(
    user_id: UUID,
    command: AccessReasonCommand,
    actor: AccessAdminAuth,
    service: AuthServiceDependency,
) -> PlatformUserView:
    try:
        return await service.restore_user(
            user_id=user_id,
            actor=actor,
            reason=command.reason,
        )
    except AccessManagementError as exc:
        raise _bad_request(exc) from exc


@router.post("/users/{user_id}/revoke", response_model=PlatformUserView)
async def revoke_user(
    user_id: UUID,
    command: AccessReasonCommand,
    actor: AccessAdminAuth,
    service: AuthServiceDependency,
) -> PlatformUserView:
    try:
        return await service.revoke_user(
            user_id=user_id,
            actor=actor,
            reason=command.reason,
            user_visible_reason=command.user_visible_reason,
        )
    except AccessManagementError as exc:
        raise _bad_request(exc) from exc


@router.post("/users/{user_id}/role", response_model=PlatformUserView)
async def change_role(
    user_id: UUID,
    command: RoleChangeCommand,
    actor: AccessAdminAuth,
    service: AuthServiceDependency,
) -> PlatformUserView:
    try:
        return await service.change_role(
            user_id=user_id,
            actor=actor,
            role=command.role,
            reason=command.reason,
        )
    except AccessManagementError as exc:
        raise _bad_request(exc) from exc


@router.post("/users/{user_id}/expiry", response_model=PlatformUserView)
async def extend_access(
    user_id: UUID,
    command: ExpiryChangeCommand,
    actor: AccessAdminAuth,
    service: AuthServiceDependency,
) -> PlatformUserView:
    try:
        return await service.extend_access(
            user_id=user_id,
            actor=actor,
            access_expires_at=command.access_expires_at,
            reason=command.reason,
        )
    except AccessManagementError as exc:
        raise _bad_request(exc) from exc


def _bad_request(exc: AccessManagementError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "access_management_error", "message": str(exc)},
    )
