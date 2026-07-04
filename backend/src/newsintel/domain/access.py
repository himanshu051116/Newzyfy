from enum import StrEnum


class AccessStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"


class AccessRole(StrEnum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    SOURCE_MANAGER = "source_manager"
    ADMINISTRATOR = "administrator"
    OWNER = "owner"


class Permission(StrEnum):
    CONTENT_VIEW = "content:view"
    CLAIMS_VIEW = "claims:view"
    RESEARCH_ADVANCED = "research:advanced"
    SOURCES_VIEW = "sources:view"
    SOURCES_MANAGE = "sources:manage"
    OPERATIONS_VIEW = "operations:view"
    USERS_MANAGE = "users:manage"
    SETTINGS_MANAGE = "settings:manage"
    OWNER_MANAGE = "owner:manage"


ROLE_PERMISSIONS: dict[AccessRole, frozenset[Permission]] = {
    AccessRole.VIEWER: frozenset(
        {
            Permission.CONTENT_VIEW,
            Permission.SOURCES_VIEW,
        }
    ),
    AccessRole.ANALYST: frozenset(
        {
            Permission.CONTENT_VIEW,
            Permission.CLAIMS_VIEW,
            Permission.RESEARCH_ADVANCED,
            Permission.SOURCES_VIEW,
        }
    ),
    AccessRole.SOURCE_MANAGER: frozenset(
        {
            Permission.CONTENT_VIEW,
            Permission.CLAIMS_VIEW,
            Permission.RESEARCH_ADVANCED,
            Permission.SOURCES_VIEW,
            Permission.SOURCES_MANAGE,
            Permission.OPERATIONS_VIEW,
        }
    ),
    AccessRole.ADMINISTRATOR: frozenset(
        {
            Permission.CONTENT_VIEW,
            Permission.CLAIMS_VIEW,
            Permission.RESEARCH_ADVANCED,
            Permission.SOURCES_VIEW,
            Permission.SOURCES_MANAGE,
            Permission.OPERATIONS_VIEW,
            Permission.USERS_MANAGE,
            Permission.SETTINGS_MANAGE,
        }
    ),
    AccessRole.OWNER: frozenset(Permission),
}


def permissions_for_role(role: AccessRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]


def role_has_permission(role: AccessRole, permission: Permission) -> bool:
    return permission in permissions_for_role(role)
