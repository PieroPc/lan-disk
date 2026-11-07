"""
分享链接 · 把云盘里的文件/文件夹变成一个短地址

- 链接形如 http://192.168.1.9:8088/s/AbC123xyz ，同一局域网内谁都能打开
- 记录持久化在 shares.json，服务重启后原来的链接依然有效
- 支持有效期（1/7/30 天或永久）、访问计数；文件被删掉后链接自动失效
- 令牌不可猜测（secrets 生成），也不需要登录态，所以别把链接发到公网
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

MAX_ITEMS = 200  # 一个分享最多包含多少个文件
TOKEN_BYTES = 9  # token_urlsafe(9) → 12 个字符


class BadShare(Exception):
    """分享参数不合法 / 记录不存在。"""


class Store:
    def __init__(self, path: Path) -> None:
        self.file = Path(path)
        self._lock = threading.RLock()
        self._items: Dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------ 持久化
    def _load(self) -> None:
        try:
            raw = json.loads(self.file.read_text("utf-8"))
        except (OSError, ValueError):
            raw = {}
        items = raw.get("items") if isinstance(raw, dict) else None
        if isinstance(items, dict):
            self._items = {k: v for k, v in items.items() if isinstance(v, dict)}

    def _save(self) -> None:
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_name(self.file.name + ".tmp")
            tmp.write_text(
                json.dumps({"items": self._items}, ensure_ascii=False, indent=1),
                "utf-8",
            )
            tmp.replace(self.file)
        except OSError:
            pass  # 磁盘只读也不该让分享失败，内存里仍然可用

    # ------------------------------------------------------------ 业务
    def create(self, paths: List[str], label: str = "", days: int = 7) -> dict:
        cleaned: List[str] = []
        for p in paths or []:
            p = (p or "").replace("\\", "/").strip("/")
            if p and p not in cleaned:
                cleaned.append(p)
        if not cleaned:
            raise BadShare("没有选择要分享的内容")
        if len(cleaned) > MAX_ITEMS:
            raise BadShare(f"一次最多分享 {MAX_ITEMS} 项")

        now = int(time.time())
        token = secrets.token_urlsafe(TOKEN_BYTES)
        while token in self._items:  # 理论上不会撞，稳妥起见
            token = secrets.token_urlsafe(TOKEN_BYTES)

        rec = {
            "token": token,
            "paths": cleaned,
            "label": (label or "").strip()[:120] or "分享文件",
            "created": now,
            "expires": now + int(days) * 86400 if days else 0,
            "hits": 0,
            "last": 0,
        }
        with self._lock:
            self._items[token] = rec
            self._save()
        return rec

    def get(self, token: str, purge: bool = True) -> Optional[dict]:
        rec = self._items.get(token or "")
        if not rec:
            return None
        exp = int(rec.get("expires") or 0)
        if exp and exp < time.time():
            if purge:
                self.revoke(token)
            return None
        return rec

    def set_expiry(self, token: str, days: int) -> dict:
        rec = self.get(token)
        if not rec:
            raise BadShare("链接不存在或已过期")
        with self._lock:
            rec["expires"] = int(time.time()) + int(days) * 86400 if days else 0
            self._save()
        return rec

    def touch(self, token: str) -> None:
        with self._lock:
            rec = self._items.get(token)
            if not rec:
                return
            rec["hits"] = int(rec.get("hits") or 0) + 1
            rec["last"] = int(time.time())
            self._save()

    def revoke(self, token: str) -> bool:
        with self._lock:
            if self._items.pop(token or "", None) is None:
                return False
            self._save()
            return True

    def list(self) -> List[dict]:
        """未过期的分享，最近访问/创建的排前面。"""
        keep = {}
        changed = False
        for token, rec in list(self._items.items()):
            exp = int(rec.get("expires") or 0)
            if exp and exp < time.time():
                self._items.pop(token, None)
                changed = True
                continue
            keep[token] = rec
        if changed:
            self._save()
        return sorted(keep.values(), key=lambda r: (r.get("last") or r.get("created") or 0), reverse=True)

    def total(self) -> int:
        return len(self._items)
