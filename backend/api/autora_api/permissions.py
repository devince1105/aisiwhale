"""What each back-office role may do (AD-09, D-234 ①), in one place.

Permission keys are ``module:action``. Every route through the back office's door that changes
something needs one, named here by its method and template; a read needs one only when listed
(the audit trail, a reader's coin wallet) — everything else any role may read. ``require_operator``
looks the route up and refuses (403) a role without the key; test_admin_permissions.py fails if a
write route is missing from the table, so a new one cannot slip in open.

The roles: ``owner`` everything; ``editor`` the newsroom and its approvals; ``finance`` money,
memberships and coins; ``viewer`` reads. ADMIN_EMAILS are owners; so is the operator token —
the machines' (CI, scripts, the worker), recorded as ``operator`` in the audit trail (D-234 ②).
"""

from __future__ import annotations

from autora.db.models import AdminRoleName

NEWSROOM = "newsroom:edit"
APPROVALS = "approvals:decide"
PROJECTS = "projects:manage"
WORKFLOWS = "workflows:run"
AGENTS = "agents:manage"
COMPANY = "company:manage"
FINANCE = "finance:edit"
MEMBERSHIPS = "memberships:grant"
COINS_ADJUST = "coins:adjust"
COINS_VIEW = "coins:view"
AUDIT = "audit:view"
ACCESS = "access:manage"
SELF = "self:prefs"
"""One's own preferences (AD-10): every role has it."""

ALL = frozenset(
    {
        NEWSROOM,
        APPROVALS,
        PROJECTS,
        WORKFLOWS,
        AGENTS,
        COMPANY,
        FINANCE,
        MEMBERSHIPS,
        COINS_ADJUST,
        COINS_VIEW,
        AUDIT,
        ACCESS,
        SELF,
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    AdminRoleName.OWNER: ALL,
    AdminRoleName.EDITOR: frozenset({NEWSROOM, APPROVALS, PROJECTS, WORKFLOWS, SELF}),
    AdminRoleName.FINANCE: frozenset({FINANCE, MEMBERSHIPS, COINS_ADJUST, COINS_VIEW, SELF}),
    AdminRoleName.VIEWER: frozenset({SELF}),
}

ROUTES: dict[tuple[str, str], str] = {
    # the company and its people
    ("POST", "/api/companies"): COMPANY,
    ("PUT", "/api/companies/{company_id}/office-theme"): COMPANY,
    ("POST", "/api/companies/{company_id}/agents"): AGENTS,
    ("POST", "/api/companies/{company_id}/agents/{agent_id}/pause"): AGENTS,
    ("POST", "/api/companies/{company_id}/agents/{agent_id}/resume"): AGENTS,
    ("POST", "/api/companies/{company_id}/agents/{agent_id}/retire"): AGENTS,
    # work
    ("POST", "/api/approvals/{approval_id}/decide"): APPROVALS,
    ("POST", "/api/companies/{company_id}/workflows"): WORKFLOWS,
    ("POST", "/api/companies/{company_id}/workflows/{workflow_run_id}/restart"): WORKFLOWS,
    ("POST", "/api/companies/{company_id}/projects/{project_id}/pause"): PROJECTS,
    ("POST", "/api/companies/{company_id}/projects/{project_id}/resume"): PROJECTS,
    # the newsroom
    ("POST", "/api/stories/{story_id}/start"): NEWSROOM,
    ("POST", "/api/companies/{company_id}/sources"): NEWSROOM,
    ("POST", "/api/companies/{company_id}/team/messages"): NEWSROOM,
    ("POST", "/api/articles/{article_id}/access"): NEWSROOM,
    ("POST", "/api/articles/{article_id}/section"): NEWSROOM,
    ("POST", "/api/articles/{article_id}/unpublish"): NEWSROOM,
    ("POST", "/api/articles/{article_id}/republish"): NEWSROOM,
    ("POST", "/api/articles/{article_id}/revise"): NEWSROOM,
    ("POST", "/api/articles/{article_id}/cover/swap"): NEWSROOM,
    ("POST", "/api/articles/{article_id}/cover/search"): NEWSROOM,
    ("POST", "/api/articles/{article_id}/cover/ask"): NEWSROOM,
    ("DELETE", "/api/articles/{article_id}/cover"): NEWSROOM,
    # money, memberships, coins
    ("POST", "/api/companies/{company_id}/finance/budgets"): FINANCE,
    ("POST", "/api/companies/{company_id}/finance/capital"): FINANCE,
    ("POST", "/api/admin/memberships/comps"): MEMBERSHIPS,
    ("POST", "/api/admin/memberships/comps/{grant_id}/revoke"): MEMBERSHIPS,
    ("POST", "/api/admin/coins/adjustments"): COINS_ADJUST,
    ("GET", "/api/admin/coins/wallet"): COINS_VIEW,  # a reader's details and history
    # the back office itself
    ("GET", "/api/admin/audit"): AUDIT,
    ("GET", "/api/admin/access"): ACCESS,
    ("POST", "/api/admin/access"): ACCESS,
    ("PUT", "/api/admin/access/{reader_id}"): ACCESS,
    ("DELETE", "/api/admin/access/{reader_id}"): ACCESS,
    ("PUT", "/api/admin/me/prefs"): SELF,
}


def needed(method: str, route: str) -> str | None:
    """The key a route needs, or None: any back-office role may (a read)."""
    return ROUTES.get((method, route))


def permissions_of(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())
