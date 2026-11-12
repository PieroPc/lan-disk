"""微信本地 OCR 引擎接入（不联网、不需要 AppID）。

原理：调用本机安装的微信自带的 OCR 引擎（wxocr.dll + .xnet 模型），
通过开源封装 wcocr.dll（github.com/swigger/wechat-ocr，随云盘附带在 wcocr/ 目录）
以进程间通信方式驱动引擎识别图片文字。图片不上传到任何服务器。

自动检测：
  1) OCR 引擎： %APPDATA%\\Tencent\\xwechat\\XPlugin\\plugins\\WeChatOcr\\<版本>\\extracted\\wxocr.dll
  2) 微信目录（含 mmmojo_64.dll）： C:\\Program Files\\Tencent\\Weixin\\<版本> 等
  3) 手动路径覆盖存本机 ocr.json： {"ocr_dll": "...", "wechat_dir": "..."}
"""
import ctypes
import json
import os
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
FILE = BASE_DIR / "data" / "ocr.json"             # 手动配置（可选，归档在 data/ 里）
WCOCR_DLL = BASE_DIR / "wcocr" / "wcocr.dll"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif"}
MAX_SIZE = 20 * 1024 * 1024
MIN_SIZE = 512

_lock = threading.Lock()
_dll = None
_cached = None                                    # 检测结果缓存


class OcrError(Exception):
    """面向用户的友好错误。"""


# ---------------------------------------------------------------- 配置

def load() -> dict:
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save(cfg: dict):
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, FILE)
    global _cached
    _cached = None


def clear():
    global _cached
    if FILE.exists():
        FILE.unlink()
    _cached = None


# ---------------------------------------------------------------- 自动检测

def _find_wxocr_dll() -> str:
    """找微信解压好的 wxocr.dll，取版本号最大的一个。"""
    appdata = os.environ.get("APPDATA", "")
    root = Path(appdata) / "Tencent" / "xwechat" / "XPlugin" / "plugins" / "WeChatOcr"
    best = None
    if root.is_dir():
        for ver in root.iterdir():
            cand = ver / "extracted" / "wxocr.dll"
            if cand.is_file():
                try:
                    key = [int(x) for x in ver.name.split(".")]
                except ValueError:
                    key = [0]
                if best is None or key > best[0]:
                    best = (key, str(cand))
    return best[1] if best else ""


def _find_wechat_dirs() -> list:
    """候选微信安装目录（含 mmmojo_64.dll 的版本目录），版本新的优先。"""
    out = []
    roots = [
        Path("C:/Program Files/Tencent/Weixin"),
        Path("C:/Program Files (x86)/Tencent/Weixin"),
        Path("C:/Program Files/Tencent/WeChat"),
        Path("C:/Program Files (x86)/Tencent/WeChat"),
        Path("D:/Program Files/Tencent/Weixin"),
        Path("D:/Tencent/Weixin"),
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if (child / "mmmojo_64.dll").is_file() or (child / "Weixin.exe").is_file():
                out.append(str(child))
            elif root.name == "WeChat" and (child / "mmmojo_64.dll").is_file():
                out.append(str(child))
    # 版本目录形如 4.1.15.50 / [3.9.12.17]，新的排前面
    def vkey(p: str):
        import re
        m = re.findall(r"\d+", Path(p).name)
        return [int(x) for x in m] or [0]
    out.sort(key=vkey, reverse=True)
    return out


def detect() -> dict:
    """返回 {"found", "ocr_dll", "wechat_dir", "manual"}，manual=True 表示用了手动配置。"""
    global _cached
    if _cached is not None:
        return _cached
    cfg = load()
    manual = bool(cfg.get("ocr_dll") or cfg.get("wechat_dir"))
    ocr_dll = cfg.get("ocr_dll") or _find_wxocr_dll()
    wechat_dir = cfg.get("wechat_dir") or ""
    found = False
    if ocr_dll and Path(ocr_dll).is_file() and WCOCR_DLL.is_file():
        if not wechat_dir:
            for cand in _find_wechat_dirs():
                # wxocr 引擎需要微信目录里的 mmmojo_64.dll
                if (Path(cand) / "mmmojo_64.dll").is_file():
                    wechat_dir = cand
                    break
        found = bool(ocr_dll and wechat_dir and Path(wechat_dir, "mmmojo_64.dll").is_file())
    _cached = {
        "found": found,
        "ocr_dll": ocr_dll if found else (ocr_dll or ""),
        "wechat_dir": wechat_dir,
        "manual": manual,
    }
    return _cached


# ---------------------------------------------------------------- 引擎调用

_RESULT_CB = ctypes.CFUNCTYPE(None, ctypes.c_void_p)


def _get_dll():
    global _dll
    if _dll is None:
        _dll = ctypes.CDLL(str(WCOCR_DLL))
        _dll.wechat_ocr.argtypes = [
            ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_char_p, _RESULT_CB]
        _dll.wechat_ocr.restype = ctypes.c_bool
    return _dll


def recognize(path: Path) -> str:
    """识别图片文字，返回多行文本。完全本地，不联网。"""
    info = detect()
    if not info["found"]:
        raise OcrError("没有找到微信的 OCR 引擎：请确认本机已安装新版微信（4.x），或到 设置 → 文字识别 手动指定路径")
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in IMAGE_EXT:
        raise OcrError("只支持识别图片文件")
    size = path.stat().st_size
    if size > MAX_SIZE:
        raise OcrError("图片超过 20MB，无法识别")
    if size < MIN_SIZE:
        raise OcrError("图片太小，无法识别")

    holder = {}

    def on_result(ptr):
        if ptr:
            holder["json"] = ctypes.string_at(ptr).decode("utf-8", "replace")

    dll = _get_dll()
    cb = _RESULT_CB(on_result)
    with _lock:                       # 引擎一次只喂一张图
        try:
            ok = dll.wechat_ocr(info["ocr_dll"], info["wechat_dir"],
                                str(path).encode("utf-8"), cb)
        except Exception as e:
            raise OcrError(f"OCR 引擎调用失败：{e}")
        raw = holder.get("json", "")
        if not ok and not raw:
            raise OcrError("OCR 引擎没有返回结果（微信可能正在升级，稍后再试）")
    try:
        data = json.loads(raw)
    except Exception:
        raise OcrError("OCR 引擎返回了无法解析的数据")

    if data.get("errcode", 0) != 0:
        raise OcrError(f"识别失败（errcode={data.get('errcode')}）")
    lines = [str(x.get("text", "")).strip() for x in data.get("ocr_response", [])]
    text = "\n".join(x for x in lines if x)
    if not text:
        raise OcrError("没有识别出文字（图片里可能没有可读文本）")
    return text
