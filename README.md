# FastAPI RAG Chatbot v11 — Multi-Auth

Production-grade retrieval-augmented chatbot with admin-managed embeddings, progress UI, and multiple optional identity providers.

## Stack and architecture
- API & transport: FastAPI served by Gunicorn using Uvicorn workers; WebSocket endpoint (`/ws/chat`) streams chat responses; Jinja2 templates + static assets render chat/admin/embeddings pages.
- Background jobs: Celery worker (`app/tasks.py`) processes embedding jobs; Redis (broker + backend + progress store) coordinates tasks and exposes progress polled by the UI.
- Retrieval & ranking: ChromaDB persistent store at `/data/chroma_store`; SentenceTransformers text encoder selected by `EMBED_MODE`; token-based chunking (`CHUNK_SIZE_TOKENS`, 20% overlap) in `app/utils.py`; image files are OCR-extracted and indexed as text; optional cross-encoder reranking (`cross-encoder/ms-marco-MiniLM-L-6-v2`) in `app/retrieval.py`.
- Generation: OpenAI Chat Completions (default `gpt-4o-mini`) called via `httpx` with a grounding system prompt to keep answers tied to retrieved context.
- Auth: Local admin login with bcrypt hash saved to `/data/admin_hash.txt` and forced change when the default hash is detected; optional SSO providers (Google, Azure AD, Okta, Auth0, generic SAML) registered from `app/auth_providers/*` when env flags enable them.
- Persistence & files: `/data` volume stores the Chroma collection, uploaded source files (`/data/uploads`), and the admin hash; upload limits enforced before jobs are queued.

## How the app works
- Admin + embeddings: `/admin/login` guards `/embeddings`. Uploads are validated (per-file and total size), stored in `/data/uploads`, then a Celery job (`process_embeddings`) chunks text, OCRs image text, embeds all indexed content with the text embedding model, and writes vectors to Chroma. Redis DB 2 stores progress so the embeddings page can render a progress bar and status updates.
- Chat flow: `/chat` opens a WebSocket to `/ws/chat`. Messages trigger `answer_question`: fetch candidates from Chroma, optionally rerank, and send top context to OpenAI. Responses stream back to the browser. If no collection exists, the bot instructs the user to log in and build embeddings.
- Startup: `app/main.py` warms up text-embedding and rerank models on startup to avoid first-request latency and registers any enabled OAuth/SAML providers.

### LLM provider options (cloud vs on‑prem)
- `LLM_PROVIDER=openai` (default) uses OpenAI Chat Completions with `LLM_MODEL_OPENAI` (default `gpt-4o-mini`).
- `LLM_PROVIDER=local` uses an OpenAI-compatible local endpoint (e.g., Ollama or llama.cpp server) at `LOCAL_LLM_ENDPOINT` (default `http://localhost:11434/v1`; use `http://host.docker.internal:11434/v1` when the LLM runs on host and app runs in Docker).
  - Pick model size with `LOCAL_LLM_SIZE=small|large`.
    - `small` → `LOCAL_LLM_MODEL_SMALL` (default `llama3:8b-instruct-q4_0`).
    - `large` → `LOCAL_LLM_MODEL_LARGE` (default `llama3:70b-instruct`).
- Embeddings for QA are text-space only: `TEXT_EMBED_MODEL_CPU/GPU` selected by `EMBED_MODE`, regardless of LLM provider. Image files contribute via OCR text extraction.

## Configuration (.env)
Populate `.env` (defaults shown):

```env
# LLM selection
LLM_PROVIDER=openai                 # or local
LLM_MODEL_OPENAI=gpt-4o-mini
OPENAI_API_KEY=

# Local LLM (OpenAI-compatible, e.g., Ollama/llama.cpp server)
# If app runs in Docker and LLM runs on host, use http://host.docker.internal:11434/v1
LOCAL_LLM_ENDPOINT=http://localhost:11434/v1
LOCAL_LLM_SIZE=small               # small (Llama 3 8B Q4) or large (Llama 3 70B)
LOCAL_LLM_MODEL_SMALL=llama3:8b-instruct-q4_0
LOCAL_LLM_MODEL_LARGE=llama3:70b-instruct

# Embeddings
EMBED_STORE_PATH=/data/chroma_store
EMBED_MODE=cpu
TEXT_EMBED_MODEL_CPU=all-MiniLM-L6-v2
TEXT_EMBED_MODEL_GPU=all-mpnet-base-v2

# Retrieval
CHUNK_SIZE_TOKENS=1024
TOP_K_INITIAL=50
TOP_K_RERANKED=5
RERANK_ENABLED=true

# Upload limits
MAX_FILE_SIZE_MB=10
MAX_TOTAL_DOC_SIZE_MB=1024

# Admin & UI
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
ADMIN_PASSWORD_HASH=
CHATBOT_WELCOME_MSG="Hi, what is your query today?"

# Optional auth providers (set *_ENABLED=true to activate)
AUTH_GOOGLE_ENABLED=false
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
GOOGLE_ALLOWED_DOMAINS=

AUTH_AZURE_AD_ENABLED=false
AZURE_AD_TENANT_ID=
AZURE_AD_CLIENT_ID=
AZURE_AD_CLIENT_SECRET=
AZURE_AD_REDIRECT_URI=
AZURE_AD_ALLOWED_GROUPS=

AUTH_OKTA_ENABLED=false
OKTA_ISSUER=
OKTA_CLIENT_ID=
OKTA_CLIENT_SECRET=
OKTA_REDIRECT_URI=
OKTA_ALLOWED_GROUPS=

AUTH_AUTH0_ENABLED=false
AUTH0_DOMAIN=
AUTH0_CLIENT_ID=
AUTH0_CLIENT_SECRET=
AUTH0_REDIRECT_URI=
AUTH0_ALLOWED_EMAILS=

AUTH_SAML_ENABLED=false
SAML_METADATA_URL=
SAML_ENTITY_ID=
SAML_ASSERTION_CONSUMER=
SAML_ALLOWED_EMAILS=
```

- If `ADMIN_PASSWORD_HASH` (bcrypt) is set, it is used directly; otherwise `ADMIN_PASSWORD` is hashed into `/data/admin_hash.txt`. If the hash matches the default password, admins must change it before using `/embeddings`.
- Embeddings and admin hash persist under `./data` via the Compose volume; delete that directory to wipe state.

## Running with Docker Compose
1) Create `.env` with the values above.  
2) Build and start services:
```bash
docker compose up --build
```
Services: `app` (FastAPI), `worker` (Celery), `redis` (broker/storage). Port 8000 on the host maps to the app container; the shared `./data` volume keeps embeddings between runs.

Visit:
- Chat: http://localhost:8000/chat
- Admin login: http://localhost:8000/admin/login
- Change password: http://localhost:8000/admin/change-password
- Embeddings UI: http://localhost:8000/embeddings (admin only)

## Iterating quickly (code/config changes)
- Code changes only: rebuild app + worker and restart without touching data:
  ```bash
  docker compose build app worker
  docker compose up -d app worker
  ```
- Dependency or base image changes: add `--no-cache` to the build step.
- OCR support uses `tesseract-ocr` in the image; after dependency changes, rebuild app/worker images.
- Env/config changes: edit `.env`, then `docker compose up -d --build` to reload settings.
- Clearing stuck jobs: `docker compose restart redis` (keeps data) or `docker compose down -v` (wipes Chroma/uploads/admin hash; only if you want a clean slate).
- Logs: `docker compose logs -f app` and `docker compose logs -f worker`.

## Code map
- `app/main.py` — FastAPI app, routes, WebSocket chat handler, admin session handling, OAuth/SAML provider registration, model warm-up.
- `app/embeddings.py` — Upload handling, token-based chunking, OCR for image text, text embeddings, and Chroma collection operations.
- `app/retrieval.py` — Similarity search, optional cross-encoder rerank, and Chat Completions assembly (OpenAI or local OpenAI-compatible server).
- `app/tasks.py` — Celery task to build/reset the vector store with Redis-backed progress reporting.
- `app/celery_app.py` — Celery instance configured for Redis broker/backend.
- `app/templates/*` and `app/static/*` — Jinja2 views and static assets for chat/admin/embeddings pages.
