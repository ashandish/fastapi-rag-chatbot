from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from .models import settings

oauth = OAuth()

def configure_oauth(app):
    # Session middleware for OAuth state and admin session
    app.add_middleware(SessionMiddleware, secret_key="replace-with-strong-secret")

    # Google OAuth2
    if settings.auth_google_enabled:
        oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
            redirect_uri=settings.google_redirect_uri,
        )

    # Azure AD (OIDC)
    if settings.auth_azure_ad_enabled:
        oauth.register(
            name="azure_ad",
            client_id=settings.azure_ad_client_id,
            client_secret=settings.azure_ad_client_secret,
            server_metadata_url=f"https://login.microsoftonline.com/{settings.azure_ad_tenant_id}/v2.0/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
            redirect_uri=settings.azure_ad_redirect_uri,
        )

    # Okta OIDC
    if settings.auth_okta_enabled:
        oauth.register(
            name="okta",
            client_id=settings.okta_client_id,
            client_secret=settings.okta_client_secret,
            server_metadata_url=f"{settings.okta_issuer}/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
            redirect_uri=settings.okta_redirect_uri,
        )

    # Auth0 OIDC
    if settings.auth_auth0_enabled:
        oauth.register(
            name="auth0",
            client_id=settings.auth0_client_id,
            client_secret=settings.auth0_client_secret,
            server_metadata_url=f"https://{settings.auth0_domain}/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
            redirect_uri=settings.auth0_redirect_uri,
        )

    # SAML is configured separately in auth_providers/saml.py

    return oauth