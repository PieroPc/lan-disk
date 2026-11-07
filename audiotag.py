"""读取音频文件内嵌信息（目前覆盖 MP3 的 ID3v2 / ID3v1）。

只为了在预览页显示歌名、艺人、专辑和封面，不做转码。
"""

from __future__ import annotations

from pathlib import Path

MAX_TAG = 24 * 1024 * 1024  # 见过封面很大的 mp3，但也不能无限读

_ENC = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}

APIC_MIME = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
    "image/gif": "image/gif",
    "jpg": "image/jpeg",
    "png": "image/png",
}

FRAME_MAP = {
    "TIT2": "title", "TT2": "title",
    "TPE1": "artist", "TP1": "artist",
    "TALB": "album", "TAL": "album",
    "TYER": "year", "TDRC": "year", "TYE": "year",
    "TCON": "genre", "TCO": "genre",
    "TRCK": "track", "TRK": "track",
}


def _syncsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _id3v2(data: bytes):
    """返回 (tags dict, apic tuple|None)。data 至少 10 字节。"""
    if len(data) < 10 or data[:3] != b"ID3":
        return {}, None
    major = data[3]
    flags = data[5]
    size = _syncsafe(data[6:10])
    body = data[10:10 + size]
    if flags & 0x80 and major < 4:  # 整体 unsynchronisation
        body = body.replace(b"\xff\x00", b"\xff")

    tags: dict = {}
    apic = None
    pos = 0
    id_len = 3 if major == 2 else 4
    while pos + id_len + 4 <= len(body):
        fid_b = body[pos:pos + id_len]
        if not fid_b.strip(b"\x00") or not fid_b.isalnum():
            break
        fid = fid_b.decode("latin-1")
        if major == 2:
            fsize = int.from_bytes(body[pos + 3:pos + 6], "big")
            hdr = 6
        else:
            raw = body[pos + 4:pos + 8]
            fsize = _syncsafe(raw) if major == 4 else int.from_bytes(raw, "big")
            hdr = 10
        start = pos + hdr
        content = body[start:start + fsize]
        pos = start + fsize
        if fsize <= 0 or not content:
            continue

        if fid == "APIC" or fid == "PIC":
            try:
                enc = content[0]
                rest = content[1:]
                if fid == "PIC":  # v2.2 是 3 字符图片格式
                    mime = rest[:3].decode("latin-1").lower()
                    rest = rest[3:]
                else:
                    sep = rest.find(b"\x00")
                    if sep < 0:
                        continue
                    mime = rest[:sep].decode("latin-1").lower()
                    rest = rest[sep + 1:]
                if not rest:
                    continue
                ptype = rest[0]
                rest = rest[1:]
                enc_name = _ENC.get(enc, "latin-1")
                # 跳过描述字符串
                if enc in (1, 2):
                    end = 0
                    while end + 1 < len(rest):
                        if rest[end] == 0 and rest[end + 1] == 0:
                            end += 2
                            break
                        end += 2
                    rest = rest[end:]
                else:
                    sep = rest.find(b"\x00")
                    rest = rest[sep + 1:] if sep >= 0 else b""
                if rest and (apic is None or ptype == 3):
                    apic = (APIC_MIME.get(mime, "image/jpeg"), rest)
                    _ = enc_name
            except (IndexError, UnicodeDecodeError):
                pass
            continue

        key = FRAME_MAP.get(fid)
        if not key:
            continue
        try:
            enc = content[0]
            text = content[1:].decode(_ENC.get(enc, "latin-1"), errors="replace")
        except (IndexError, LookupError):
            continue
        text = text.replace("\x00", "").strip()
        if text and key not in tags:
            tags[key] = text
    return tags, apic


def _id3v1(data: bytes) -> dict:
    if len(data) < 128 or data[-128:-125] != b"TAG":
        return {}
    tail = data[-125:]
    out = {}
    for key, (a, b) in {"title": (0, 30), "artist": (30, 60), "album": (60, 90),
                        "year": (90, 94)}.items():
        val = tail[a:b].decode("latin-1", errors="replace").strip("\x00 ").strip()
        if val:
            out[key] = val
    return out


def read(path) -> dict:
    """返回 {title, artist, album, year, genre, cover_mime}；没读到的键不出现。"""
    p = Path(path)
    out: dict = {}
    try:
        with p.open("rb") as fh:
            head = fh.read(10)
            size = 0
            if head[:3] == b"ID3" and len(head) >= 10:
                size = _syncsafe(head[6:10]) + 10
            data = head + fh.read(min(size, MAX_TAG) if size else 0)
        tags, apic = _id3v2(data)
        if not tags:
            try:
                with p.open("rb") as fh:
                    fh.seek(max(0, p.stat().st_size - 128))
                    tags = _id3v1(fh.read(128))
            except OSError:
                pass
        out.update(tags)
        if apic:
            out["cover_mime"] = apic[0]
    except OSError:
        pass
    return out


def cover(path):
    """返回 (bytes, mime) 或 None。"""
    p = Path(path)
    try:
        with p.open("rb") as fh:
            head = fh.read(10)
            if head[:3] != b"ID3" or len(head) < 10:
                return None
            size = _syncsafe(head[6:10]) + 10
            data = head + fh.read(min(size, MAX_TAG))
    except OSError:
        return None
    _tags, apic = _id3v2(data)
    return apic if apic and len(apic[1]) > 100 else None
