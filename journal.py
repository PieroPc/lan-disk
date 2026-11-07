"""活动日志（系统日志）

设计取舍：
- 进程内用 deque 存最近 MAX_MEMORY 条，查询走内存，不做磁盘扫描
- 同时按行追加写 logs/system.log，一行一条 JSON，服务重启后能恢复
- 文件超过 MAX_FILE 轮转一份 .1，只留一代，避免无限增长
- 写操作加锁，读操作基于快照，不阻塞请求
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

MAX_MEMORY = 2000          # 内存里保留多少条
MAX_FILE = 2 * 1024 * 1024  # 单个日志文件上限 2MB
MAX_MSG = 300               # 单条消息长度上限
MAX_DETAIL = 600

LEVELS = ("info", "ok", "warn", "error")


class Journal:
    def __init__(self, directory: Path, filename: str = "system.log"):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / filename
        self._lock = threading.Lock()
        self._items: deque = deque(maxlen=MAX_MEMORY)
        self._seq = 0
        self._load_history()

    # ------------------------------------------------------------ 内部

    def _load_history(self) -> None:
        """从日志文件尾部恢复最近的记录，让重启后不是一片空白。"""
        if not self.path.exists():
            return
        try:
            size = self.path.stat().st_size
            with open(self.path, "rb") as fh:
                if size > MAX_FILE // 2:
                    fh.seek(size - MAX_FILE // 2)
                    fh.readline()  # 丢掉被截断的首行
                raw = fh.read()
        except OSError:
            return

        loaded: List[dict] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and "ts" in row:
                loaded.append(row)
        for row in loaded[-MAX_MEMORY:]:
            self._items.append(row)
            try:
                self._seq = max(self._seq, int(row.get("id") or 0))
            except (TypeError, ValueError):
                pass

    def _rotate(self) -> None:
        if not self.path.exists():
            return
        try:
            if self.path.stat().st_size < MAX_FILE:
                return
            old = self.path.with_suffix(self.path.suffix + ".1")
            os.replace(self.path, old)
        except OSError:
            pass

    # ------------------------------------------------------------ 写入

    def record(self, action: str, level: str = "info", message: str = "",
               detail: str = "", ip: str = "") -> dict:
        """记一条。action 是机器可读的短标识，例如 upload / delete / note.save。"""
        level = level if level in LEVELS else "info"
        with self._lock:
            self._seq += 1
            row = {
                "id": self._seq,
                "ts": round(time.time(), 3),
                "level": level,
                "action": (action or "event")[:40],
                "message": (message or "")[:MAX_MSG],
                "detail": (detail or "")[:MAX_DETAIL],
                "ip": (ip or "")[:64],
            }
            self._items.append(row)
            try:
                self._rotate()
                with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            except OSError:
                pass  # 日志写不进去也不能影响正常业务
            return row

    # ------------------------------------------------------------ 查询

    def _snapshot(self) -> List[dict]:
        with self._lock:
            return list(self._items)

    def counts(self) -> Dict[str, int]:
        rows = self._snapshot()
        out = {"all": len(rows), "info": 0, "ok": 0, "warn": 0, "error": 0}
        for row in rows:
            lv = row.get("level")
            if lv in out:
                out[lv] += 1
        return out

    def query(self, level: str = "", keyword: str = "", limit: int = 120,
              offset: int = 0) -> dict:
        rows = self._snapshot()
        counts = {"all": len(rows), "info": 0, "ok": 0, "warn": 0, "error": 0}
        for row in rows:
            lv = row.get("level")
            if lv in counts:
                counts[lv] += 1

        kw = (keyword or "").strip().lower()
        filtered = []
        for row in reversed(rows):  # 新的在前
            if level and row.get("level") != level:
                continue
            if kw:
                hay = f"{row.get('message','')} {row.get('detail','')} {row.get('action','')}".lower()
                if kw not in hay:
                    continue
            filtered.append(row)

        limit = max(1, min(int(limit or 120), 500))
        offset = max(0, int(offset or 0))
        page = filtered[offset:offset + limit]

        try:
            size = self.path.stat().st_size if self.path.exists() else 0
        except OSError:
            size = 0

        return {
            "items": page,
            "matched": len(filtered),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(page) < len(filtered),
            "counts": counts,
            "file_size": size,
        }

    def total(self) -> int:
        with self._lock:
            return len(self._items)

    # ------------------------------------------------------------ 维护

    def clear(self) -> int:
        """清空内存与文件，返回清掉的条数。"""
        with self._lock:
            removed = len(self._items)
            self._items.clear()
            try:
                self.path.write_text("", encoding="utf-8")
                old = self.path.with_suffix(self.path.suffix + ".1")
                if old.exists():
                    old.unlink()
            except OSError:
                pass
            return removed

    def export_text(self) -> str:
        """导出为纯文本，方便直接贴给别人看。"""
        rows = self._snapshot()
        lines = [
            "# 局域网云盘 · 系统日志",
            f"# 导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"# 记录条数：{len(rows)}",
            "",
        ]
        for row in rows:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row.get("ts") or 0))
            lv = str(row.get("level") or "info").upper().ljust(5)
            head = f"{ts}  {lv}  [{row.get('action','')}]  {row.get('message','')}"
            lines.append(head)
            if row.get("detail"):
                lines.append(f"{' ' * 22}{row['detail']}")
            if row.get("ip"):
                lines.append(f"{' ' * 22}来源 {row['ip']}")
        return "\n".join(lines) + "\n"
