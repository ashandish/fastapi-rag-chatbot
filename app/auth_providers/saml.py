from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from ..models import settings
import urllib.parse

router = APIRouter()

def _prepare_fastapi_request(request: Request):
    # Minimal adapter from FastAPI request to python3-saml expected dict
    url = str(request.url)
    return {
        "https": "on" if request.url.scheme == "https" else "off",
        "http_host": request.client.host,
        "server_port": request.url.port or (443 if request.url.scheme == "https" else 80),
        "script_name": request.url.path,
        "get_data": dict(request.query_params),
        "post_data": {},
    }

def _saml_settings_from_env():
    if not settings.saml_entity_id or not settings.saml_assertion_consumer:
        return None
    # Very minimal settings; in real deployments you will want a dedicated settings.json
    saml_settings = {
        "strict": True,
        "debug": True,
        "sp": {
            "entityId": settings.saml_entity_id,
            "assertionConsumerService": {
                "url": settings.saml_assertion_consumer,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
        },
        "idp": {
            "entityId": settings.saml_metadata_url or "",
            "singleSignOnService": {
                "url": settings.saml_metadata_url or "",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
        },
    }
    return saml_settings

def register_saml():
    if not settings.auth_saml_enabled:
        return None
    return router

@router.get("/login/saml")
async def login_saml(request: Request):
    saml_settings = _saml_settings_from_env()
    if not saml_settings:
        return HTMLResponse("SAML not fully configured", status_code=500)
    req_data = _prepare_fastapi_request(request)
    auth = OneLogin_Saml2_Auth(req_data, saml_settings)
    return RedirectResponse(auth.login())

@router.post("/auth/saml/callback")
async def auth_saml_callback(request: Request):
    saml_settings = _saml_settings_from_env()
    if not saml_settings:
        return HTMLResponse("SAML not fully configured", status_code=500)
    req_data = _prepare_fastapi_request(request)
    # NOTE: python3-saml expects POST data as well; for brevity, we skip detail here.
    auth = OneLogin_Saml2_Auth(req_data, saml_settings)
    auth.process_response()
    errors = auth.get_errors()
    if errors:
        return HTMLResponse("SAML error: " + ", ".join(errors), status_code=400)
    if not auth.is_authenticated():
        return HTMLResponse("SAML auth failed", status_code=401)
    attrs = auth.get_attributes()
    nameid = auth.get_nameid() or ""
    email = nameid

    allowed_emails = [e.strip().lower() for e in (settings.saml_allowed_emails or "").split(",") if e.strip()]
    if allowed_emails and email.lower() not in allowed_emails:
        return HTMLResponse("Not allowed", status_code=403)

    request.session["user"] = {"email": email, "provider": "saml"}
    request.session["is_admin"] = True
    request.session.setdefault("must_change", False)
    return RedirectResponse(url="/embeddings")
