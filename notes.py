"""
网络笔记 · Markdown 存储

磁盘结构：
    notes/<id>.json          每篇笔记一个文件，原子写入
    notes/media/<hash>.<ext> 笔记里粘贴/插入的图片

单文件存储既方便备份（整个 notes 目录 copy 走就能用），
也避免把几百篇笔记塞进同一个大 JSON 里反复重写。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import List, Optional

ID_RE = re.compile(r"^[0-9a-f]{12}$")
MEDIA_RE = re.compile(r"^[0-9a-f]{16}\.[a-z0-9]{2,5}$")
TITLE_MAX = 120
EXCERPT_MAX = 160
MEDIA_EXT = {".png", ".jpg", ".gif", ".webp", ".bmp", ".svg", ".avif"}


class BadNote(Exception):
    """笔记编号 / 附件名不合法，或内容超限。"""


# ------------------------------------------------------------------ 文本处理

_MD_PATTERNS = [
    (re.compile(r"```.*?```", re.S), " "),
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), " "),
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),
    (re.compile(r"<[^>]+>"), " "),
    (re.compile(r"^\s{0,3}#{1,6}\s*", re.M), ""),
    (re.compile(r"^\s{0,3}>\s?", re.M), ""),
    (re.compile(r"^\s*([-*+]|\d+[.)])\s+", re.M), ""),
    (re.compile(r"[*_~]{1,3}"), ""),
    (re.compile(r"^\s*[-:| ]{3,}\s*$", re.M), " "),
    (re.compile(r"\|"), " "),
]


def _plain(content: str) -> str:
    """把 Markdown 粗略压成纯文本，用于列表摘要与搜索。"""
    text = content or ""
    for pattern, repl in _MD_PATTERNS:
        text = pattern.sub(repl, text)
    return re.sub(r"\s+", " ", text).strip()


def derive_title(title: str, content: str) -> str:
    """用户没写标题时，取正文第一行有内容的文字。"""
    t = (title or "").strip()
    if t:
        return t[:TITLE_MAX]
    for line in (content or "").splitlines():
        s = line.strip()
        if not s or s in ("---", "***"):
            continue
        s = re.sub(r"^#{1,6}\s*", "", s)
        s = re.sub(r"^([-*+>]|\d+[.)])\s*", "", s)
        s = re.sub(r"^\[[ xX]\]\s*", "", s)
        s = s.replace("**", "").replace("`", "").strip()
        if s:
            return s[:TITLE_MAX]
    return "无标题笔记"


def meta_of(note: dict) -> dict:
    content = note.get("content") or ""
    return {
        "id": note.get("id", ""),
        "title": derive_title(note.get("title") or "", content),
        "title_raw": note.get("title") or "",
        "excerpt": _plain(content)[:EXCERPT_MAX],
        "chars": len(content),
        "pinned": bool(note.get("pinned")),
        "created": int(note.get("created") or 0),
        "updated": int(note.get("updated") or 0),
    }


# ------------------------------------------------------------------ 存储

class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.media_dir = self.root / "media"
        self.root.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ---- 内部 ----
    def _path(self, nid: str) -> Path:
        nid = str(nid or "")
        if not ID_RE.match(nid):
            raise BadNote("笔记编号不合法")
        return self.root / f"{nid}.json"

    def _read(self, p: Path) -> Optional[dict]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or not data.get("id"):
            return None
        return data

    def _write(self, note: dict) -> None:
        p = self._path(note["id"])
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)

    def _scan(self) -> List[dict]:
        out: List[dict] = []
        try:
            entries = list(os.scandir(self.root))
        except OSError:
            return out
        for entry in entries:
            if not entry.name.endswith(".json"):
                continue
            note = self._read(Path(entry.path))
            if note:
                out.append(note)
        out.sort(key=lambda n: (bool(n.get("pinned")), int(n.get("updated") or 0)), reverse=True)
        return out

    # ---- 对外 ----
    def list(self, q: str = "") -> List[dict]:
        q = (q or "").strip().lower()
        items = []
        for note in self._scan():
            if q:
                hay = f"{note.get('title', '')}\n{note.get('content', '')}".lower()
                if q not in hay:
                    continue
            items.append(meta_of(note))
        return items

    def get(self, nid: str) -> dict:
        note = self._read(self._path(nid))
        if not note:
            raise BadNote("笔记不存在")
        data = meta_of(note)
        data["content"] = note.get("content") or ""
        return data

    def all_full(self) -> List[dict]:
        """导出用：包含正文的全部笔记。"""
        return self._scan()

    def create(self, title: str = "", content: str = "") -> dict:
        now = int(time.time())
        note = {
            "id": uuid.uuid4().hex[:12],
            "title": (title or "").strip()[:TITLE_MAX],
            "content": content or "",
            "pinned": False,
            "created": now,
            "updated": now,
        }
        with self._lock:
            self._write(note)
        return meta_of(note)

    def save(self, nid: str, title: Optional[str] = None, content: Optional[str] = None) -> dict:
        p = self._path(nid)
        with self._lock:
            note = self._read(p)
            if not note:
                raise BadNote("笔记不存在")
            if content is not None:
                note["content"] = content
            if title is not None:
                # 只存用户真正写下的标题；空标题由正文首行推导展示
                note["title"] = title.strip()[:TITLE_MAX]
            note["updated"] = int(time.time())
            self._write(note)
        return meta_of(note)

    def delete(self, nid: str) -> None:
        p = self._path(nid)
        with self._lock:
            try:
                p.unlink()
            except FileNotFoundError:
                raise BadNote("笔记不存在") from None

    def set_pin(self, nid: str, pinned: bool) -> dict:
        p = self._path(nid)
        with self._lock:
            note = self._read(p)
            if not note:
                raise BadNote("笔记不存在")
            note["pinned"] = bool(pinned)
            note["updated"] = int(time.time())
            self._write(note)
        return meta_of(note)

    # ---- 附件 ----
    def put_media(self, data: bytes, filename: str = "") -> dict:
        ext = Path(filename or "").suffix.lower()
        if ext == ".jpeg":
            ext = ".jpg"
        if ext not in MEDIA_EXT:
            ext = ".png"
        name = f"{hashlib.sha1(data).hexdigest()[:16]}{ext}"
        target = self.media_dir / name
        if not target.exists():
            target.write_bytes(data)
        stem = Path(filename or "").stem.strip() or "图片"
        return {"name": stem[:60], "url": f"/notes-media/{name}"}

    def media_path(self, name: str) -> Path:
        name = str(name or "")
        if not MEDIA_RE.match(name):
            raise BadNote("资源名不合法")
        p = self.media_dir / name
        if not p.is_file():
            raise BadNote("资源不存在")
        return p
