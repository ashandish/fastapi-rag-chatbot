from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal
import os

class Settings(BaseSettings):
    # LLM provider selection
    llm_provider: Literal["openai", "local"] = Field(default="openai", alias="LLM_PROVIDER")
    llm_model_openai: str = Field(default="gpt-4o-mini", alias="LLM_MODEL_OPENAI")

    # Local LLM (OpenAI-compatible server such as Ollama or llama.cpp server)
    local_llm_endpoint: str = Field(default="http://localhost:11434/v1", alias="LOCAL_LLM_ENDPOINT")
    local_llm_size: Literal["small", "large"] = Field(default="small", alias="LOCAL_LLM_SIZE")  # small=8B Q4, large=70B
    local_llm_model_small: str = Field(default="llama3:8b-instruct-q4_0", alias="LOCAL_LLM_MODEL_SMALL")
    local_llm_model_large: str = Field(default="llama3:70b-instruct", alias="LOCAL_LLM_MODEL_LARGE")

    # OpenAI & embeddings
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    embed_store_path: str = Field(default="/data/chroma_store", alias="EMBED_STORE_PATH")

    embed_mode: Literal["cpu", "gpu"] = Field(default="cpu", alias="EMBED_MODE")
    text_embed_model_cpu: str = Field(default="all-MiniLM-L6-v2", alias="TEXT_EMBED_MODEL_CPU")
    image_embed_model_cpu: str = Field(default="clip-ViT-B-32", alias="IMAGE_EMBED_MODEL_CPU")
    text_embed_model_gpu: str = Field(default="all-mpnet-base-v2", alias="TEXT_EMBED_MODEL_GPU")
    image_embed_model_gpu: str = Field(default="clip-ViT-L-14", alias="IMAGE_EMBED_MODEL_GPU")
    text_embed_model_local_small: str = Field(default="BAAI/bge-small-en", alias="TEXT_EMBED_MODEL_LOCAL_SMALL")
    text_embed_model_local_large: str = Field(default="BAAI/bge-large-en", alias="TEXT_EMBED_MODEL_LOCAL_LARGE")

    chunk_size_tokens: int = Field(default=1024, alias="CHUNK_SIZE_TOKENS")
    top_k_initial: int = Field(default=50, alias="TOP_K_INITIAL")
    top_k_reranked: int = Field(default=5, alias="TOP_K_RERANKED")
    rerank_enabled: bool = Field(default=True, alias="RERANK_ENABLED")

    max_file_size_mb: int = Field(default=10, alias="MAX_FILE_SIZE_MB")
    max_total_doc_size_mb: int = Field(default=1024, alias="MAX_TOTAL_DOC_SIZE_MB")

    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password_plain: str = Field(default="", alias="ADMIN_PASSWORD")
    admin_password_hash: str = Field(default="", alias="ADMIN_PASSWORD_HASH")

    chatbot_welcome_msg: str = Field(
        default="Hi, what is your query today?", alias="CHATBOT_WELCOME_MSG"
    )

    # ----------------------------
    # Authentication provider flags & config
    # ----------------------------

    # Google OAuth2
    auth_google_enabled: bool = Field(default=False, alias="AUTH_GOOGLE_ENABLED")
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(default="", alias="GOOGLE_REDIRECT_URI")
    google_allowed_domains: str = Field(default="", alias="GOOGLE_ALLOWED_DOMAINS")

    # Azure AD (Entra ID)
    auth_azure_ad_enabled: bool = Field(default=False, alias="AUTH_AZURE_AD_ENABLED")
    azure_ad_tenant_id: str = Field(default="", alias="AZURE_AD_TENANT_ID")
    azure_ad_client_id: str = Field(default="", alias="AZURE_AD_CLIENT_ID")
    azure_ad_client_secret: str = Field(default="", alias="AZURE_AD_CLIENT_SECRET")
    azure_ad_redirect_uri: str = Field(default="", alias="AZURE_AD_REDIRECT_URI")
    azure_ad_allowed_groups: str = Field(default="", alias="AZURE_AD_ALLOWED_GROUPS")

    # Okta OIDC
    auth_okta_enabled: bool = Field(default=False, alias="AUTH_OKTA_ENABLED")
    okta_issuer: str = Field(default="", alias="OKTA_ISSUER")
    okta_client_id: str = Field(default="", alias="OKTA_CLIENT_ID")
    okta_client_secret: str = Field(default="", alias="OKTA_CLIENT_SECRET")
    okta_redirect_uri: str = Field(default="", alias="OKTA_REDIRECT_URI")
    okta_allowed_groups: str = Field(default="", alias="OKTA_ALLOWED_GROUPS")

    # Auth0 OIDC
    auth_auth0_enabled: bool = Field(default=False, alias="AUTH_AUTH0_ENABLED")
    auth0_domain: str = Field(default="", alias="AUTH0_DOMAIN")
    auth0_client_id: str = Field(default="", alias="AUTH0_CLIENT_ID")
    auth0_client_secret: str = Field(default="", alias="AUTH0_CLIENT_SECRET")
    auth0_redirect_uri: str = Field(default="", alias="AUTH0_REDIRECT_URI")
    auth0_allowed_emails: str = Field(default="", alias="AUTH0_ALLOWED_EMAILS")

    # SAML (Azure AD / Okta / ADFS)
    auth_saml_enabled: bool = Field(default=False, alias="AUTH_SAML_ENABLED")
    saml_metadata_url: str = Field(default="", alias="SAML_METADATA_URL")
    saml_entity_id: str = Field(default="", alias="SAML_ENTITY_ID")
    saml_assertion_consumer: str = Field(default="", alias="SAML_ASSERTION_CONSUMER")
    saml_allowed_emails: str = Field(default="", alias="SAML_ALLOWED_EMAILS")

    class Config:
        case_sensitive = False
        env_file = ".env"

settings = Settings()

os.makedirs(settings.embed_store_path, exist_ok=True)
UPLOAD_DIR = os.path.join(os.path.dirname(settings.embed_store_path), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ADMIN_HASH_FILE = os.path.join(os.path.dirname(settings.embed_store_path), "admin_hash.txt")
