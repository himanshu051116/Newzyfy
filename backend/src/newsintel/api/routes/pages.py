# ruff: noqa: E501
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from newsintel.api.dependencies import AccessAdminAuth, AuthenticatedUserDependency, ViewerAuth
from newsintel.domain.access import AccessStatus

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def landing() -> str:
    return _page(
        "News Intelligence Platform",
        """
        <section class="hero">
          <p class="eyebrow">Private research platform</p>
          <h1>News Intelligence Platform</h1>
          <p class="lead">Track events, source coverage, provenance, extracted claims and ingestion freshness from reviewed news sources.</p>
          <div class="actions">
            <a class="button" href="/auth/login">Sign in</a>
            <a class="button secondary" href="/sign-in">Access details</a>
          </div>
        </section>
        <section class="band">
          <div>
            <h2>Approval based access</h2>
            <p>Anyone with a verified identity can sign in. New accounts are placed in a pending queue until the platform owner approves access.</p>
          </div>
          <div>
            <h2>Built for researchers</h2>
            <p>Approved users can inspect articles, events, source provenance and analysis views according to their assigned role.</p>
          </div>
        </section>
        """,
    )


@router.get("/sign-in", response_class=HTMLResponse)
async def sign_in(request: Request) -> str:
    settings = request.app.state.settings
    configured = settings.auth_mode == "oidc" or (
        settings.dev_auth_bypass_enabled and settings.environment != "production"
    )
    detail = (
        "Use your verified identity provider account. Your first sign-in creates one access request automatically."
        if configured
        else "Sign-in is not configured for this local checkout yet."
    )
    return _page(
        "Sign In",
        f"""
        <section class="panel narrow">
          <h1>Sign in</h1>
          <p>{detail}</p>
          <a class="button" href="/auth/login">Continue</a>
          <p class="muted">No extra request form is needed. If your account is pending, you will see its current status after signing in.</p>
        </section>
        """,
    )


@router.get("/pending", response_class=HTMLResponse)
async def pending(user: AuthenticatedUserDependency) -> str:
    submitted = user.requested_at.strftime("%Y-%m-%d %H:%M UTC")
    status_label = user.access_status.value.replace("_", " ").title()
    return _page(
        "Access Pending",
        f"""
        <section class="panel narrow">
          <p class="eyebrow">Access request</p>
          <h1>{status_label}</h1>
          <p>Your access request was submitted on {submitted}. The owner will review it. You do not need to submit another request.</p>
          <dl>
            <dt>Account</dt><dd>{_safe(user.verified_email or user.display_name or user.auth_provider_user_id)}</dd>
            <dt>Status</dt><dd>{status_label}</dd>
          </dl>
          <a class="button secondary" href="/auth/logout">Log out</a>
        </section>
        """,
    )


@router.get("/access-denied", response_class=HTMLResponse)
async def access_denied(user: AuthenticatedUserDependency) -> str:
    reason = {
        AccessStatus.REJECTED: user.rejection_reason or "This account was not approved.",
        AccessStatus.SUSPENDED: user.suspension_reason or "This account is currently suspended.",
        AccessStatus.REVOKED: user.revocation_reason or "This account no longer has access.",
        AccessStatus.EXPIRED: "This account's temporary access has expired.",
    }.get(user.access_status, "This account cannot access the application right now.")
    return _page(
        "Access Unavailable",
        f"""
        <section class="panel narrow">
          <p class="eyebrow">Account status</p>
          <h1>Access unavailable</h1>
          <p>{_safe(reason)}</p>
          <a class="button secondary" href="/auth/logout">Log out</a>
        </section>
        """,
    )


@router.get("/app", response_class=HTMLResponse)
async def app_home(user: ViewerAuth) -> str:
    return _page(
        "News Intelligence",
        f"""
        <section class="toolbar-page">
          <div>
            <p class="eyebrow">Approved workspace</p>
            <h1>News Intelligence</h1>
            <p class="muted">Signed in as {_safe(user.verified_email or user.display_name or "approved user")} with role {user.role.value.replace("_", " ")}.</p>
          </div>
          <a class="button secondary" href="/auth/logout">Log out</a>
        </section>
        <section class="grid">
          <a class="tile" href="/news-sources"><h2>Sources</h2><p>Manage reviewed publishers and fetch jobs if your role allows it.</p></a>
          <a class="tile" href="/api/v1/articles"><h2>Articles API</h2><p>Inspect the latest approved article records.</p></a>
          <a class="tile" href="/admin/access-console"><h2>Access Admin</h2><p>Review pending users and account history.</p></a>
        </section>
        """,
    )


@router.get("/admin/access-console", response_class=HTMLResponse)
async def access_console(_auth: AccessAdminAuth) -> str:
    return _page(
        "Access Admin",
        """
        <section class="toolbar-page">
          <div>
            <p class="eyebrow">Administration</p>
            <h1>User Access</h1>
            <p class="muted">Approve, reject, suspend, restore and revoke platform accounts.</p>
          </div>
          <button onclick="loadAccess()">Refresh</button>
        </section>
        <section class="panel">
          <h2>Pending Requests <span id="pendingCount" class="badge">0</span></h2>
          <div id="pendingList" class="stack"></div>
        </section>
        <section class="panel">
          <h2>Users</h2>
          <label class="search">Search <input id="userSearch" oninput="loadUsers()" placeholder="Name or email" /></label>
          <div id="userList" class="stack"></div>
        </section>
        <script>
          function csrf() {
            return document.cookie.split('; ').find(x => x.startsWith('newsintel_csrf='))?.split('=')[1] || '';
          }
          async function api(path, options = {}) {
            const headers = Object.assign({'Content-Type': 'application/json', 'X-CSRF-Token': csrf()}, options.headers || {});
            const res = await fetch(path, Object.assign({credentials: 'same-origin'}, options, {headers}));
            if (!res.ok) throw new Error(await res.text());
            return await res.json();
          }
          function userLine(user) {
            const label = `${user.display_name || 'Unnamed'} - ${user.verified_email || user.auth_provider_user_id}`;
            return `<div class="row"><div><b>${label}</b><p>${user.access_status} - ${user.role}</p></div><div class="actions">
              <button onclick="approve('${user.id}')">Approve</button>
              <button class="secondary" onclick="suspendUser('${user.id}')">Suspend</button>
              <button class="danger" onclick="revokeUser('${user.id}')">Revoke</button>
            </div></div>`;
          }
          async function loadAccess() {
            const pending = await api('/api/v1/admin/access/requests');
            document.getElementById('pendingCount').textContent = pending.length;
            document.getElementById('pendingList').innerHTML = pending.length ? pending.map(x => userLine(x.user)).join('') : '<p class="muted">No pending requests.</p>';
            await loadUsers();
          }
          async function loadUsers() {
            const q = encodeURIComponent(document.getElementById('userSearch')?.value || '');
            const users = await api(`/api/v1/admin/access/users${q ? '?q=' + q : ''}`);
            document.getElementById('userList').innerHTML = users.map(userLine).join('');
          }
          async function approve(id) {
            const role = prompt('Role: viewer, analyst, source_manager, administrator', 'viewer');
            if (!role) return;
            await api(`/api/v1/admin/access/users/${id}/approve`, {method: 'POST', body: JSON.stringify({role})});
            await loadAccess();
          }
          async function suspendUser(id) {
            const reason = prompt('Suspension note');
            if (reason === null) return;
            await api(`/api/v1/admin/access/users/${id}/suspend`, {method: 'POST', body: JSON.stringify({reason, user_visible_reason: reason})});
            await loadAccess();
          }
          async function revokeUser(id) {
            if (!confirm('Revoke this account?')) return;
            const reason = prompt('Revocation note');
            await api(`/api/v1/admin/access/users/${id}/revoke`, {method: 'POST', body: JSON.stringify({reason, user_visible_reason: reason})});
            await loadAccess();
          }
          loadAccess().catch(err => document.getElementById('pendingList').innerHTML = `<p class="error">${err.message}</p>`);
        </script>
        """,
    )


def _page(title: str, body: str) -> str:
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, Segoe UI, system-ui, sans-serif; background: #f7f8fb; color: #111827; }}
    body {{ margin: 0; min-height: 100vh; }}
    body::before {{ content: ""; position: fixed; inset: 0 0 auto; height: 8px; background: #0f766e; }}
    main {{ width: min(1120px, calc(100% - 32px)); margin: 0 auto; padding: 56px 0; }}
    h1 {{ font-size: clamp(34px, 6vw, 64px); line-height: 1; margin: 0 0 16px; }}
    h2 {{ margin: 0 0 10px; font-size: 20px; }}
    p {{ line-height: 1.55; }}
    a {{ color: inherit; }}
    .hero {{ min-height: 58vh; display: grid; align-content: center; }}
    .lead {{ max-width: 720px; font-size: 20px; color: #374151; }}
    .eyebrow {{ text-transform: uppercase; letter-spacing: .08em; color: #0f766e; font-weight: 700; font-size: 13px; }}
    .actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .button, button {{ display: inline-flex; align-items: center; justify-content: center; min-height: 42px; border: 0; border-radius: 8px; padding: 0 16px; background: #0f766e; color: #fff; font-weight: 700; text-decoration: none; cursor: pointer; }}
    .button.secondary, button.secondary {{ background: #e5e7eb; color: #111827; }}
    button.danger {{ background: #b91c1c; }}
    .band, .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }}
    .panel, .tile {{ background: #fff; border: 1px solid #d1d5db; border-radius: 8px; padding: 20px; box-shadow: 0 8px 28px rgba(15, 23, 42, .08); }}
    .tile {{ text-decoration: none; }}
    .narrow {{ max-width: 620px; margin: 8vh auto; }}
    .muted {{ color: #4b5563; }}
    .toolbar-page {{ display: flex; justify-content: space-between; gap: 16px; align-items: center; margin-bottom: 24px; }}
    .stack {{ display: grid; gap: 10px; }}
    .row {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }}
    .row p {{ margin: 4px 0 0; color: #4b5563; }}
    .badge {{ display: inline-flex; align-items: center; justify-content: center; min-width: 28px; height: 28px; border-radius: 999px; background: #0f766e; color: #fff; font-size: 14px; }}
    .search {{ display: grid; gap: 6px; margin-bottom: 12px; color: #374151; }}
    input {{ min-height: 42px; border: 1px solid #9ca3af; border-radius: 8px; padding: 0 12px; font: inherit; }}
    :focus-visible {{ outline: 3px solid #14b8a6; outline-offset: 2px; }}
    @media (max-width: 720px) {{ .toolbar-page, .row {{ align-items: stretch; flex-direction: column; }} }}
  </style>
</head>
<body>
  <main>{body}</main>
</body>
</html>
"""


def _safe(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
