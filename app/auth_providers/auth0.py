from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from ..models import settings

router = APIRouter()

def register_auth0(oauth: OAuth):
    if not settings.auth_auth0_enabled:
        return None
    if not settings.auth0_domain:
        return None

    oauth.register(
        "auth0",
        client_id=settings.auth0_client_id,
        client_secret=settings.auth0_client_secret,
        client_kwargs={"scope": "openid email profile"},
        api_base_url=f"https://{settings.auth0_domain}",
        access_token_url=f"https://{settings.auth0_domain}/oauth/token",
        authorize_url=f"https://{settings.auth0_domain}/authorize",
    )
    return router

@router.get("/login/auth0")
async def login_with_auth0(request: Request):
    redirect_uri = settings.auth0_redirect_uri or str(request.url_for("auth_auth0_callback"))
    return await request.app.state.oauth.auth0.authorize_redirect(request, redirect_uri)

@router.get("/auth/auth0/callback")
async def auth_auth0_callback(request: Request):
    token = await request.app.state.oauth.auth0.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")

    if not email:
        return RedirectResponse(url="/admin/login")

    allowed_emails = [e.strip().lower() for e in (settings.auth0_allowed_emails or "").split(",") if e.strip()]
    if allowed_emails and email.lower() not in allowed_emails:
        return RedirectResponse(url="/admin/login")

    request.session["user"] = {"email": email, "provider": "auth0"}
    request.session["is_admin"] = True
    request.session.setdefault("must_change", False)
    return RedirectResponse(url="/embeddings")
