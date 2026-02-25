import os, uuid, redis
from typing import List
from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .models import settings, UPLOAD_DIR
from .embeddings import save_upload, get_text_embedder
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
    return templates.TemplateResponse("layout.html", {"request": request, "is_admin": is_admin(request)})

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
    return templates.TemplateResponse("embeddings.html", {"request": request, "is_admin": True})

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
        {"request": request, "is_admin": is_admin(request), "welcome": settings.chatbot_welcome_msg},
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
