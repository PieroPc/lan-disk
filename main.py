"""
局域网云盘 · FastAPI 后端

启动： python main.py
访问： http://<本机IP>:8088

环境变量（可选）：
  LAN_DISK_PORT      端口，默认 8088
  LAN_DISK_PASSWORD  访问口令，设置后需要登录
  LAN_DISK_ROOT      存储根目录，默认 ./storage
  LAN_DISK_NOTES     笔记目录，默认 ./notes
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import mimetypes
import os
import platform
import re
import shutil
import socket
import sys
import tempfile
import time
import zipfile
from contextlib import asynccontextmanager
from urllib.parse import quote
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

import archives
import audiotag
import journal
import notes
import office
import remarks
import shares

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def _arg(flag: str, env: str, default: str = "") -> str:
    """同时支持命令行 --flag value 与环境变量。"""
    argv = sys.argv[1:]
    if flag in argv:
        idx = argv.index(flag)
        if idx + 1 < len(argv):
            return argv[idx + 1]
    return os.environ.get(env, default)


STORE_RAW = _arg("--root", "LAN_DISK_ROOT", "")
STORAGE = Path(STORE_RAW).expanduser().resolve() if STORE_RAW else (BASE_DIR / "storage")
STORAGE.mkdir(parents=True, exist_ok=True)

PORT = int(_arg("--port", "LAN_DISK_PORT", "8088") or 8088)
PASSWORD = _arg("--password", "LAN_DISK_PASSWORD", "").strip()
SECURITY_FILE = BASE_DIR / "security.json"


def _load_security():
    """UI 里设置过口令后，security.json 就是唯一真相；没设置过则沿用启动参数。"""
    try:
        d = json.loads(SECURITY_FILE.read_text(encoding="utf-8"))
        return bool(d.get("enabled")), str(d.get("password", ""))
    except (OSError, ValueError):
        return None


_AUTH = _load_security()
AUTH_ON = bool(PASSWORD) if _AUTH is None else _AUTH[0]
if _AUTH is not None:
    PASSWORD = _AUTH[1]

NOTES_RAW = _arg("--notes", "LAN_DISK_NOTES", "")
NOTES_DIR = Path(NOTES_RAW).expanduser().resolve() if NOTES_RAW else (BASE_DIR / "notes")
notes_store = notes.Store(NOTES_DIR)

SHARES = shares.Store(BASE_DIR / "shares.json")
REMARKS = remarks.Remarks(BASE_DIR / "remarks.json")

APP_NAME = "局域网云盘"
APP_VERSION = "1.11.0"
STARTED_AT = time.time()

activity = journal.Journal(BASE_DIR / "logs")
activity.record("system.boot", "ok", f"{APP_NAME} v{APP_VERSION} 已启动",
                detail=f"端口 {PORT} · 存储 {STORAGE}")


@asynccontextmanager
async def lifespan(_app):  # noqa: ANN001
    yield
    activity.record("system.stop", "info", "服务已停止",
                    detail=f"本次运行 {int(time.time() - STARTED_AT)} 秒")


CHUNK = 1024 * 1024
MAX_TEXT_PREVIEW = 512 * 1024  # 文本预览上限 512KB
MAX_NOTE_CHARS = 512 * 1024  # 单篇笔记正文上限
MAX_NOTE_MEDIA = 20 * 1024 * 1024  # 笔记图片上限 20MB
MAX_OFFICE_PARSE = 60 * 1024 * 1024  # Office 在线解析上限 60MB
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico", ".avif"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}
TEXT_EXT = {
    ".txt", ".md", ".json", ".js", ".ts", ".py", ".html", ".css", ".yml", ".yaml",
    ".toml", ".ini", ".conf", ".log", ".csv", ".xml", ".sh", ".bat", ".java", ".c",
    ".cpp", ".go", ".rs", ".sql", ".tsx", ".jsx", ".vue", ".env", ".gitignore",
}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}
DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".wps", ".et", ".dps"}
OFFICE_EXT = {".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm"}
LEGACY_OFFICE_EXT = {".doc", ".xls", ".ppt", ".wps", ".et", ".dps"}
OFFICE_KIND = {
    ".docx": "word", ".docm": "word",
    ".xlsx": "excel", ".xlsm": "excel",
    ".pptx": "ppt", ".pptm": "ppt",
}
AUDIOTAG_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"}
BAD_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')

app = FastAPI(title="局域网云盘", docs_url=None, redoc_url=None, lifespan=lifespan)


# ---------------------------------------------------------------- 日志埋点

def client_ip(request: Optional[Request]) -> str:
    """局域网里取真实来源 IP（可能有反向代理）。"""
    if request is None:
        return ""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def log(request: Optional[Request], action: str, level: str = "info",
        message: str = "", detail: str = "") -> None:
    activity.record(action, level, message, detail, client_ip(request))



# ---------------------------------------------------------------- 工具函数

def resolve(rel: str) -> Path:
    """把 API 传进来的相对路径映射成磁盘绝对路径，并拦截目录穿越。"""
    rel = (rel or "").replace("\\", "/").strip()
    parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
    target = (STORAGE / Path(*parts)).resolve() if parts else STORAGE
    if target != STORAGE and STORAGE not in target.parents:
        raise HTTPException(status_code=400, detail="非法路径")
    return target


def rel_of(path: Path) -> str:
    p = path.resolve()
    if p == STORAGE:
        return ""
    try:
        return p.relative_to(STORAGE).as_posix()
    except ValueError:
        return ""


def clean_name(name: str) -> str:
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    name = BAD_CHARS.sub("_", name).strip(" .")
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    if len(name) > 200:
        raise HTTPException(status_code=400, detail="名称过长")
    return name


def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    i = 1
    while True:
        candidate = p.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def kind_of(path: Path) -> str:
    if path.is_dir():
        return "folder"
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext == ".pdf":
        return "pdf"
    if ext in (".md", ".markdown"):
        return "markdown"
    if ext in (".html", ".htm"):
        return "html"
    if ext in (".csv", ".tsv"):
        return "table"
    if ext in OFFICE_KIND:
        return OFFICE_KIND[ext]
    if ext in LEGACY_OFFICE_EXT:
        return "legacy"
    if ext in TEXT_EXT:
        return "text"
    if ext in ARCHIVE_EXT:
        return "archive"
    if ext in DOC_EXT:
        return "doc"
    return "file"


def item_of(path: Path) -> dict:
    st = path.stat()
    return {
        "name": path.name,
        "path": rel_of(path),
        "is_dir": path.is_dir(),
        "kind": kind_of(path),
        "size": 0 if path.is_dir() else st.st_size,
        "mtime": int(st.st_mtime),
        "ext": path.suffix.lower().lstrip("."),
        "remark": REMARKS.get(rel_of(path)),
    }


def folder_size(path: Path, budget: float = 1.5) -> int:
    """限制耗时的目录大小统计。"""
    total, start = 0, time.time()
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
        if time.time() - start > budget:
            break
    return total


def fmt_bytes(n: float) -> str:
    """日志里给人看的体积，例如 1.6 MB。"""
    v = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            return f"{v:.0f} {unit}" if unit == "B" else f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} TB"


# ---------------------------------------------------------------- 简单登录

def issue_token() -> str:
    secret = hashlib.sha256(f"lan-disk::{PASSWORD}::{STORAGE}".encode()).hexdigest().encode()
    return hmac.new(secret, b"session-v1", hashlib.sha256).hexdigest()


def set_auth(enabled: bool, password: str) -> None:
    """运行时开关口令；security.json 原子落盘，重启后依然生效。"""
    global AUTH_ON, PASSWORD
    AUTH_ON = enabled
    PASSWORD = password
    tmp = SECURITY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"enabled": enabled, "password": password}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, SECURITY_FILE)


def authed(request: Request) -> bool:
    if not AUTH_ON or not PASSWORD:
        return True
    return hmac.compare_digest(request.cookies.get("lan_disk_token", ""), issue_token())


def require_auth(request: Request) -> None:
    if not authed(request):
        raise HTTPException(status_code=401, detail="需要登录")


@app.exception_handler(401)
async def _401(request: Request, exc):  # noqa: ANN001
    return JSONResponse({"detail": "需要登录"}, status_code=401)


@app.get("/api/session")
async def session(request: Request):
    return {"auth_required": AUTH_ON, "logged_in": authed(request)}


@app.post("/api/login")
async def login(request: Request, payload: dict):
    if AUTH_ON and not hmac.compare_digest(str(payload.get("password", "")), PASSWORD):
        log(request, "auth.fail", "warn", "口令错误，登录被拒绝")
        raise HTTPException(status_code=403, detail="口令错误")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        "lan_disk_token", issue_token(), max_age=60 * 60 * 24 * 30,
        httponly=True, samesite="lax",
    )
    if AUTH_ON:
        log(request, "auth.login", "ok", "登录成功")
    return resp


@app.get("/api/security")
async def security_get(request: Request):
    require_auth(request)
    return {"enabled": AUTH_ON, "has_password": bool(PASSWORD)}


@app.post("/api/security")
async def security_set(request: Request, payload: dict):
    """运行时开关口令登录；改完本浏览器保持登录，其他设备需重新登录。"""
    require_auth(request)
    enabled = bool(payload.get("enabled"))
    pwd = str(payload.get("password", "")).strip()
    if enabled and not pwd:
        raise HTTPException(status_code=400, detail="开启前请先设置口令")
    if len(pwd) > 128:
        raise HTTPException(status_code=400, detail="口令太长（最多 128 字符）")
    old_on = AUTH_ON
    new_pwd = pwd if (enabled and pwd) else PASSWORD
    set_auth(enabled, new_pwd)
    if enabled and not old_on:
        log(request, "auth.set", "warn", "已开启口令登录，局域网内其他设备需重新登录")
    elif enabled and pwd:
        log(request, "auth.set", "warn", "访问口令已修改，其他设备需用新口令重新登录")
    elif not enabled:
        log(request, "auth.set", "info", "已关闭口令登录，局域网内可直接访问")
    resp = JSONResponse({"ok": True, "enabled": enabled})
    if enabled:
        # 当前浏览器直接换发新凭证，自己不用再输一遍
        resp.set_cookie("lan_disk_token", issue_token(), max_age=60 * 60 * 24 * 30,
                        httponly=True, samesite="lax")
    return resp


@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("lan_disk_token")
    return resp


# ---------------------------------------------------------------- 浏览接口

@app.get("/api/list")
async def list_dir(request: Request, path: str = "", sort: str = "name", order: str = "asc"):
    require_auth(request)
    target = resolve(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="目录不存在")
    if target.is_file():
        raise HTTPException(status_code=400, detail="不是目录")

    items = []
    with os.scandir(target) as it:
        entries = list(it)
    for entry in entries:
        if entry.name.endswith(".part"):
            continue
        try:
            items.append(item_of(Path(entry.path)))
        except OSError:
            continue

    reverse = order == "desc"
    if sort == "size":
        items.sort(key=lambda x: (x["is_dir"], x["size"]), reverse=reverse)
        if not reverse:
            items.sort(key=lambda x: not x["is_dir"])
    elif sort == "mtime":
        items.sort(key=lambda x: (x["is_dir"], x["mtime"]), reverse=reverse)
    else:
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()), reverse=reverse)

    rel = rel_of(target)
    crumbs = [{"name": "全部文件", "path": ""}]
    if rel:
        acc = []
        for part in rel.split("/"):
            acc.append(part)
            crumbs.append({"name": part, "path": "/".join(acc)})

    parent = None
    if rel:
        parent = "/".join(rel.split("/")[:-1])

    return {
        "path": rel,
        "parent": parent,
        "crumbs": crumbs,
        "items": items,
        "count": len(items),
    }


@app.get("/api/search")
async def search(request: Request, q: str = "", limit: int = 300):
    require_auth(request)
    q = (q or "").strip().lower()
    if not q:
        return {"items": []}
    results = []
    start = time.time()
    for root, dirs, files in os.walk(STORAGE):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in dirs + files:
            if q in name.lower():
                try:
                    results.append(item_of(Path(root) / name))
                except OSError:
                    pass
                if len(results) >= limit:
                    return {"items": results, "truncated": True}
        if time.time() - start > 8:
            return {"items": results, "truncated": True}
    return {"items": results, "truncated": False}


@app.get("/api/browse")
async def browse(request: Request, kind: str = "recent", limit: int = 240):
    """侧边栏分类视图：最近 / 图片 / 视频 / 音乐 / 文档。"""
    require_auth(request)
    groups = {
        "image": IMAGE_EXT,
        "video": VIDEO_EXT,
        "audio": AUDIO_EXT,
        "doc": DOC_EXT | TEXT_EXT,
    }
    exts = groups.get(kind)
    found = []
    start = time.time()
    for root, dirs, files in os.walk(STORAGE):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if exts is not None and Path(name).suffix.lower() not in exts:
                continue
            full = Path(root) / name
            try:
                st = full.stat()
            except OSError:
                continue
            found.append({
                "name": name,
                "path": rel_of(full),
                "is_dir": False,
                "kind": kind_of(full),
                "size": st.st_size,
                "mtime": int(st.st_mtime),
                "ext": full.suffix.lower().lstrip("."),
            })
        if time.time() - start > 6:
            break
    found.sort(key=lambda x: x["mtime"], reverse=True)
    return {"items": found[:limit], "total": len(found), "kind": kind}


@app.get("/api/tree")
async def tree(request: Request, max_nodes: int = 500):
    """返回全部文件夹树，供「移动到」选择目标目录。"""
    require_auth(request)
    counter = {"n": 0}

    def build(p: Path, depth: int) -> list:
        if depth <= 0 or counter["n"] >= max_nodes:
            return []
        try:
            with os.scandir(p) as it:
                dirs = sorted((e for e in it if e.is_dir()), key=lambda e: e.name.lower())
        except OSError:
            return []
        out = []
        for entry in dirs:
            if entry.name.startswith("."):
                continue
            counter["n"] += 1
            if counter["n"] > max_nodes:
                break
            out.append({
                "name": entry.name,
                "path": rel_of(Path(entry.path)),
                "children": build(Path(entry.path), depth - 1),
            })
        return out

    return {"children": build(STORAGE, 8), "truncated": counter["n"] >= max_nodes}


@app.get("/api/stats")
async def stats(request: Request, path: str = ""):
    require_auth(request)
    target = resolve(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="路径不存在")
    if target.is_dir():
        used = folder_size(target)
        count = sum(len(f) for _r, _d, f in os.walk(target))
    else:
        used, count = target.stat().st_size, 1
    du = shutil.disk_usage(STORAGE)
    return {
        "size": used,
        "count": count,
        "disk_total": du.total,
        "disk_free": du.free,
        "root": str(STORAGE),
    }


# ---------------------------------------------------------------- 写操作

@app.post("/api/mkdir")
async def mkdir(request: Request, payload: dict):
    require_auth(request)
    parent = resolve(payload.get("path", ""))
    if not parent.is_dir():
        raise HTTPException(status_code=400, detail="父目录不存在")
    dest = unique_path(parent / clean_name(payload.get("name", "")))
    dest.mkdir(parents=True, exist_ok=False)
    log(request, "mkdir", "ok", f"新建文件夹「{dest.name}」", detail=f"位置 {rel_of(parent) or '根目录'}")
    return {"ok": True, "item": item_of(dest)}


@app.post("/api/upload")
async def upload(request: Request, path: str = Form(""), files: List[UploadFile] = File(...)):
    require_auth(request)
    target_dir = resolve(path)
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="目标目录不存在")

    saved = []
    for f in files:
        raw = (f.filename or "未命名").replace("\\", "/").split("/")[-1]
        try:
            name = clean_name(raw)
        except HTTPException:
            name = "未命名"
        dest = unique_path(target_dir / name)
        tmp = dest.with_name(dest.name + ".part")
        with open(tmp, "wb") as out:
            while True:
                chunk = await f.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
        os.replace(tmp, dest)
        saved.append(item_of(dest))
        await f.close()

    if saved:
        names = "、".join(i["name"] for i in saved[:3]) + ("…" if len(saved) > 3 else "")
        total = sum(i["size"] for i in saved)
        log(request, "upload", "ok",
            f"上传 {len(saved)} 个文件到 {rel_of(target_dir) or '根目录'}",
            detail=f"{names} · 共 {fmt_bytes(total)}")
    return {"ok": True, "items": saved}


@app.post("/api/rename")
async def rename(request: Request, payload: dict):
    require_auth(request)
    src = resolve(payload.get("path", ""))
    if not src.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if src == STORAGE:
        raise HTTPException(status_code=400, detail="不能重命名根目录")
    new_name = clean_name(payload.get("new_name", ""))
    dest = src.with_name(new_name)
    if dest.exists() and dest != src:
        raise HTTPException(status_code=409, detail="同名文件已存在")
    src.rename(dest)
    REMARKS.move_prefix(rel_of(src), rel_of(dest))
    log(request, "rename", "ok", f"重命名「{src.name}」→「{dest.name}」",
        detail=f"位置 {rel_of(dest.parent) or '根目录'}")
    return {"ok": True, "item": item_of(dest)}


@app.post("/api/move")
async def move(request: Request, payload: dict):
    require_auth(request)
    paths = payload.get("paths") or []
    dest_dir = resolve(payload.get("dest", ""))
    if not dest_dir.is_dir():
        raise HTTPException(status_code=400, detail="目标目录不存在")
    moved = []
    for p in paths:
        src = resolve(p)
        if not src.exists() or src == STORAGE:
            continue
        if dest_dir == src or src in dest_dir.parents:
            continue  # 不能移动到自己或子目录
        dest = unique_path(dest_dir / src.name)
        shutil.move(str(src), str(dest))
        REMARKS.move_prefix(rel_of(src), rel_of(dest))
        moved.append(item_of(dest))
    if moved:
        log(request, "move", "ok",
            f"移动 {len(moved)} 项到 {rel_of(dest_dir) or '根目录'}",
            detail="、".join(i["name"] for i in moved[:3]) + ("…" if len(moved) > 3 else ""))
    return {"ok": True, "items": moved}


@app.post("/api/delete")
async def delete(request: Request, payload: dict):
    require_auth(request)
    paths = payload.get("paths") or []
    removed = 0
    gone = []
    for p in paths:
        target = resolve(p)
        if target == STORAGE or not target.exists():
            continue
        info = {"name": target.name, "dir": target.is_dir(), "size": 0}
        if info["dir"]:
            info["size"] = folder_size(target, budget=0.3)
        else:
            try:
                info["size"] = target.stat().st_size
            except OSError:
                pass
        gone.append(info)
        REMARKS.delete_prefix(rel_of(target))
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            try:
                target.unlink()
            except OSError:
                pass
        removed += 1
    if gone:
        brief = "、".join(g["name"] + ("（文件夹）" if g["dir"] else "") for g in gone[:3])
        if len(gone) > 3:
            brief += f" 等 {len(gone)} 项"
        total = sum(g["size"] for g in gone)
        log(request, "delete", "warn", f"删除 {removed} 项", detail=f"{brief} · 释放 {fmt_bytes(total)}")
    return {"ok": True, "removed": removed}


@app.post("/api/copy")
async def copy(request: Request, payload: dict):
    require_auth(request)
    paths = payload.get("paths") or []
    dest_dir = resolve(payload.get("dest", ""))
    if not dest_dir.is_dir():
        raise HTTPException(status_code=400, detail="目标目录不存在")
    out = []
    for p in paths:
        src = resolve(p)
        if not src.exists():
            continue
        dest = unique_path(dest_dir / src.name)
        if src.is_dir():
            if dest_dir == src or src in dest_dir.parents:
                continue
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        out.append(item_of(dest))
    if out:
        log(request, "copy", "ok", f"复制 {len(out)} 项到 {rel_of(dest_dir) or '根目录'}",
            detail="、".join(i["name"] for i in out[:3]) + ("…" if len(out) > 3 else ""))
    return {"ok": True, "items": out}


# ---------------------------------------------------------------- 读取接口

def serve_file(path: Path, inline: bool, filename: Optional[str] = None, request: Optional[Request] = None):
    """支持 HTTP Range 的文件响应（视频拖动进度条必需）。"""
    if not path.exists() or path.is_dir():
        raise HTTPException(status_code=404, detail="文件不存在")

    size = path.stat().st_size
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if media_type.startswith("text/") or media_type in ("application/javascript", "application/json"):
        media_type += "; charset=utf-8"

    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=60"}
    if filename:
        headers["Content-Disposition"] = (
            f"{'inline' if inline else 'attachment'}; filename*=UTF-8''"
            + quote(filename)
        )

    range_header = request.headers.get("range") if request else None
    if range_header and range_header.startswith("bytes="):
        try:
            start_s, _, end_s = range_header[6:].partition("-")
            if start_s:
                start = int(start_s)
                end = int(end_s) if end_s else size - 1
            else:  # bytes=-500 取末尾
                length = int(end_s or 0)
                start, end = max(0, size - length), size - 1
            end = min(end, size - 1)
            if start > end or start >= size:
                raise ValueError
        except ValueError:
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{size}"},
            )

        length = end - start + 1

        def iter_range():
            with open(path, "rb") as fh:
                fh.seek(start)
                left = length
                while left > 0:
                    chunk = fh.read(min(CHUNK, left))
                    if not chunk:
                        break
                    left -= len(chunk)
                    yield chunk

        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(length)
        return StreamingResponse(iter_range(), status_code=206, media_type=media_type, headers=headers)

    def iter_all():
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(CHUNK)
                if not chunk:
                    break
                yield chunk

    headers["Content-Length"] = str(size)
    return StreamingResponse(iter_all(), media_type=media_type, headers=headers)


@app.get("/api/raw")
async def raw(request: Request, path: str = "", dl: int = 0):
    require_auth(request)
    target = resolve(path)
    return serve_file(target, inline=not dl, filename=target.name, request=request)


@app.get("/files/{full_path:path}")
async def files_route(request: Request, full_path: str):
    """按真实目录结构提供文件，用于 HTML 预览时相对路径（css/js/图片）能正确解析。"""
    require_auth(request)
    target = resolve(full_path)
    if target.is_dir():
        raise HTTPException(status_code=404, detail="不是文件")
    return serve_file(target, inline=True, request=request)


@app.get("/api/download")
async def download(request: Request, path: str = ""):
    require_auth(request)
    target = resolve(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if target.is_dir():
        return await zip_folder(request, path)
    try:
        size = target.stat().st_size
    except OSError:
        size = 0
    log(request, "download", "info", f"下载「{target.name}」", detail=fmt_bytes(size))
    return serve_file(target, inline=False, filename=target.name, request=request)


def make_zip(targets: List[Path], arc_root: str = "") -> Path:
    """把若干文件/目录打进临时 zip，返回临时文件路径（调用方负责清理）。"""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    tmp_path = Path(tmp.name)
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for target in targets:
            if target.is_file():
                zf.write(target, target.name)
            elif target.is_dir():
                base = target.name
                for root, _dirs, files in os.walk(target):
                    for f in files:
                        full = Path(root) / f
                        try:
                            zf.write(full, Path(base) / full.relative_to(target))
                        except OSError:
                            pass
    return tmp_path


def zip_response(tmp_path: Path, name: str):
    from starlette.background import BackgroundTask

    def cleanup():
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    headers = {
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(f"{name}.zip"),
        "Content-Length": str(tmp_path.stat().st_size),
    }
    return FileResponse(tmp_path, media_type="application/zip", headers=headers,
                        background=BackgroundTask(cleanup))


@app.get("/api/zip")
async def zip_folder(request: Request, path: str = ""):
    require_auth(request)
    target = resolve(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="路径不存在")
    name = target.name if target.is_dir() else target.stem
    log(request, "zip", "info", f"打包下载「{name}」",
        detail=f"位置 {rel_of(target) or '根目录'}")
    return zip_response(make_zip([target]), name or "storage")


@app.post("/api/zip_many")
async def zip_many(request: Request, payload: dict):
    """多选打包下载。"""
    require_auth(request)
    paths = payload.get("paths") or []
    targets = [resolve(p) for p in paths]
    targets = [t for t in targets if t.exists()]
    if not targets:
        raise HTTPException(status_code=400, detail="没有可打包的文件")
    if len(targets) == 1:
        t = targets[0]
        log(request, "zip", "info", f"打包下载「{t.name}」", detail="多选打包")
        return zip_response(make_zip([t]), t.name if t.is_dir() else t.stem)
    log(request, "zip", "info", f"打包下载 {len(targets)} 项", detail="多选打包")
    return zip_response(make_zip(targets), f"云盘文件_{time.strftime('%Y%m%d_%H%M')}")


# ---------------------------------------------------------------- 分享链接

INLINE_MIME_PREFIX = ("image/", "video/", "audio/", "text/")
INLINE_MIME_EXACT = {"application/pdf", "application/json"}


def share_base(request: Optional[Request] = None) -> str:
    """给局域网里其他人用的地址前缀：优先本机 192.168 网段，取不到才退回请求 host。"""
    for ip in lan_ips():
        if ip and not ip.startswith("169.254."):
            return f"http://{ip}:{PORT}"
    if request is not None:
        return str(request.base_url).rstrip("/")
    return f"http://127.0.0.1:{PORT}"


def share_view(rec: dict, request: Optional[Request] = None) -> dict:
    base = share_base(request)
    url = f"{base}/s/{rec['token']}"
    exp = int(rec.get("expires") or 0)
    return {
        "token": rec["token"],
        "label": rec.get("label") or "分享文件",
        "paths": rec.get("paths") or [],
        "count": len(rec.get("paths") or []),
        "url": url,
        "download_url": url + "?dl=1",
        "created": int(rec.get("created") or 0),
        "expires": exp,
        "expires_in": max(0, exp - int(time.time())) if exp else 0,
        "hits": int(rec.get("hits") or 0),
        "last": int(rec.get("last") or 0),
    }


def can_inline(path: Path) -> bool:
    mime = mimetypes.guess_type(path.name)[0] or ""
    return mime.startswith(INLINE_MIME_PREFIX) or mime in INLINE_MIME_EXACT


SHARE_404 = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>链接不可用 · 局域网云盘</title>
<style>
 html,body{height:100%;margin:0}
 body{display:grid;place-items:center;background:#f4f6fb;color:#1c2434;
      font:15px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
 .box{background:#fff;border-radius:18px;padding:34px 30px;max-width:420px;
      box-shadow:0 18px 50px rgba(28,36,52,.12);text-align:center}
 h1{margin:0 0 8px;font-size:18px}
 p{margin:0;color:#67708a}
 code{background:#f1f3f9;border-radius:6px;padding:1px 6px;font-size:12.5px}
 @media (prefers-color-scheme: dark){
   body{background:#0e1116;color:#e8ecf5}
   .box{background:#171b22;box-shadow:none}
   p{color:#9aa4bb} code{background:#222833}
 }
</style>
<div class="box">
  <h1>__TITLE__</h1>
  <p>__TEXT__</p>
</div></html>"""


def share_error_page(title: str, text: str) -> HTMLResponse:
    body = SHARE_404.replace("__TITLE__", title).replace("__TEXT__", text)
    return HTMLResponse(body, status_code=404)


@app.post("/api/share")
async def share_create(request: Request, payload: dict):
    require_auth(request)
    paths = payload.get("paths")
    if paths is None:
        paths = [payload.get("path") or ""]
    days = payload.get("days", 7)
    try:
        days = max(0, min(int(days), 365))
    except (TypeError, ValueError):
        days = 7

    targets = []
    for p in paths:
        target = resolve(p)
        if target.exists():
            targets.append(target)
    if not targets:
        raise HTTPException(status_code=404, detail="文件不存在，无法分享")

    label = str(payload.get("label") or "").strip()
    if not label:
        label = targets[0].name if len(targets) == 1 else f"{len(targets)} 个文件"

    try:
        rec = SHARES.create([rel_of(t) for t in targets], label, days)
    except shares.BadShare as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    view = share_view(rec, request)
    log(request, "share.create", "info", f"创建分享「{label}」",
        detail=f"{view['count']} 项 · {'永久' if not days else f'{days} 天'} · {view['url']}")
    return {"ok": True, "share": view}


@app.get("/api/shares")
async def share_list(request: Request):
    require_auth(request)
    return {"items": [share_view(r, request) for r in SHARES.list()]}


@app.post("/api/share/{token}")
async def share_update(request: Request, token: str, payload: dict):
    """调整有效期（不改 token，已经发出去的链接继续有效）。"""
    require_auth(request)
    try:
        days = max(0, min(int(payload.get("days", 7)), 365))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="有效期不合法") from None
    try:
        rec = SHARES.set_expiry(token, days)
    except shares.BadShare as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    log(request, "share.update", "info", f"修改分享有效期「{rec.get('label')}」",
        detail="永久" if not days else f"{days} 天")
    return {"ok": True, "share": share_view(rec, request)}


@app.delete("/api/share/{token}")
async def share_revoke(request: Request, token: str):
    require_auth(request)
    rec = SHARES.get(token, purge=False)
    if not SHARES.revoke(token):
        raise HTTPException(status_code=404, detail="链接不存在")
    log(request, "share.revoke", "warn", f"取消分享「{(rec or {}).get('label') or token}」")
    return {"ok": True}


@app.get("/s/{token}")
async def share_open(request: Request, token: str, dl: int = 0):
    """公开访问入口：不需要登录，凭链接即可预览或下载。"""
    rec = SHARES.get(token)
    if not rec:
        return share_error_page("链接已失效", "这个分享链接不存在、已过期或被取消了。")

    targets: List[Path] = []
    for p in rec.get("paths") or []:
        try:
            target = resolve(p)
        except HTTPException:
            continue
        if target.exists():
            targets.append(target)

    if not targets:
        return share_error_page("内容已被删除", "分享的文件已经不在云盘里了，请让对方重新分享。")

    SHARES.touch(token)
    log(request, "share.open", "info", f"访问分享「{rec.get('label')}」",
        detail=f"{len(targets)} 项 · {client_ip(request)}")

    if len(targets) == 1:
        target = targets[0]
        if target.is_dir():
            return zip_response(make_zip([target]), target.name)
        return serve_file(target, inline=not dl and can_inline(target),
                          filename=target.name, request=request)
    return zip_response(make_zip(targets), str(rec.get("label") or "分享文件"))


@app.get("/api/qr")
async def qr_png(request: Request, text: str = "", scale: int = 6):
    """把分享链接画成二维码（手机扫码即可打开）。"""
    require_auth(request)
    text = (text or "").strip()
    if not text or len(text) > 800:
        raise HTTPException(status_code=400, detail="内容不合法")
    try:
        import qrcode  # type: ignore
        from qrcode.constants import ERROR_CORRECT_M
    except ImportError:
        raise HTTPException(status_code=501, detail="服务端没有安装 qrcode") from None
    box = max(2, min(int(scale or 6), 16))
    try:
        qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=box, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1c2434", back_color="#ffffff")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
    except Exception:  # 少了 Pillow 之类，前端会自动隐藏二维码
        raise HTTPException(status_code=501, detail="二维码生成失败，建议装 Pillow") from None
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=600"})


@app.get("/api/text")
async def read_text(request: Request, path: str = ""):
    require_auth(request)
    target = resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if target.stat().st_size > MAX_TEXT_PREVIEW:
        raise HTTPException(status_code=413, detail="文件太大，无法预览")
    data = target.read_bytes()
    for enc in ("utf-8", "gb18030", "utf-16", "latin-1"):
        try:
            return {"content": data.decode(enc), "encoding": enc}
        except UnicodeDecodeError:
            continue
    return {"content": data.decode("utf-8", errors="replace"), "encoding": "utf-8?"}


@app.post("/api/save_text")
async def save_text(request: Request, payload: dict):
    require_auth(request)
    target = resolve(payload.get("path", ""))
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if target.stat().st_size > MAX_TEXT_PREVIEW:
        raise HTTPException(status_code=413, detail="文件太大，无法编辑")
    target.write_bytes(str(payload.get("content", "")).encode("utf-8"))
    log(request, "edit", "ok", f"保存文本「{target.name}」",
        detail=fmt_bytes(len(str(payload.get("content", "")).encode("utf-8"))))
    return {"ok": True, "item": item_of(target)}


# ---------------------------------------------------------------- Office 预览

_office_cache: dict = {}
_office_order: List[str] = []
OFFICE_CACHE_MAX = 16


@app.get("/api/office")
async def office_view(request: Request, path: str = ""):
    """解析 docx / xlsx / pptx，返回前端渲染用的中性结构。"""
    require_auth(request)
    target = resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    ext = target.suffix.lower()
    if ext in LEGACY_OFFICE_EXT:
        return {
            "type": "legacy",
            "message": f"{ext} 是 97-2003 老格式，无法在线解析",
            "name": target.name,
        }
    if ext not in OFFICE_EXT:
        raise HTTPException(status_code=400, detail="不支持该格式")

    st = target.stat()
    if st.st_size > MAX_OFFICE_PARSE:
        raise HTTPException(status_code=413, detail="文件太大（超过 60MB），请下载后查看")

    key = str(target)
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _office_cache.get(key)
    if hit and hit[0] == stamp:
        return hit[1]

    try:
        data = office.parse(target)
    except office.BadFile as exc:
        return {"type": "error", "message": str(exc), "name": target.name}
    except Exception as exc:  # 解析器兜底，别让单个坏文件把接口打挂
        return {"type": "error", "message": f"解析失败：{type(exc).__name__}", "name": target.name}

    data["name"] = target.name
    data["size"] = st.st_size
    _office_cache[key] = (stamp, data)
    _office_order.append(key)
    while len(_office_order) > OFFICE_CACHE_MAX:
        old = _office_order.pop(0)
        if old != key:
            _office_cache.pop(old, None)
    return data


@app.get("/api/office_media")
async def office_media(request: Request, path: str = "", name: str = ""):
    """取 Office 文件内嵌的图片（word/media/xxx、ppt/media/xxx）。"""
    require_auth(request)
    target = resolve(path)
    if not target.is_file() or not name:
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        with zipfile.ZipFile(target) as zf:
            info = zf.getinfo(name)
            if info.file_size > 40 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="图片过大")
            data = zf.read(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="资源不存在") from None
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="文件损坏") from None
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return Response(content=data, media_type=mime,
                    headers={"Cache-Control": "private, max-age=1800"})


# ---------------------------------------------------------------- 压缩包

@app.get("/api/archive")
async def archive_preview(request: Request, path: str = ""):
    """列出压缩包内文件（zip / tar / tar.gz，rar、7z 不支持）。"""
    require_auth(request)
    target = resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        data = archives.list_entries(target)
    except archives.Unsupported as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from None
    except archives.BadArchive as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    data["name"] = target.name
    data["size"] = target.stat().st_size
    return data


@app.post("/api/archive/extract")
async def archive_extract(request: Request, payload: dict):
    """解压到压缩包所在目录下、以压缩包名命名的新文件夹。"""
    require_auth(request)
    target = resolve(str(payload.get("path", "")))
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        rec = archives.extract(target, target.parent)
    except archives.Unsupported as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from None
    except archives.BadArchive as exc:
        log(request, "extract", "err", f"解压「{target.name}」失败", detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from None
    log(request, "extract", "info", f"解压「{target.name}」",
        detail=f"{rec['count']} 项，{fmt_bytes(rec['size'])} → {rec['dest']}/")
    return rec


# ---------------------------------------------------------------- 文件备注

@app.post("/api/remarks")
async def set_remark(request: Request, payload: dict):
    """给文件/文件夹写备注；text 为空表示清除。"""
    require_auth(request)
    target = resolve(str(payload.get("path", "")))
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    rec = REMARKS.set(rel_of(target), str(payload.get("text", "")))
    log(request, "remark", "ok",
        f"{'备注' if rec else '清除备注'}「{target.name}」",
        detail=(rec["text"][:60] + "…" if rec and len(rec["text"]) > 60 else (rec["text"] if rec else "")))
    return {"ok": True, "remark": rec["text"] if rec else ""}


# ---------------------------------------------------------------- 音频信息

@app.get("/api/audio_meta")
async def audio_meta(request: Request, path: str = ""):
    require_auth(request)
    target = resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    meta = audiotag.read(target)
    meta["name"] = target.name
    meta["size"] = target.stat().st_size
    meta["has_cover"] = "cover_mime" in meta
    return meta


@app.get("/api/audio_cover")
async def audio_cover(request: Request, path: str = ""):
    require_auth(request)
    target = resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    got = audiotag.cover(target)
    if not got:
        raise HTTPException(status_code=404, detail="没有内嵌封面")
    mime, data = got
    return Response(content=data, media_type=mime,
                    headers={"Cache-Control": "private, max-age=1800"})


# ---------------------------------------------------------------- 网络笔记

def note_error(exc: Exception) -> HTTPException:
    msg = str(exc) or "笔记操作失败"
    return HTTPException(status_code=404 if "不存在" in msg else 400, detail=msg)


@app.get("/api/notes")
async def notes_list(request: Request, q: str = ""):
    """笔记列表（置顶优先，其余按更新时间倒序）。"""
    require_auth(request)
    items = notes_store.list(q)
    return {"items": items, "count": len(items)}


@app.post("/api/notes")
async def notes_create(request: Request, payload: dict):
    require_auth(request)
    content = str(payload.get("content") or "")
    if len(content) > MAX_NOTE_CHARS:
        raise HTTPException(status_code=413, detail="笔记太长（超过 512KB）")
    note = notes_store.create(str(payload.get("title") or ""), content)
    log(request, "note.new", "ok", f"新建笔记「{note['title']}」", detail=f"{note['chars']} 字")
    return {"ok": True, "note": note}


@app.post("/api/notes/media")
async def notes_media_upload(request: Request, file: UploadFile = File(...)):
    """笔记里粘贴/插入的图片。"""
    require_auth(request)
    data = await file.read(MAX_NOTE_MEDIA + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=400, detail="文件是空的")
    if len(data) > MAX_NOTE_MEDIA:
        raise HTTPException(status_code=413, detail="图片太大（超过 20MB）")
    got = notes_store.put_media(data, file.filename or "")
    log(request, "note.media", "info", f"笔记插图「{file.filename or '粘贴的图片'}」",
        detail=fmt_bytes(len(data)))
    return {"ok": True, **got}


@app.get("/api/notes/export")
async def notes_export(request: Request):
    """把所有笔记打包成 Markdown 下载。"""
    require_auth(request)
    buf = io.BytesIO()
    used: set = set()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for note in notes_store.all_full():
            title = notes.derive_title(note.get("title") or "", note.get("content") or "")
            safe = BAD_CHARS.sub("_", title).strip(" .") or "笔记"
            name, i = safe, 1
            while name + ".md" in used:
                i += 1
                name = f"{safe} ({i})"
            used.add(name + ".md")
            zf.writestr(name + ".md", note.get("content") or "")
            count += 1
    if not count:
        raise HTTPException(status_code=404, detail="还没有笔记")
    log(request, "note.export", "ok", f"导出全部笔记（{count} 篇）")
    head = "attachment; filename*=UTF-8''" + quote(f"笔记_{time.strftime('%Y%m%d')}.zip")
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": head})


@app.get("/notes-media/{name}")
async def notes_media(name: str, request: Request):
    require_auth(request)
    try:
        target = notes_store.media_path(name)
    except notes.BadNote as exc:
        raise note_error(exc) from None
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=mime,
                        headers={"Cache-Control": "private, max-age=604800"})


@app.get("/api/notes/{nid}")
async def notes_get(request: Request, nid: str):
    require_auth(request)
    try:
        return notes_store.get(nid)
    except notes.BadNote as exc:
        raise note_error(exc) from None


@app.post("/api/notes/{nid}")
async def notes_save(request: Request, nid: str, payload: dict):
    require_auth(request)
    content = payload.get("content")
    title = payload.get("title")
    if content is not None and len(str(content)) > MAX_NOTE_CHARS:
        raise HTTPException(status_code=413, detail="笔记太长（超过 512KB）")
    try:
        note = notes_store.save(
            nid,
            None if title is None else str(title),
            None if content is None else str(content),
        )
    except notes.BadNote as exc:
        raise note_error(exc) from None
    return {"ok": True, "note": note}


@app.post("/api/notes/{nid}/pin")
async def notes_pin(request: Request, nid: str, payload: dict):
    require_auth(request)
    try:
        note = notes_store.set_pin(nid, bool(payload.get("pinned")))
    except notes.BadNote as exc:
        raise note_error(exc) from None
    return {"ok": True, "note": note}


@app.delete("/api/notes/{nid}")
async def notes_delete(request: Request, nid: str):
    require_auth(request)
    try:
        title = notes_store.get(nid).get("title") or "无标题笔记"
        notes_store.delete(nid)
    except notes.BadNote as exc:
        raise note_error(exc) from None
    log(request, "note.delete", "warn", f"删除笔记「{title}」")
    return {"ok": True}


# ---------------------------------------------------------------- 系统设置

def scan_storage() -> dict:
    """轻量统计云盘内容（有时间预算，不会让接口卡住）。"""
    files = folders = 0
    size = 0
    start = time.time()
    for root, dirs, names in os.walk(STORAGE):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        folders += len(dirs)
        for n in names:
            if n.endswith(".part"):
                continue
            files += 1
            try:
                size += (Path(root) / n).stat().st_size
            except OSError:
                pass
        if time.time() - start > 1.5:
            break
    return {"files": files, "folders": folders, "size": size}


@app.get("/api/about")
async def about(request: Request):
    """「关于我们」里展示的运行信息。"""
    require_auth(request)
    import fastapi  # 局部导入，避免顶层多一个依赖

    content = scan_storage()
    note_list = notes_store.list()
    note_chars = sum(n.get("chars") or 0 for n in note_list)
    du = shutil.disk_usage(STORAGE)

    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "tagline": "把一台电脑变成整个局域网的私有云盘",
        "started_at": int(STARTED_AT),
        "uptime": int(time.time() - STARTED_AT),
        "now": int(time.time()),
        "port": PORT,
        "addr": f":{PORT}",
        "lan": [f"http://{ip}:{PORT}" for ip in lan_ips()],
        "host": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "python": platform.python_version(),
        "fastapi": getattr(fastapi, "__version__", "—"),
        "storage_dir": str(STORAGE),
        "notes_dir": str(NOTES_DIR),
        "log_file": str(activity.path),
        "password": AUTH_ON,
        "content": content,
        "notes": {"count": len(note_list), "chars": note_chars},
        "logs": {"count": activity.total(), "file_size": _file_size(activity.path)},
        "disk": {"total": du.total, "free": du.free},
    }


def _file_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


@app.get("/api/logs")
async def logs_list(request: Request, level: str = "", q: str = "",
                    limit: int = 120, offset: int = 0):
    require_auth(request)
    if level and level not in journal.LEVELS:
        raise HTTPException(status_code=400, detail="未知的日志级别")
    return activity.query(level=level, keyword=q, limit=limit, offset=offset)


@app.delete("/api/logs")
async def logs_clear(request: Request):
    require_auth(request)
    removed = activity.clear()
    activity.record("log.clear", "warn", "系统日志已清空",
                    detail=f"清除了 {removed} 条记录", ip=client_ip(request))
    return {"ok": True, "removed": removed}


@app.get("/api/logs/export")
async def logs_export(request: Request):
    require_auth(request)
    text = activity.export_text()
    log(request, "log.export", "info", "导出系统日志", detail=f"{activity.total()} 条")
    name = f"云盘日志_{time.strftime('%Y%m%d_%H%M')}.txt"
    return Response(
        content=text.encode("utf-8-sig"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(name)},
    )


# ---------------------------------------------------------------- 错误日志

@app.middleware("http")
async def log_http_errors(request: Request, call_next):
    """只记出错的 API 请求，正常浏览不刷屏。"""
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001
        activity.record(
            "error", "error", f"{request.method} {request.url.path} 处理失败",
            detail=f"{type(exc).__name__}: {exc}", ip=client_ip(request),
        )
        raise

    path = request.url.path
    status = response.status_code
    if path.startswith("/static/"):
        # 每次都回源校验：改了样式/脚本，刷新即生效，不用清缓存
        response.headers["Cache-Control"] = "no-cache"
    noisy = status == 401 or path.startswith("/static/") or not path.startswith("/api/")
    if status >= 400 and not noisy:
        level = "error" if status >= 500 else "warn"
        activity.record(
            f"http.{status}", level,
            f"{request.method} {path} → {status}",
            detail=str(request.url.query)[:200], ip=client_ip(request),
        )
    return response


# ---------------------------------------------------------------- 前端

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """注入静态资源版本号，避免浏览器拿旧缓存导致新按钮点了没反应。"""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    stamp = 0
    for name in ("app.js", "style.css"):
        try:
            stamp = max(stamp, int((STATIC_DIR / name).stat().st_mtime))
        except OSError:
            pass
    return HTMLResponse(html.replace("__V__", str(stamp)),
                        headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


# ---------------------------------------------------------------- 启动

def lan_ips() -> List[str]:
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except socket.gaierror:
        pass

    def rank(ip: str) -> tuple:
        """家里/公司最常见的 192.168 优先，避免先列出虚拟网卡。"""
        if ip.startswith("192.168."):
            return (0, ip)
        if ip.startswith("10."):
            return (1, ip)
        if ip.startswith("172."):
            return (2, ip)
        return (3, ip)

    return sorted(ips, key=rank)


def show_qr(url: str) -> None:
    try:
        import qrcode  # type: ignore
    except ImportError:
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


if __name__ == "__main__":
    ips = lan_ips()
    print("\n" + "=" * 52)
    print("  局域网云盘已启动")
    print(f"  存储目录 : {STORAGE}")
    print(f"  笔记目录 : {NOTES_DIR}")
    print(f"  本机访问 : http://127.0.0.1:{PORT}")
    for ip in ips:
        print(f"  局域网   : http://{ip}:{PORT}")
    if AUTH_ON:
        print("  访问口令 : 已开启")
    print("=" * 52)
    if ips:
        show_qr(f"http://{ips[0]}:{PORT}")
    print("  按 Ctrl+C 停止\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
