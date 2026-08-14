"""term-web — browser terminal for Claude Code / Codex on forge.

Every page/API is OIDC-gated except /favicon.svg and /healthz. The WS endpoint
additionally requires a one-time ticket minted by POST /api/terminal and an
Origin check (see terminal.py for why: RCE is the feature, so layer everything).
"""

import asyncio
import time

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from . import auth, config, sessions, terminal, ui

_cache: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 15


async def _cached(key: str, fn):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    val = await asyncio.get_event_loop().run_in_executor(None, fn)
    _cache[key] = (now, val)
    return val


# ------------------------------------------------------------------ pages

async def picker(request: Request):
    user = auth.require_user(request)
    if not isinstance(user, str):
        return user
    return HTMLResponse(ui.page("term — sessions", ui.PICKER_BODY))


async def terminal_page(request: Request):
    user = auth.require_user(request)
    if not isinstance(user, str):
        return user
    name = request.path_params["name"]
    if not sessions.TMUX_NAME_RE.match(name):
        return RedirectResponse(url="/")
    css_url, css_sri = ui.XTERM_CSS
    head = f'<link rel="stylesheet" href="{css_url}" integrity="{css_sri}" crossorigin="anonymous">'
    return HTMLResponse(ui.page(f"term — {name}", ui.terminal_body(name), head_extra=head))


# ------------------------------------------------------------------ APIs

async def api_sessions(request: Request):
    user = auth.require_user(request, api=True)
    if not isinstance(user, str):
        return user
    claude, codex, tmux, workdirs = await asyncio.gather(
        _cached("claude", sessions.list_claude),
        _cached("codex", sessions.list_codex),
        _cached("tmux", sessions.list_tmux),
        _cached("workdirs", sessions.list_workdirs),
    )
    return JSONResponse({"claude": claude, "codex": codex,
                         "tmux": tmux, "workdirs": workdirs})


async def api_terminal(request: Request):
    user = auth.require_user(request, api=True)
    if not isinstance(user, str):
        return user
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse({"error": "bad json"}, status_code=400)
    try:
        target = await terminal.resolve_target(body)
    except terminal.TargetError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"ticket": terminal.mint_ticket(user, target),
                         "name": target["name"]})


# ------------------------------------------------------------------ WS

async def terminal_ws(ws: WebSocket):
    email = auth.verify_session_cookie(ws.cookies.get(auth.SESSION_COOKIE))
    if email not in config.ALLOWED_EMAILS:
        await ws.close(code=4401)
        return
    if ws.headers.get("origin") != config.PUBLIC_BASE_URL:
        await ws.close(code=4403)
        return
    target = terminal.redeem_ticket(ws.query_params.get("ticket", ""), email)
    if not target:
        await ws.close(code=4403)
        return
    if terminal.active_terminals >= config.MAX_TERMINALS:
        await ws.close(code=4429)
        return
    await ws.accept()
    await terminal.bridge(ws, target)


# ------------------------------------------------------------------ misc

async def favicon(request: Request):
    return Response(ui.FAVICON_SVG, media_type="image/svg+xml")


async def healthz(request: Request):
    return JSONResponse({"ok": True})


async def logout(request: Request):
    resp = RedirectResponse(url="/")
    resp.delete_cookie(auth.SESSION_COOKIE)
    return resp


routes = [
    Route("/", picker),
    Route("/t/{name}", terminal_page),
    Route("/api/sessions", api_sessions),
    Route("/api/terminal", api_terminal, methods=["POST"]),
    WebSocketRoute("/ws/term", terminal_ws),
    Route("/auth/login", auth.login),
    Route("/auth/callback", auth.callback),
    Route("/auth/logout", logout),
    Route("/favicon.svg", favicon),
    Route("/healthz", healthz),
]

app = Starlette(routes=routes)
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
