from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from ..models import settings

router = APIRouter()

def register_google(oauth: OAuth):
    if not settings.auth_google_enabled:
        return None

    oauth.register(
        "google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return router

@router.get("/login/google")
async def login_with_google(request: Request):
    redirect_uri = settings.google_redirect_uri or str(request.url_for("auth_google_callback"))
    return await request.app.state.oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/auth/google/callback")
async def auth_google_callback(request: Request):
    token = await request.app.state.oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")

    if not email:
        return RedirectResponse(url="/admin/login")

    allowed_domains = [d.strip().lower() for d in (settings.google_allowed_domains or "").split(",") if d.strip()]
    if allowed_domains:
        domain = email.split("@")[-1].lower()
        if domain not in allowed_domains:
            return RedirectResponse(url="/admin/login")

    # Mark as admin
    request.session["user"] = {"email": email, "provider": "google"}
    request.session["is_admin"] = True
    request.session.setdefault("must_change", False)
    return RedirectResponse(url="/embeddings")
