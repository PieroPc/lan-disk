"""文件备注： remarks.json 存储（相对路径 -> {text, updated}）。

文件被重命名 / 移动 / 删除时由 main.py 同步维护，备注跟着文件走。
"""
import json
import os
import time
from pathlib import Path


def norm(p: str) -> str:
    """统一成 / 分隔、无首尾斜杠的相对路径。"""
    p = str(p).replace("\\", "/").strip().strip("/")
    while "//" in p:
        p = p.replace("//", "/")
    return p


class Remarks:
    def __init__(self, file: Path):
        self.file = Path(file)
        self.data = {}
        self._load()

    # ---- 存取 ----
    def _load(self):
        try:
            self.data = json.loads(self.file.read_text(encoding="utf-8"))
            if not isinstance(self.data, dict):
                self.data = {}
        except Exception:
            self.data = {}

    def _save(self):
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.file)  # 原子替换，断电也不丢旧文件

    # ---- 查询 ----
    def get(self, path) -> str:
        rec = self.data.get(norm(path))
        return rec["text"] if rec else ""

    def count(self) -> int:
        return len(self.data)

    # ---- 修改 ----
    def set(self, path, text):
        """写入备注；text 为空则删除记录，返回记录 dict 或 None。"""
        key = norm(path)
        text = (text or "").strip()
        if not text:
            if key in self.data:
                self.data.pop(key)
                self._save()
            return None
        rec = {"text": text, "updated": int(time.time())}
        self.data[key] = rec
        self._save()
        return rec

    def move_prefix(self, old, new):
        """重命名/移动：old（含其子路径前缀）的备注全部改挂到 new。"""
        old, new = norm(old), norm(new)
        if not old or old == new:
            return
        hit = False
        for key in list(self.data):
            if key == old or key.startswith(old + "/"):
                self.data[new + key[len(old):]] = self.data.pop(key)
                hit = True
        if hit:
            self._save()

    def delete_prefix(self, path):
        """删除文件/目录：连带清掉它和它子路径的所有备注。"""
        path = norm(path)
        if not path:
            return
        hit = False
        for key in list(self.data):
            if key == path or key.startswith(path + "/"):
                self.data.pop(key)
                hit = True
        if hit:
            self._save()
