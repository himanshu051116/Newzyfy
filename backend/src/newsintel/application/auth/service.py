from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.auth.dto import (
    AccessAuditLogView,
    AccessRequestView,
    CurrentUser,
    IdentityClaims,
    PlatformUserView,
)
from newsintel.contracts.events import IntegrationEvent
from newsintel.core.ids import uuid7
from newsintel.domain.access import (
    AccessRole,
    AccessStatus,
    permissions_for_role,
)
from newsintel.infrastructure.db.models import (
    AccessAuditLogModel,
    AccessRequestModel,
    OutboxEventModel,
    PlatformUserModel,
)


class AccessDeniedError(PermissionError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AccessManagementError(ValueError):
    pass


class PlatformAuthService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def authenticate_identity(
        self,
        identity: IdentityClaims,
        *,
        credential_source: str,
        request_metadata: dict[str, object] | None = None,
        bootstrap_owner_provider: str | None = None,
        bootstrap_owner_user_id: str | None = None,
        bootstrap_owner_email: str | None = None,
    ) -> CurrentUser:
        if not identity.email_verified:
            raise AccessDeniedError(
                "email_unverified",
                "verified identity email is required",
            )
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            user = await session.scalar(
                select(PlatformUserModel).where(
                    PlatformUserModel.auth_provider == identity.provider,
                    PlatformUserModel.auth_provider_user_id == identity.provider_user_id,
                )
            )
            created = user is None
            should_bootstrap_owner = _matches_owner_bootstrap(
                identity,
                bootstrap_owner_provider=bootstrap_owner_provider,
                bootstrap_owner_user_id=bootstrap_owner_user_id,
                bootstrap_owner_email=bootstrap_owner_email,
            )
            if user is None:
                user = PlatformUserModel(
                    id=uuid7(),
                    auth_provider=identity.provider,
                    auth_provider_user_id=identity.provider_user_id,
                    verified_email=identity.verified_email,
                    display_name=identity.display_name,
                    avatar_url=identity.avatar_url,
                    access_status=(
                        AccessStatus.APPROVED.value
                        if should_bootstrap_owner
                        else AccessStatus.PENDING.value
                    ),
                    role=(
                        AccessRole.OWNER.value
                        if should_bootstrap_owner
                        else AccessRole.VIEWER.value
                    ),
                    requested_at=now,
                    approved_at=now if should_bootstrap_owner else None,
                    last_login_at=now,
                    last_activity_at=now,
                    metadata_={},
                    created_at=now,
                    updated_at=now,
                )
                session.add(user)
                await session.flush()
                if not should_bootstrap_owner:
                    await self._ensure_open_request(session, user=user, now=now)
                await self._audit(
                    session,
                    action=(
                        "owner_bootstrapped"
                        if should_bootstrap_owner
                        else "access_requested"
                    ),
                    actor_user_id=user.id if should_bootstrap_owner else None,
                    affected_user=user,
                    previous_status=None,
                    new_status=user.access_status,
                    previous_role=None,
                    new_role=user.role,
                    reason=None,
                    request_metadata=request_metadata,
                    created_at=now,
                )
            else:
                user.verified_email = identity.verified_email
                user.display_name = identity.display_name
                user.avatar_url = identity.avatar_url
                user.last_login_at = now
                user.last_activity_at = now
                user.updated_at = now
                if user.access_status == AccessStatus.PENDING.value:
                    await self._ensure_open_request(session, user=user, now=now)
            if created and not should_bootstrap_owner:
                await self._add_outbox(
                    session,
                    IntegrationEvent(
                        event_type="access.request_created",
                        aggregate_type="platform_user",
                        aggregate_id=user.id,
                        payload={
                            "platform_user_id": str(user.id),
                            "auth_provider": user.auth_provider,
                            "verified_email": user.verified_email,
                            "display_name": user.display_name,
                        },
                        producer="access-control",
                        idempotency_key=f"access.request_created:{user.id}",
                    ),
                )
            view = _current_user_from_model(user, credential_source=credential_source)
        return view

    async def get_user(
        self,
        user_id: UUID,
        *,
        credential_source: str = "database",
    ) -> CurrentUser | None:
        async with self._session_factory() as session:
            user = await session.get(PlatformUserModel, user_id)
            return (
                _current_user_from_model(user, credential_source=credential_source)
                if user
                else None
            )

    async def touch_activity(self, user_id: UUID) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            user = await session.get(PlatformUserModel, user_id)
            if user is not None:
                user.last_activity_at = now
                user.updated_at = now

    async def list_pending_requests(self) -> list[AccessRequestView]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(AccessRequestModel, PlatformUserModel)
                    .join(PlatformUserModel, PlatformUserModel.id == AccessRequestModel.user_id)
                    .where(AccessRequestModel.status == "open")
                    .order_by(AccessRequestModel.requested_at)
                )
            ).all()
            return [
                _request_view(request, user=user)
                for request, user in rows
            ]

    async def list_users(
        self,
        *,
        query: str | None = None,
        limit: int = 100,
    ) -> list[PlatformUserView]:
        async with self._session_factory() as session:
            statement = (
                select(PlatformUserModel)
                .order_by(PlatformUserModel.requested_at)
                .limit(limit)
            )
            if query:
                pattern = f"%{query.lower()}%"
                statement = statement.where(
                    or_(
                        func.lower(PlatformUserModel.verified_email).like(pattern),
                        func.lower(PlatformUserModel.display_name).like(pattern),
                    )
                )
            users = (await session.scalars(statement)).all()
            return [_user_view(user) for user in users]

    async def audit_timeline(self, user_id: UUID) -> list[AccessAuditLogView]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(AccessAuditLogModel)
                    .where(AccessAuditLogModel.affected_user_id == user_id)
                    .order_by(AccessAuditLogModel.created_at)
                )
            ).all()
            return [_audit_view(row) for row in rows]

    async def approve_user(
        self,
        *,
        user_id: UUID,
        actor: CurrentUser,
        role: AccessRole,
        reason: str | None,
        access_expires_at: datetime | None,
    ) -> PlatformUserView:
        if role is AccessRole.OWNER and actor.role is not AccessRole.OWNER:
            raise AccessManagementError("only an owner can grant owner access")
        return await self._transition(
            user_id=user_id,
            actor=actor,
            action="approved",
            new_status=AccessStatus.APPROVED,
            new_role=role,
            reason=reason,
            access_expires_at=access_expires_at,
        )

    async def reject_user(
        self,
        *,
        user_id: UUID,
        actor: CurrentUser,
        reason: str | None,
        user_visible_reason: str | None,
    ) -> PlatformUserView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            user = await self._load_user_for_update(session, user_id)
            previous_status = user.access_status
            previous_role = user.role
            user.access_status = AccessStatus.REJECTED.value
            user.rejected_at = now
            user.rejection_reason = user_visible_reason
            user.updated_at = now
            await self._close_open_requests(
                session,
                user_id=user.id,
                status="rejected",
                actor_id=actor.id,
                reason=user_visible_reason or reason,
                closed_at=now,
            )
            await self._audit(
                session,
                action="rejected",
                actor_user_id=actor.id,
                affected_user=user,
                previous_status=previous_status,
                new_status=user.access_status,
                previous_role=previous_role,
                new_role=user.role,
                reason=reason,
                request_metadata=None,
                created_at=now,
            )
            await self._decision_outbox(session, user=user, action="rejected")
            return _user_view(user)

    async def suspend_user(
        self,
        *,
        user_id: UUID,
        actor: CurrentUser,
        reason: str | None,
        user_visible_reason: str | None,
    ) -> PlatformUserView:
        return await self._transition(
            user_id=user_id,
            actor=actor,
            action="suspended",
            new_status=AccessStatus.SUSPENDED,
            new_role=None,
            reason=reason,
            user_visible_reason=user_visible_reason,
            access_expires_at=None,
        )

    async def restore_user(
        self,
        *,
        user_id: UUID,
        actor: CurrentUser,
        reason: str | None,
    ) -> PlatformUserView:
        return await self._transition(
            user_id=user_id,
            actor=actor,
            action="restored",
            new_status=AccessStatus.APPROVED,
            new_role=None,
            reason=reason,
            access_expires_at=None,
        )

    async def revoke_user(
        self,
        *,
        user_id: UUID,
        actor: CurrentUser,
        reason: str | None,
        user_visible_reason: str | None,
    ) -> PlatformUserView:
        return await self._transition(
            user_id=user_id,
            actor=actor,
            action="revoked",
            new_status=AccessStatus.REVOKED,
            new_role=None,
            reason=reason,
            user_visible_reason=user_visible_reason,
            access_expires_at=None,
        )

    async def change_role(
        self,
        *,
        user_id: UUID,
        actor: CurrentUser,
        role: AccessRole,
        reason: str | None,
    ) -> PlatformUserView:
        if role is AccessRole.OWNER and actor.role is not AccessRole.OWNER:
            raise AccessManagementError("only an owner can grant owner access")
        return await self._transition(
            user_id=user_id,
            actor=actor,
            action="role_changed",
            new_status=None,
            new_role=role,
            reason=reason,
            access_expires_at=None,
        )

    async def extend_access(
        self,
        *,
        user_id: UUID,
        actor: CurrentUser,
        access_expires_at: datetime | None,
        reason: str | None,
    ) -> PlatformUserView:
        return await self._transition(
            user_id=user_id,
            actor=actor,
            action="expiry_changed",
            new_status=None,
            new_role=None,
            reason=reason,
            access_expires_at=access_expires_at,
            update_expiry=True,
        )

    async def _transition(
        self,
        *,
        user_id: UUID,
        actor: CurrentUser,
        action: str,
        new_status: AccessStatus | None,
        new_role: AccessRole | None,
        reason: str | None,
        access_expires_at: datetime | None,
        user_visible_reason: str | None = None,
        update_expiry: bool = False,
    ) -> PlatformUserView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            user = await self._load_user_for_update(session, user_id)
            if (
                user.role == AccessRole.OWNER.value
                and actor.id != user.id
                and actor.role is not AccessRole.OWNER
            ):
                raise AccessManagementError("owner access can only be changed by an owner")
            previous_status = user.access_status
            previous_role = user.role
            if new_status is not None:
                user.access_status = new_status.value
            if new_role is not None:
                user.role = new_role.value
            if new_status is AccessStatus.APPROVED:
                user.approved_at = now
                user.approved_by_admin_id = actor.id
                await self._close_open_requests(
                    session,
                    user_id=user.id,
                    status="approved",
                    actor_id=actor.id,
                    reason=reason,
                    closed_at=now,
                )
            elif new_status is AccessStatus.SUSPENDED:
                user.suspended_at = now
                user.suspension_reason = user_visible_reason
            elif new_status is AccessStatus.REVOKED:
                user.revoked_at = now
                user.revocation_reason = user_visible_reason
            if access_expires_at is not None or update_expiry:
                user.access_expires_at = access_expires_at
            user.updated_at = now
            await self._audit(
                session,
                action=action,
                actor_user_id=actor.id,
                affected_user=user,
                previous_status=previous_status,
                new_status=user.access_status,
                previous_role=previous_role,
                new_role=user.role,
                reason=reason,
                request_metadata=None,
                created_at=now,
            )
            await self._decision_outbox(session, user=user, action=action)
            return _user_view(user)

    async def _load_user_for_update(
        self,
        session: AsyncSession,
        user_id: UUID,
    ) -> PlatformUserModel:
        user = await session.scalar(
            select(PlatformUserModel)
            .where(PlatformUserModel.id == user_id)
            .with_for_update()
        )
        if user is None:
            raise AccessManagementError(f"platform user not found: {user_id}")
        return user

    async def _ensure_open_request(
        self,
        session: AsyncSession,
        *,
        user: PlatformUserModel,
        now: datetime,
    ) -> None:
        existing = await session.scalar(
            select(AccessRequestModel).where(
                AccessRequestModel.user_id == user.id,
                AccessRequestModel.status == "open",
            )
        )
        if existing is not None:
            return
        session.add(
            AccessRequestModel(
                id=uuid7(),
                user_id=user.id,
                status="open",
                purpose=None,
                requested_at=now,
                created_at=now,
                updated_at=now,
            )
        )

    async def _close_open_requests(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        status: str,
        actor_id: UUID,
        reason: str | None,
        closed_at: datetime,
    ) -> None:
        requests = (
            await session.scalars(
                select(AccessRequestModel)
                .where(
                    AccessRequestModel.user_id == user_id,
                    AccessRequestModel.status == "open",
                )
                .with_for_update()
            )
        ).all()
        for request in requests:
            request.status = status
            request.closed_at = closed_at
            request.closed_by_admin_id = actor_id
            request.decision_reason = reason
            request.updated_at = closed_at

    async def _audit(
        self,
        session: AsyncSession,
        *,
        action: str,
        actor_user_id: UUID | None,
        affected_user: PlatformUserModel,
        previous_status: str | None,
        new_status: str | None,
        previous_role: str | None,
        new_role: str | None,
        reason: str | None,
        request_metadata: dict[str, object] | None,
        created_at: datetime,
    ) -> None:
        session.add(
            AccessAuditLogModel(
                id=uuid7(),
                action=action,
                actor_user_id=actor_user_id,
                affected_user_id=affected_user.id,
                previous_status=previous_status,
                new_status=new_status,
                previous_role=previous_role,
                new_role=new_role,
                reason=reason,
                correlation_id=None,
                request_metadata=request_metadata or {},
                created_at=created_at,
            )
        )

    async def _decision_outbox(
        self,
        session: AsyncSession,
        *,
        user: PlatformUserModel,
        action: str,
    ) -> None:
        await self._add_outbox(
            session,
            IntegrationEvent(
                event_type=f"access.{action}",
                aggregate_type="platform_user",
                aggregate_id=user.id,
                payload={
                    "platform_user_id": str(user.id),
                    "access_status": user.access_status,
                    "role": user.role,
                    "verified_email": user.verified_email,
                },
                producer="access-control",
                idempotency_key=f"access.{action}:{user.id}:{datetime.now(UTC).isoformat()}",
            ),
        )

    async def _add_outbox(self, session: AsyncSession, event: IntegrationEvent) -> None:
        session.add(
            OutboxEventModel(
                id=event.event_id,
                event_type=event.event_type,
                event_version=event.event_version,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                payload=event.payload,
                occurred_at=event.occurred_at,
                producer=event.producer,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                traceparent=event.traceparent,
                idempotency_key=event.idempotency_key,
            )
        )


def assert_approved(user: CurrentUser) -> None:
    now = datetime.now(UTC)
    if user.access_status == AccessStatus.APPROVED:
        if user.access_expires_at is not None and user.access_expires_at <= now:
            raise AccessDeniedError("access_expired", "access has expired")
        return
    code = {
        AccessStatus.PENDING: "access_pending",
        AccessStatus.REJECTED: "access_rejected",
        AccessStatus.SUSPENDED: "access_suspended",
        AccessStatus.REVOKED: "access_revoked",
        AccessStatus.EXPIRED: "access_expired",
    }.get(user.access_status, "access_denied")
    raise AccessDeniedError(code, "account is not approved for this resource")


def assert_permission(user: CurrentUser, permission: str) -> None:
    assert_approved(user)
    if permission not in user.permissions:
        raise AccessDeniedError("insufficient_role", "account role cannot access this resource")


def _matches_owner_bootstrap(
    identity: IdentityClaims,
    *,
    bootstrap_owner_provider: str | None,
    bootstrap_owner_user_id: str | None,
    bootstrap_owner_email: str | None,
) -> bool:
    if not bootstrap_owner_provider or not bootstrap_owner_user_id:
        return False
    if identity.provider != bootstrap_owner_provider:
        return False
    if identity.provider_user_id != bootstrap_owner_user_id:
        return False
    if bootstrap_owner_email:
        return identity.verified_email == bootstrap_owner_email
    return True


def _user_view(user: PlatformUserModel) -> PlatformUserView:
    return PlatformUserView(
        id=user.id,
        auth_provider=user.auth_provider,
        auth_provider_user_id=user.auth_provider_user_id,
        verified_email=user.verified_email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        access_status=AccessStatus(user.access_status),
        role=AccessRole(user.role),
        requested_at=user.requested_at,
        approved_at=user.approved_at,
        rejected_at=user.rejected_at,
        rejection_reason=user.rejection_reason,
        suspended_at=user.suspended_at,
        suspension_reason=user.suspension_reason,
        revoked_at=user.revoked_at,
        revocation_reason=user.revocation_reason,
        access_expires_at=user.access_expires_at,
        last_login_at=user.last_login_at,
        last_activity_at=user.last_activity_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _current_user_from_model(
    user: PlatformUserModel,
    *,
    credential_source: str,
) -> CurrentUser:
    view = _user_view(user)
    return CurrentUser(
        **view.model_dump(),
        permissions=frozenset(permission.value for permission in permissions_for_role(view.role)),
        credential_source=credential_source,
    )


def _request_view(
    request: AccessRequestModel,
    *,
    user: PlatformUserModel | None = None,
) -> AccessRequestView:
    return AccessRequestView(
        id=request.id,
        user_id=request.user_id,
        status=request.status,
        purpose=request.purpose,
        requested_at=request.requested_at,
        closed_at=request.closed_at,
        decision_reason=request.decision_reason,
        created_at=request.created_at,
        updated_at=request.updated_at,
        user=_user_view(user) if user else None,
    )


def _audit_view(row: AccessAuditLogModel) -> AccessAuditLogView:
    return AccessAuditLogView(
        id=row.id,
        action=row.action,
        actor_user_id=row.actor_user_id,
        affected_user_id=row.affected_user_id,
        previous_status=row.previous_status,
        new_status=row.new_status,
        previous_role=row.previous_role,
        new_role=row.new_role,
        reason=row.reason,
        created_at=row.created_at,
    )
