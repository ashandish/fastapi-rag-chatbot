import os, re, uuid, redis
from typing import List
from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .models import settings, UPLOAD_DIR
from .embeddings import save_upload, get_text_embedder, collection_size
from .retrieval import answer_question, get_reranker
from .auth import configure_oauth, oauth
from .admin_auth import (
    require_admin,
    admin_login_get,
    admin_login_post,
    admin_logout,
    is_admin,
    change_password_get,
    change_password_post,
    is_default_password,
)
from .tasks import process_embeddings
from .auth_providers.google import register_google
from .auth_providers.azure_ad import register_aad
from .auth_providers.okta import register_okta
from .auth_providers.auth0 import register_auth0
from .auth_providers.saml import register_saml

app = FastAPI(title="RAG Chatbot v11 — Multi-Auth")
SYSTEM_LOGS_DIR = os.path.join(os.path.dirname(settings.embed_store_path), "system_logs")
SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")

def _build_index_status() -> dict:
    count = collection_size()
    is_built = count > 0
    return {
        "is_built": is_built,
        "count": count,
        "message": f"Embeddings are built ({count} chunk{'s' if count != 1 else ''} indexed)." if is_built else "Embeddings are not built yet.",
    }

def _ensure_system_logs_dir() -> None:
    os.makedirs(SYSTEM_LOGS_DIR, exist_ok=True)

def _is_safe_name(value: str) -> bool:
    return bool(SAFE_NAME_RE.fullmatch(value))

def _list_components() -> list[str]:
    _ensure_system_logs_dir()
    out = []
    for name in sorted(os.listdir(SYSTEM_LOGS_DIR)):
        p = os.path.join(SYSTEM_LOGS_DIR, name)
        if os.path.isdir(p) and _is_safe_name(name):
            out.append(name)
    return out

def _list_log_files(component: str) -> list[str]:
    comp_dir = os.path.join(SYSTEM_LOGS_DIR, component)
    if not os.path.isdir(comp_dir):
        return []
    out = []
    for name in sorted(os.listdir(comp_dir)):
        p = os.path.join(comp_dir, name)
        if os.path.isfile(p) and _is_safe_name(name):
            out.append(name)
    return out

def _tail_lines(path: str, lines: int) -> str:
    # Read only tail bytes to keep request time bounded for large log files.
    max_bytes = 1_000_000
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        start = max(0, size - max_bytes)
        f.seek(start)
        data = f.read().decode("utf-8", errors="replace")
    parts = data.splitlines()
    return "\n".join(parts[-lines:])

# Preload heavy models when the app boots so first requests do not time out.
@app.on_event("startup")
async def warm_up_models():
    try:
        get_text_embedder()
        if settings.rerank_enabled:
            get_reranker()
    except Exception as exc:
        print(f"[warmup] Model warm-up failed: {exc}")

# Static & templates
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Sessions + OAuth
configure_oauth(app)
app.state.oauth = oauth  # for provider modules

# Register optional auth provider routes
google_router = register_google(oauth)
if google_router:
    app.include_router(google_router)

aad_router = register_aad(oauth)
if aad_router:
    app.include_router(aad_router)

okta_router = register_okta(oauth)
if okta_router:
    app.include_router(okta_router)

auth0_router = register_auth0(oauth)
if auth0_router:
    app.include_router(auth0_router)

saml_router = register_saml()
if saml_router:
    app.include_router(saml_router)

# Redis for progress
r = redis.Redis(host="redis", port=6379, db=2, decode_responses=True)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "layout.html",
        {
            "request": request,
            "is_admin": is_admin(request),
            "index_status": _build_index_status(),
        },
    )

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_form(request: Request):
    return await admin_login_get(request, templates)

@app.post("/admin/login", response_class=HTMLResponse)
async def admin_login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    return await admin_login_post(request, templates, username, password)

@app.get("/admin/logout")
async def admin_logout_route(request: Request):
    return await admin_logout(request)

@app.get("/admin/change-password", response_class=HTMLResponse)
async def admin_change_password_form(request: Request, _: None = Depends(require_admin)):
    return await change_password_get(request, templates)

@app.post("/admin/change-password", response_class=HTMLResponse)
async def admin_change_password_submit(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    _: None = Depends(require_admin),
):
    return await change_password_post(request, templates, old_password, new_password, confirm_password)

@app.get("/embeddings", response_class=HTMLResponse)
async def embeddings_get(request: Request, _: None = Depends(require_admin)):
    if request.session.get("must_change") or is_default_password():
        return RedirectResponse(url="/admin/change-password?notice=default", status_code=303)
    return templates.TemplateResponse(
        "embeddings.html",
        {"request": request, "is_admin": True, "index_status": _build_index_status()},
    )

@app.get("/admin/system-logs", response_class=HTMLResponse)
async def admin_system_logs(
    request: Request,
    component: str = Query(default=""),
    log_file: str = Query(default=""),
    _: None = Depends(require_admin),
):
    if request.session.get("must_change") or is_default_password():
        return RedirectResponse(url="/admin/change-password?notice=default", status_code=303)
    components = _list_components()
    selected_component = component.strip()
    if selected_component not in components:
        selected_component = components[0] if components else ""
    files = _list_log_files(selected_component) if selected_component else []
    selected_file = log_file.strip()
    if selected_file not in files:
        selected_file = files[0] if files else ""
    return templates.TemplateResponse(
        "system_logs.html",
        {
            "request": request,
            "is_admin": True,
            "components": components,
            "selected_component": selected_component,
            "files": files,
            "selected_file": selected_file,
        },
    )

@app.get("/admin/system-logs/api/components")
async def admin_system_log_components(_: None = Depends(require_admin)):
    return {"components": _list_components()}

@app.get("/admin/system-logs/api/files")
async def admin_system_log_files(
    component: str = Query(...),
    _: None = Depends(require_admin),
):
    comp = component.strip()
    if not _is_safe_name(comp):
        return JSONResponse({"error": "Invalid component"}, status_code=400)
    return {"component": comp, "files": _list_log_files(comp)}

@app.get("/admin/system-logs/api/tail")
async def admin_system_log_tail(
    component: str = Query(...),
    log_file: str = Query(...),
    lines: int = Query(default=300, ge=50, le=5000),
    _: None = Depends(require_admin),
):
    comp = component.strip()
    fname = log_file.strip()
    if not _is_safe_name(comp) or not _is_safe_name(fname):
        return JSONResponse({"error": "Invalid path"}, status_code=400)
    path = os.path.join(SYSTEM_LOGS_DIR, comp, fname)
    if not os.path.isfile(path):
        return JSONResponse({"error": "Log file not found"}, status_code=404)
    try:
        text = _tail_lines(path, lines)
        stat = os.stat(path)
        return {
            "component": comp,
            "log_file": fname,
            "lines": lines,
            "content": text,
            "size_bytes": stat.st_size,
            "updated_at": int(stat.st_mtime),
        }
    except Exception as exc:
        return JSONResponse({"error": f"Failed to read log file: {exc}"}, status_code=500)

@app.post("/embeddings/process")
async def embeddings_process(
    request: Request,
    action: str = Form("add"),
    files: List[UploadFile] = File(default=None),
    _: None = Depends(require_admin),
):
    if request.session.get("must_change") or is_default_password():
        return JSONResponse(
            {"status": "error", "message": "Password change required before using embeddings."},
            status_code=403,
        )

    if action not in {"clean", "add"}:
        return JSONResponse({"status": "error", "message": "Invalid action"}, status_code=400)
    if not files:
        return JSONResponse({"status": "error", "message": "No files provided"}, status_code=400)

    max_file = int(settings.max_file_size_mb) * 1024 * 1024
    max_total = int(settings.max_total_doc_size_mb) * 1024 * 1024

    # ✅ safe file size computation (no seek whence=END)
    total_upload_size = 0
    for f in files:
        content = await f.read()
        size = len(content)
        await f.seek(0)

        if size > max_file:
            return JSONResponse(
                {"status": "error", "message": f"{f.filename} exceeds {settings.max_file_size_mb} MB"},
                status_code=400,
            )
        total_upload_size += size

    existing_size = 0
    if os.path.isdir(UPLOAD_DIR):
        for name in os.listdir(UPLOAD_DIR):
            p = os.path.join(UPLOAD_DIR, name)
            if os.path.isfile(p):
                existing_size += os.path.getsize(p)

    if existing_size + total_upload_size > max_total:
        return JSONResponse(
            {
                "status": "error",
                "message": f"Total upload size limit ({settings.max_total_doc_size_mb} MB) exceeded",
            },
            status_code=400,
        )

    saved_paths = []
    for f in files:
        content = await f.read()
        path = save_upload(content, f.filename)
        saved_paths.append(path)

    job_id = str(uuid.uuid4())
    r.set(f"job:{job_id}:progress", 0)
    r.set(f"job:{job_id}:status", "queued")
    r.set(f"job:{job_id}:detail", "Queued")

    task = process_embeddings.delay(job_id, saved_paths, action)
    r.set(f"job:{job_id}:task_id", task.id)

    return JSONResponse(
        {"status": "queued", "job_id": job_id, "message": f"Embedding job started for {len(saved_paths)} files."}
    )



@app.get("/embeddings/progress/{job_id}")
async def embeddings_progress(job_id: str, request: Request, _: None = Depends(require_admin)):
    progress = int(r.get(f"job:{job_id}:progress") or 0)
    status = r.get(f"job:{job_id}:status") or "unknown"
    detail = r.get(f"job:{job_id}:detail") or ""
    return {"job_id": job_id, "progress": progress, "status": status, "detail": detail}

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "is_admin": is_admin(request),
            "welcome": settings.chatbot_welcome_msg,
            "index_status": _build_index_status(),
        },
    )

@app.websocket("/ws/chat")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_text()
            reply = answer_question(data)
            await ws.send_text(reply)
    except WebSocketDisconnect:
        pass
