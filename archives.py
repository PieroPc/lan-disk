"""压缩包内容预览与解压（纯标准库：zipfile / tarfile）。

支持 zip、tar、tar.gz/bz2/xz 以及单文件 .gz/.bz2/.xz；
rar、7z 没有标准库支持，明确报「请下载后解压」。
"""
import tarfile
import time
import zipfile
from pathlib import Path, PurePosixPath

MAX_ENTRIES = 5000                 # 预览最多列出的条目数
MAX_EXTRACT_BYTES = 2 * 1024**3    # 解压总量上限 2GB，防解压炸弹
_SINGLE = {".gz", ".bz2", ".xz"}
_TAR_SUFFIX = (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz")


class BadArchive(Exception):
    """文件损坏或不是受支持的压缩包。"""


class Unsupported(Exception):
    """格式明确不支持（rar/7z）。"""


def _decode_zip_name(info) -> str:
    """zip 的文件名：有 UTF-8 标志直接用；否则按 cp437 存的原始字节猜 utf-8/gbk。"""
    if info.flag_bits & 0x800:
        return info.filename
    raw = info.filename.encode("cp437", "replace")
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return info.filename


def _zip_ts(info) -> int:
    try:
        y, mo, d, h, mi, s = info.date_time
        return int(time.mktime((y, mo, d, h, mi, min(s, 59), -1, -1, -1)))
    except Exception:
        return 0


def _entry(name: str, is_dir: bool, size: int, csize, mtime: int) -> dict:
    return {"name": name, "dir": is_dir, "size": 0 if is_dir else size,
            "csize": csize, "mtime": int(mtime or 0)}


def _list_zip(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            entries = []
            for i in infos[:MAX_ENTRIES]:
                name = _decode_zip_name(i)
                if not name:
                    continue
                entries.append(_entry(name, i.is_dir(), i.file_size,
                                      i.compress_size, _zip_ts(i)))
            return {"type": "zip", "entries": entries, "total": len(infos),
                    "truncated": len(infos) > MAX_ENTRIES,
                    "encrypted": any(i.flag_bits & 0x1 for i in infos)}
    except zipfile.BadZipFile:
        raise BadArchive("压缩包损坏，或不是有效的 zip 文件") from None
    except NotImplementedError:
        raise BadArchive("该压缩包使用了不支持的压缩算法") from None
    except OSError as exc:
        raise BadArchive(f"读取失败：{exc}") from None


def _list_tar(path: Path) -> dict:
    try:
        with tarfile.open(path, "r:*") as tf:
            members = tf.getmembers()
            entries = [_entry(m.name, m.isdir(), m.size, None, m.mtime)
                       for m in members[:MAX_ENTRIES] if m.name]
            return {"type": "tar", "entries": entries, "total": len(members),
                    "truncated": len(members) > MAX_ENTRIES, "encrypted": False}
    except tarfile.TarError:
        raise BadArchive("压缩包损坏，或不是有效的 tar 文件") from None
    except OSError as exc:
        raise BadArchive(f"读取失败：{exc}") from None


def list_entries(path: Path) -> dict:
    """返回压缩包内条目列表。"""
    ext = path.suffix.lower()
    lower = path.name.lower()
    if ext == ".zip":
        return _list_zip(path)
    if ext == ".tar" or lower.endswith(_TAR_SUFFIX):
        return _list_tar(path)
    if ext in _SINGLE:
        # 单文件压缩，如 photo.jpg.gz —— 里头就一个文件
        inner = lower[:-len(ext)] or path.stem
        try:
            st = path.stat()
            size = 0
            if ext == ".gz":  # gzip 尾部 4 字节 ISIZE 就是原始大小（mod 2^32）
                import struct
                with open(path, "rb") as f:
                    f.seek(-4, 2)
                    size = struct.unpack("<I", f.read(4))[0]
            return {"type": "single", "total": 1, "truncated": False,
                    "encrypted": False,
                    "entries": [_entry(inner, False, size, None, st.st_mtime)]}
        except OSError as exc:
            raise BadArchive(f"读取失败：{exc}") from None
    raise Unsupported("在线查看仅支持 zip / tar / tar.gz，rar、7z 请下载后解压")


# ---------------------------------------------------------------- 解压

def _safe_rel(name: str) -> Path:
    """把压缩包内的路径转成安全相对路径，挡掉 zip slip（../ 、绝对路径、盘符）。"""
    clean = name.replace("\\", "/")
    parts = [p for p in PurePosixPath(clean).parts
             if p not in ("..", ".") and not p.startswith("/") and ":" not in p]
    if not parts:
        raise BadArchive(f"压缩包内路径不安全：{name}")
    return Path(*parts)


def _free_dir(base: Path, stem: str) -> Path:
    stem = (stem or "archive").strip().rstrip(".") or "archive"
    cand = base / stem
    n = 1
    while cand.exists():
        cand = base / f"{stem} ({n})"
        n += 1
        if n > 999:
            raise BadArchive("目标文件夹名冲突")
    cand.mkdir(parents=True)
    return cand


def extract(path: Path, base: Path) -> dict:
    """把压缩包解到 base 下的同名新文件夹里，返回 {dest, count, size}。"""
    ext = path.suffix.lower()
    lower = path.name.lower()
    if ext not in (".zip", ".tar") and not lower.endswith(_TAR_SUFFIX) and ext not in _SINGLE:
        raise Unsupported("在线解压仅支持 zip / tar / tar.gz，rar、7z 请用本地工具")
    if ext in _SINGLE and not lower.endswith(_TAR_SUFFIX):
        raise Unsupported("单文件压缩（.gz/.bz2/.xz）没有解压的必要")

    # 备份.tar.gz 的解压文件夹应该叫「备份」而不是「备份.tar」
    stem = path.stem
    for suf in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz",
                ".zip", ".tar", ".gz", ".bz2", ".xz"):
        if lower.endswith(suf):
            stem = path.name[: -len(suf)]
            break
    dest = _free_dir(base, stem)
    count = 0
    total = 0
    try:
        if ext == ".zip":
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    rel = _safe_rel(_decode_zip_name(info))
                    out = dest / rel
                    if info.is_dir():
                        out.mkdir(parents=True, exist_ok=True)
                        continue
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(out, "wb") as f:
                        while True:
                            chunk = src.read(256 * 1024)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > MAX_EXTRACT_BYTES:
                                raise BadArchive("解压后的内容超过 2GB，已中止")
                            f.write(chunk)
                    count += 1
        else:
            with tarfile.open(path, "r:*") as tf:
                for m in tf.getmembers():
                    if m.name in ("", "."):
                        continue
                    rel = _safe_rel(m.name)
                    out = dest / rel
                    if m.isdir():
                        out.mkdir(parents=True, exist_ok=True)
                        continue
                    if not m.isfile():
                        continue  # 跳过软链接、设备文件，防提权
                    out.parent.mkdir(parents=True, exist_ok=True)
                    src = tf.extractfile(m)
                    if src is None:
                        continue
                    with src, open(out, "wb") as f:
                        while True:
                            chunk = src.read(256 * 1024)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > MAX_EXTRACT_BYTES:
                                raise BadArchive("解压后的内容超过 2GB，已中止")
                            f.write(chunk)
                    count += 1
    except (zipfile.BadZipFile, tarfile.TarError):
        raise BadArchive("压缩包损坏，解压中止（已解出的部分保留）") from None
    return {"dest": dest.name, "count": count, "size": total}
