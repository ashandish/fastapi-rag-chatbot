from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from ..models import settings

router = APIRouter()

def register_okta(oauth: OAuth):
    if not settings.auth_okta_enabled:
        return None
    if not settings.okta_issuer:
        return None

    oauth.register(
        "okta",
        server_metadata_url=f"{settings.okta_issuer}/.well-known/openid-configuration",
        client_id=settings.okta_client_id,
        client_secret=settings.okta_client_secret,
        client_kwargs={"scope": "openid email profile"},
    )
    return router

@router.get("/login/okta")
async def login_with_okta(request: Request):
    redirect_uri = settings.okta_redirect_uri or str(request.url_for("auth_okta_callback"))
    return await request.app.state.oauth.okta.authorize_redirect(request, redirect_uri)

@router.get("/auth/okta/callback")
async def auth_okta_callback(request: Request):
    token = await request.app.state.oauth.okta.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")

    if not email:
        return RedirectResponse(url="/admin/login")

    # Group checks are environment-specific; use OKTA_ALLOWED_GROUPS as a hint
    request.session["user"] = {"email": email, "provider": "okta"}
    request.session["is_admin"] = True
    request.session.setdefault("must_change", False)
    return RedirectResponse(url="/embeddings")
