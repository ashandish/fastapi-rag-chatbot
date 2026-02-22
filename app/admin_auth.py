import os
import bcrypt
from fastapi import Request, HTTPException, Form
from fastapi.responses import RedirectResponse
from .models import settings, ADMIN_HASH_FILE

DEFAULT_PLAINTEXT = "Strongpassword123#"

def _ensure_hash_file():
    os.makedirs(os.path.dirname(ADMIN_HASH_FILE), exist_ok=True)
    if os.path.isfile(ADMIN_HASH_FILE):
        return
    env_hash = (settings.admin_password_hash or "").strip()
    if env_hash and env_hash.startswith("$2b$"):
        with open(ADMIN_HASH_FILE, "w", encoding="utf-8") as f:
            f.write(env_hash.strip())
        return
    raw = (settings.admin_password_plain or "").strip() or DEFAULT_PLAINTEXT
    hashed = bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    with open(ADMIN_HASH_FILE, "w", encoding="utf-8") as f:
        f.write(hashed)

def _read_hash() -> str:
    _ensure_hash_file()
    with open(ADMIN_HASH_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

def _write_hash(new_hash: str):
    with open(ADMIN_HASH_FILE, "w", encoding="utf-8") as f:
        f.write(new_hash.strip())

def verify_password(plain: str) -> bool:
    saved = _read_hash().encode("utf-8")
    return bcrypt.checkpw(plain.encode("utf-8"), saved)

def is_default_password() -> bool:
    saved = _read_hash().encode("utf-8")
    try:
        return bcrypt.checkpw(DEFAULT_PLAINTEXT.encode("utf-8"), saved)
    except Exception:
        return False

def set_new_password(new_plain: str):
    new_hash = bcrypt.hashpw(new_plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    _write_hash(new_hash)

def is_admin(request: Request) -> bool:
    return bool(request.session.get("is_admin") is True)

async def require_admin(request: Request):
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Forbidden")

async def admin_login_get(request, templates):
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": None})

async def admin_login_post(request, templates, username: str = Form(...), password: str = Form(...)):
    if username == settings.admin_username and verify_password(password):
        request.session["is_admin"] = True
        if is_default_password():
            request.session["must_change"] = True
            return RedirectResponse(url="/admin/change-password?notice=default", status_code=303)
        else:
            request.session["must_change"] = False
            return RedirectResponse(url="/embeddings", status_code=303)
    else:
        return templates.TemplateResponse("admin_login.html", {"request": request, "error": "Invalid credentials"})

async def admin_logout(request: Request):
    request.session.pop("is_admin", None)
    request.session.pop("must_change", None)
    request.session.pop("user", None)
    return RedirectResponse(url="/", status_code=303)

async def change_password_get(request, templates):
    notice = None
    if request.query_params.get("notice") == "default":
        notice = "You are using the default password. Please change it before proceeding."
    return templates.TemplateResponse(
        "change_password.html",
        {"request": request, "error": None, "ok": None, "notice": notice}
    )

async def change_password_post(request, templates,
                               old_password: str = Form(...),
                               new_password: str = Form(...),
                               confirm_password: str = Form(...)):
    if not verify_password(old_password):
        return templates.TemplateResponse(
            "change_password.html",
            {"request": request, "error": "Old password is incorrect", "ok": None, "notice": None}
        )
    if new_password != confirm_password:
        return templates.TemplateResponse(
            "change_password.html",
            {"request": request, "error": "New passwords do not match", "ok": None, "notice": None}
        )
    if len(new_password) < 8:
        return templates.TemplateResponse(
            "change_password.html",
            {"request": request, "error": "New password must be at least 8 characters", "ok": None, "notice": None}
        )
    set_new_password(new_password)
    request.session["must_change"] = False
    return templates.TemplateResponse(
        "change_password.html",
        {"request": request, "error": None, "ok": "Password updated successfully. You can now access Embeddings.", "notice": None}
    )
