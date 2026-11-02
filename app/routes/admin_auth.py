"""Formularanmeldung und serverseitig widerrufbare Admin-Sitzungen."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.auth import (
    admin_configured,
    admin_credentials_valid,
    create_admin_session,
    request_is_admin,
    require_admin,
    require_admin_csrf,
    require_same_origin,
    revoke_admin_session,
    safe_admin_next,
)
from app.templating import page_context, templates

router = APIRouter()


def login_page(
    request: Request, *, target="/admin", username="", error="", status_code=200, headers=None
):
    return templates.TemplateResponse(
        request=request,
        name="admin_login.html",
        context=page_context(
            request,
            "admin_login",
            "",
            target=target,
            username=username,
            error=error,
            logged_out=request.query_params.get("abgemeldet") == "1",
        ),
        status_code=status_code,
        headers=headers,
    )


@router.get("/admin/anmelden")
def login(request: Request):
    if not admin_configured():
        return login_page(request, error="Admin-Zugang ist nicht konfiguriert.", status_code=503)
    target = safe_admin_next(request.query_params.get("next", "/admin"))
    if request_is_admin(request):
        return RedirectResponse(target, status_code=303)
    return login_page(request, target=target)


@router.post(
    "/admin/anmelden", dependencies=[Depends(require_admin_csrf), Depends(require_same_origin)]
)
async def submit_login(request: Request):
    from starlette.concurrency import run_in_threadpool

    from app.middleware import consume_rate_limit

    if not admin_configured():
        return login_page(request, error="Admin-Zugang ist nicht konfiguriert.", status_code=503)
    async with request.form(max_files=0, max_fields=4, max_part_size=4096) as form:
        username = form.get("username", "")
        password = form.get("password", "")
        target = safe_admin_next(str(form.get("next", "/admin")))
    retry = await run_in_threadpool(
        consume_rate_limit,
        request.client.host if request.client else "unknown",
        namespace="admin-login",
    )
    if retry:
        return login_page(
            request,
            target=target,
            error="Zu viele Anmeldeversuche. Bitte später erneut versuchen.",
            status_code=429,
            headers={"Retry-After": str(retry)},
        )
    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or len(username) > 256
        or len(password) > 4096
        or not admin_credentials_valid(username, password)
    ):
        return login_page(
            request,
            target=target,
            username=username[:256] if isinstance(username, str) else "",
            error="Benutzername oder Passwort ist falsch.",
            status_code=401,
        )
    response = RedirectResponse(target, status_code=303)
    await run_in_threadpool(create_admin_session, request, response)
    return response


@router.post("/admin/abmelden", dependencies=[Depends(require_admin), Depends(require_admin_csrf)])
def logout(request: Request):
    response = RedirectResponse("/admin/anmelden?abgemeldet=1", status_code=303)
    revoke_admin_session(request, response)
    return response
