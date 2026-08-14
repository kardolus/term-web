"""Keycloak OIDC gate — ringer's pattern (authlib handshake + itsdangerous signed
cookie; Starlette SessionMiddleware only carries the transient OIDC state/nonce).

Every page/API handler calls `require_user(request)`: returns the email for a
valid session, or a RedirectResponse/JSONResponse to return as-is. Public paths
(/favicon.svg, /healthz) never call it.
"""

from authlib.integrations.starlette_client import OAuth
from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from . import config

SESSION_COOKIE = "term_session"
# This cookie is a shell on forge — much shorter-lived than the other apps' 14d.
SESSION_MAX_AGE = 60 * 60 * 72  # 3 days

_serializer = URLSafeTimedSerializer(config.SESSION_SECRET)

oauth = OAuth()
oauth.register(
    name="keycloak",
    server_metadata_url=f"{config.KEYCLOAK_ISSUER}/.well-known/openid-configuration",
    client_id=config.KEYCLOAK_CLIENT_ID,
    client_secret=config.KEYCLOAK_CLIENT_SECRET,
    client_kwargs={"scope": "openid email profile"},
)


def create_session_cookie(email: str) -> str:
    return _serializer.dumps({"email": email})


def verify_session_cookie(cookie_value: str | None) -> str | None:
    if not cookie_value:
        return None
    try:
        return _serializer.loads(cookie_value, max_age=SESSION_MAX_AGE).get("email")
    except BadSignature:
        return None


def current_user(request: Request) -> str | None:
    email = verify_session_cookie(request.cookies.get(SESSION_COOKIE))
    if email in config.ALLOWED_EMAILS:
        return email
    return None


def require_user(request: Request, api: bool = False):
    """Email for a valid session, else the response to send instead."""
    email = current_user(request)
    if email:
        return email
    if api:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return RedirectResponse(url="/auth/login")


async def login(request: Request):
    redirect_uri = f"{config.PUBLIC_BASE_URL}/auth/callback"
    # kc_idp_hint=google skips Keycloak's login page straight to Google (Grafana/ringer pattern).
    return await oauth.keycloak.authorize_redirect(request, redirect_uri, kc_idp_hint="google")


async def callback(request: Request):
    token = await oauth.keycloak.authorize_access_token(request)
    userinfo = token.get("userinfo") or await oauth.keycloak.userinfo(token=token)
    email = (userinfo or {}).get("email")
    if email not in config.ALLOWED_EMAILS:
        # Realm-level lockdown is the first gate; this app-level allow-list is
        # defense in depth AND per-app scoping — a shell on forge is single-user.
        return JSONResponse({"error": "forbidden"}, status_code=403)
    resp = RedirectResponse(url="/")
    resp.set_cookie(
        SESSION_COOKIE, create_session_cookie(email),
        max_age=SESSION_MAX_AGE, httponly=True, secure=True, samesite="lax",
    )
    return resp
