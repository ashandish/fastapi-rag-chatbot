from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from ..models import settings

def register_aad(oauth):
    """
    Azure AD / Entra ID OAuth2 provider registration
    Returns router if enabled, otherwise None.
    """
    if not settings.auth_azure_ad_enabled:
        return None

    router = APIRouter(prefix="/auth/aad")

    @router.get("/login")
    async def login(request: Request):
        redirect_uri = settings.azure_ad_redirect_uri
        return await oauth.azure_ad.authorize_redirect(request, redirect_uri)

    @router.get("/callback")
    async def callback(request: Request):
        token = await oauth.azure_ad.authorize_access_token(request)
        user = token.get("userinfo") or {}

        email = user.get("email", "").lower()

        allowed_groups = [g.strip().lower() for g in settings.azure_ad_allowed_groups.split(",") if g.strip()]

        request.session["user"] = {
            "email": email,
            "provider": "azure_ad",
        }

        return RedirectResponse(url="/")

    return router
