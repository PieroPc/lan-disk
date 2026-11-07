"""Office 文档（docx / xlsx / pptx）轻量解析。

只依赖标准库：这几种格式本质都是 ZIP + OOXML，直接解包读 XML 就够用了，
不需要装 python-docx / openpyxl / python-pptx，也不依赖本机装 Office。

输出的是给前端渲染用的中性结构，不追求像素级还原，但保留
标题层级、粗斜体、列表、表格、图片、超链接、单元格类型与合并这些关键信息。
"""

from __future__ import annotations

import datetime as dt
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"

TRUE_VALS = ("1", "true", "on")


class BadFile(Exception):
    """文件损坏或不是预期的 OOXML。"""


# --------------------------------------------------------------------------
# 公共小工具
# --------------------------------------------------------------------------
def _on(el, attr: str = "val") -> bool:
    """OOXML 里 <w:b/>、<w:b w:val="0"/> 都合法，需要区分开关。"""
    if el is None:
        return False
    v = el.get(W + attr)
    return True if v is None else v.lower() in TRUE_VALS


def _luma(hex6: str) -> float:
    """粗略感知亮度，用来判断这个颜色在深/浅底上还看不看得见。"""
    try:
        n = int(hex6.lstrip("#"), 16)
    except ValueError:
        return 0.5
    r, g, b = (n >> 16) & 255, (n >> 8) & 255, n & 255
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _worth_color(val: str) -> bool:
    """接近纯黑/纯白的颜色一律丢掉——它只是"正文色"，用主题色更安全。"""
    v = (val or "").strip().lstrip("#")
    if len(v) != 6:
        return False
    return 0.2 < _luma(v) < 0.93


def _int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _rels(z: zipfile.ZipFile, part: str) -> dict:
    """读取某个 part 对应的 .rels，返回 {rId: 归一化后的 zip 内路径}。"""
    d, name = posixpath.split(part)
    rp = posixpath.join(d, "_rels", name + ".rels")
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(z.read(rp))
    except (KeyError, ET.ParseError):
        return out
    for rel in root:
        rid, tgt = rel.get("Id"), rel.get("Target") or ""
        if not rid:
            continue
        if rel.get("TargetMode") == "External":
            out[rid] = tgt
            continue
        if tgt.startswith("/"):
            out[rid] = tgt.lstrip("/")
        else:
            out[rid] = posixpath.normpath(posixpath.join(d, tgt))
    return out


def _main_part(z: zipfile.ZipFile, fallback_prefix: str, fallback_name: str) -> str:
    """找到主文档 part，兼容少数把 main part 改了名的文件。"""
    for n in z.namelist():
        if n == f"{fallback_prefix}/{fallback_name}":
            return n
    for n in z.namelist():
        if n.startswith(fallback_prefix + "/") and n.endswith(".xml") and "/_" not in n:
            return n
    raise BadFile("压缩包里找不到主文档")


def _xml(z: zipfile.ZipFile, name: str):
    try:
        return ET.fromstring(z.read(name))
    except KeyError:
        raise BadFile(f"缺少 {name}") from None
    except ET.ParseError as exc:
        raise BadFile(f"{name} 解析失败") from exc


# --------------------------------------------------------------------------
# Word (.docx)
# --------------------------------------------------------------------------
_BULLET_HINT = ("bullet", "•", "-", "·", "o", "Ø", "ü", "v")


def _docx_numbering(z: zipfile.ZipFile) -> dict:
    """numId -> {ilvl: (numFmt, lvlText)}，用来判断列表是有序还是无序。"""
    try:
        root = _xml(z, "word/numbering.xml")
    except BadFile:
        return {}
    abstract = {}
    for an in root.iter(W + "abstractNum"):
        aid = an.get(W + "abstractNumId")
        levels = {}
        for lvl in an.iter(W + "lvl"):
            fmt = lvl.find(W + "numFmt")
            txt = lvl.find(W + "lvlText")
            levels[_int(lvl.get(W + "ilvl"))] = (
                fmt.get(W + "val") if fmt is not None else "bullet",
                txt.get(W + "val") if txt is not None else "",
            )
        abstract[aid] = levels

    out = {}
    for num in root.iter(W + "num"):
        nid = num.get(W + "numId")
        ref = num.find(W + "abstractNumId")
        if ref is not None:
            out[nid] = abstract.get(ref.get(W + "val"), {})
    return out


def _docx_styles(z: zipfile.ZipFile) -> dict:
    """styleId -> (显示名, 大纲级别)。"""
    try:
        root = _xml(z, "word/styles.xml")
    except BadFile:
        return {}
    out = {}
    for st in root.iter(W + "style"):
        sid = st.get(W + "styleId")
        if not sid:
            continue
        name_el = st.find(W + "name")
        name = name_el.get(W + "val") if name_el is not None else sid
        ppr = st.find(W + "pPr")
        lvl = None
        if ppr is not None:
            ol = ppr.find(W + "outlineLvl")
            if ol is not None:
                lvl = _int(ol.get(W + "val"), -1)
        out[sid] = (name or sid, lvl)
    return out


def _docx_runs(el, rels: dict, media: set, fmt: dict) -> list:
    """把一段（可能含超链接、域、内容控件）拍平成 run 列表。"""
    runs: list = []
    for ch in el:
        tag = ch.tag
        if tag == W + "r":
            runs.extend(_docx_run(ch, rels, media))
        elif tag == W + "hyperlink":
            rid = ch.get(R + "id")
            href = rels.get(rid, "") if rid else ""
            for r in _docx_runs(ch, rels, media, fmt):
                if href and not href.startswith("#"):
                    r["href"] = href
                runs.append(r)
        elif tag in (W + "ins", W + "smartTag", W + "sdt", W + "sdtContent",
                     W + "fldSimple", W + "bdo", W + "dir"):
            runs.extend(_docx_runs(ch, rels, media, fmt))
    return runs


def _docx_run(r, rels: dict, media: set) -> list:
    rpr = r.find(W + "rPr")
    on = {"b": False, "i": False, "u": False, "s": False, "sz": None, "c": None}
    if rpr is not None:
        on["b"] = _on(rpr.find(W + "b"))
        on["i"] = _on(rpr.find(W + "i"))
        u = rpr.find(W + "u")
        on["u"] = u is not None and (u.get(W + "val") or "single") != "none"
        on["s"] = _on(rpr.find(W + "strike")) or _on(rpr.find(W + "dstrike"))
        sz = rpr.find(W + "sz")
        if sz is not None:
            on["sz"] = round(_int(sz.get(W + "val")) / 2, 1) or None
        c = rpr.find(W + "color")
        if c is not None:
            v = (c.get(W + "val") or "").lower()
            if v != "auto" and _worth_color(v):
                on["c"] = "#" + v
    out: list = []
    for ch in r:
        if ch.tag == W + "t":
            if ch.text:
                out.append({"t": ch.text, **on})
        elif ch.tag == W + "br":
            out.append({"t": "\n"})
        elif ch.tag == W + "tab":
            out.append({"t": "    "})
        elif ch.tag == W + "noBreakHyphen":
            out.append({"t": "-"})
        elif ch.tag == W + "drawing":
            for blip in ch.iter(A + "blip"):
                rid = blip.get(R + "embed") or blip.get(R + "link")
                if rid and rid in rels:
                    media.add(rels[rid])
                    out.append({"img": rels[rid]})
        elif ch.tag == W + "pict":  # 老式 VML 图片
            for im in ch.iter():
                rid = im.get(R + "id")
                if rid and rid in rels and "image" in rels[rid].lower():
                    media.add(rels[rid])
                    out.append({"img": rels[rid]})
    return out


def _heading_of(ppr, styles: dict) -> tuple:
    """返回 (级别 0-6, 是否为引用, 是否为代码)。"""
    level, quote, code = 0, False, False
    sid = ""
    if ppr is not None:
        ps = ppr.find(W + "pStyle")
        if ps is not None:
            sid = ps.get(W + "val") or ""
        ol = ppr.find(W + "outlineLvl")
        if ol is not None:
            lv = _int(ol.get(W + "val"), -1)
            if 0 <= lv <= 5:
                level = lv + 1
    name, style_lvl = styles.get(sid, ("", None))
    low = (name or "").lower()
    m = re.search(r"(?:heading|标题)\s*([1-9])", low)
    if m:
        level = level or int(m.group(1))
    elif low in ("title", "标题"):
        level = level or 1
    if "quote" in low or "引用" in low:
        quote = True
    if "preformatted" in low or "代码" in low or "htmlpre" in low:
        code = True
    return min(level, 6), quote, code


def _docx_para(p, rels: dict, media: set, numbering: dict, styles: dict) -> dict | None:
    ppr = p.find(W + "pPr")
    runs = [r for r in _docx_runs(p, rels, media, {}) if r.get("t") or r.get("img")]
    text = "".join(r["t"] for r in runs if "t" in r).strip()
    has_img = any("img" in r for r in runs)
    if not text and not has_img:
        return None

    level, quote, code = _heading_of(ppr, styles)
    align = None
    num = None
    if ppr is not None:
        jc = ppr.find(W + "jc")
        if jc is not None:
            j = jc.get(W + "val") or ""
            align = {"both": "justify", "distribute": "justify"}.get(j, j) or None
        npr = ppr.find(W + "numPr")
        if npr is not None:
            nid_el = npr.find(W + "numId")
            if nid_el is not None and (nid_el.get(W + "val") or "0") != "0":
                ilvl_el = npr.find(W + "ilvl")
                ilvl = _int(ilvl_el.get(W + "val")) if ilvl_el is not None else 0
                fmt = numbering.get(nid_el.get(W + "val"), {}).get(ilvl, ("bullet", ""))
                num = {
                    "level": ilvl,
                    "ordered": (fmt[0] or "bullet").lower() != "bullet",
                }

    if has_img and not text:
        for r in runs:
            if "img" in r:
                return {"t": "img", "src": r["img"]}
    block = {"t": "p", "runs": runs}
    if level:
        block["style"] = f"h{level}"
    elif quote:
        block["style"] = "quote"
    elif code:
        block["style"] = "code"
    if align:
        block["align"] = align
    if num:
        block["t"] = "li"
        block["ordered"] = num["ordered"]
        block["level"] = num["level"]
    return block


def _docx_cell(tc, rels: dict, media: set, numbering: dict, styles: dict) -> dict:
    parts, blocks = [], []
    for p in tc.iter(W + "p"):
        b = _docx_para(p, rels, media, numbering, styles)
        if not b:
            continue
        blocks.append(b)
        if b["t"] in ("p", "li"):
            parts.append("".join(r.get("t", "") for r in b["runs"]))
    colspan = 1
    tcpr = tc.find(W + "tcPr")
    if tcpr is not None:
        gs = tcpr.find(W + "gridSpan")
        if gs is not None:
            colspan = max(1, _int(gs.get(W + "val"), 1))
    head = any(r.get("b") for b in blocks for r in b.get("runs", []))
    return {"text": "\n".join(parts).strip(), "blocks": blocks,
            "colspan": colspan, "head": head}


def parse_docx(path) -> dict:
    with zipfile.ZipFile(path) as z:
        part = _main_part(z, "word", "document.xml")
        rels = _rels(z, part)
        numbering = _docx_numbering(z)
        styles = _docx_styles(z)
        root = _xml(z, part)
        body = root.find(W + "body")
        if body is None:
            raise BadFile("文档结构异常")

        media: set = set()
        blocks: list = []
        seen_tables = set()

        def walk(container):
            for child in container:
                tag = child.tag
                if tag == W + "p":
                    b = _docx_para(child, rels, media, numbering, styles)
                    if b:
                        blocks.append(b)
                elif tag == W + "tbl" and id(child) not in seen_tables:
                    seen_tables.add(id(child))
                    rows = []
                    for tr in child.findall(W + "tr"):
                        cells = [_docx_cell(tc, rels, media, numbering, styles)
                                 for tc in tr.findall(W + "tc")]
                        if cells:
                            rows.append(cells)
                    if rows:
                        blocks.append({"t": "table", "rows": rows})
                elif tag in (W + "sdt", W + "sdtContent", W + "customXml"):
                    walk(child)
                elif tag == W + "sectPr":
                    continue

        walk(body)

    for b in blocks:
        if b["t"] == "img":
            media.add(b["src"])
    return {"type": "word", "blocks": blocks, "media": sorted(media)}


# --------------------------------------------------------------------------
# Excel (.xlsx)
# --------------------------------------------------------------------------
_DATE_FMT_IDS = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))
_NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _xlsx_styles(z: zipfile.ZipFile) -> list:
    """返回 cellXfs 顺序的列表 [(是否日期, 是否百分比, 小数位)]。"""
    try:
        root = _xml(z, "xl/styles.xml")
    except BadFile:
        return []
    custom = {}
    for nf in root.iter(S + "numFmt"):
        custom[_int(nf.get("numFmtId"), -1)] = nf.get("formatCode") or ""
    out = []
    # 只取 cellXfs 里的 xf：cellStyleXfs 也含 <xf>，混进来会让样式索引整体错位
    cellxfs = root.find(S + "cellXfs")
    for xf in (cellxfs if cellxfs is not None else []):
        if xf.tag != S + "xf":
            continue
        fid = _int(xf.get("numFmtId"), 0)
        code = custom.get(fid, "")
        is_date = fid in _DATE_FMT_IDS
        is_pct = False
        if code:
            bare = re.sub(r'"[^"]*"|\[[^\]]*\]', "", code)
            if re.search(r"[yYdD]", bare) or re.search(r"[hH]:[mM]", bare):
                is_date = True
            is_pct = "%" in bare
        dec = 0
        m = re.search(r"\.(0+)", code)
        if m:
            dec = len(m.group(1))
        out.append((is_date, is_pct, dec))
    return out


def _xlsx_shared(z: zipfile.ZipFile) -> list:
    try:
        root = _xml(z, "xl/sharedStrings.xml")
    except BadFile:
        return []
    strings = []
    for si in root.iter(S + "si"):
        # 一个 si 里可能有多段富文本，还可能夹注音（rPh）
        pieces = []
        for node in si.iter():
            if node.tag == S + "t":
                pieces.append(node.text or "")
            elif node.tag == S + "rPh":
                pass
        strings.append("".join(pieces))
    return strings


def _col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return max(n - 1, 0)


def _col_name(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def _serial_to_date(v: float) -> str:
    # Excel 把 1900 年当闰年，序号 60 是虚构的 2/29，所以 61 之后要减一天
    base = dt.datetime(1899, 12, 30)
    days = int(v)
    frac = v - days
    if days >= 61:
        days -= 1
    d = base + dt.timedelta(days=days + 1)
    secs = int(round(frac * 86400))
    d = d + dt.timedelta(seconds=secs)
    if frac == 0:
        return d.strftime("%Y-%m-%d")
    if days == 0:
        return d.strftime("%H:%M:%S")
    return d.strftime("%Y-%m-%d %H:%M")


def _fmt_number(raw: str) -> str:
    if raw is None:
        return ""
    raw = raw.strip()
    if not _NUM_RE.match(raw):
        return raw
    try:
        f = float(raw)
    except ValueError:
        return raw
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    if abs(f) >= 1e15 or (0 < abs(f) < 1e-9):
        return f"{f:.6e}".replace("e+0", "e+").replace("e-0", "e-")
    return f"{f:.10f}".rstrip("0").rstrip(".")


def parse_xlsx(path, max_rows: int = 2000, max_cols: int = 80) -> dict:
    with zipfile.ZipFile(path) as z:
        wb = _xml(z, "xl/workbook.xml")
        rels = _rels(z, "xl/workbook.xml")
        shared = _xlsx_shared(z)
        style_list = _xlsx_styles(z)

        sheets = []
        for sh in wb.iter(S + "sheet"):
            name = sh.get("name") or "Sheet"
            rid = sh.get(R + "id")
            target = rels.get(rid) or ""
            if not target or not target.endswith(".xml"):
                continue
            try:
                ws = _xml(z, target)
            except BadFile:
                continue

            merges = []
            mc = ws.find(S + "mergeCells")
            if mc is not None:
                for m in mc:
                    ref = m.get("ref") or ""
                    if ":" in ref:
                        a, b = ref.split(":", 1)
                        merges.append((_col_index(a), _int(re.sub(r"\D", "", a), 1) - 1,
                                       _col_index(b), _int(re.sub(r"\D", "", b), 1) - 1))

            grid: dict = {}
            max_r = max_c = 0
            truncated = False
            data = ws.find(S + "sheetData")
            rows_iter = list(data) if data is not None else []
            for r_i, row in enumerate(rows_iter):
                if r_i >= max_rows:
                    truncated = True
                    break
                for c in row:
                    if c.tag != S + "c":
                        continue
                    ref = c.get("r") or ""
                    ci = _col_index(ref)
                    ri = _int(c.get("r") and re.sub(r"\D", "", c.get("r")), r_i + 1) - 1
                    if ci >= max_cols:
                        truncated = True
                        continue
                    t = c.get("t") or "n"
                    v_el = c.find(S + "v")
                    raw = v_el.text if v_el is not None else None
                    val, align = "", "left"
                    if t == "s":
                        try:
                            val = shared[int(raw)]
                        except (TypeError, ValueError, IndexError):
                            val = ""
                    elif t == "inlineStr":
                        is_el = c.find(S + "is")
                        val = "".join(x.text or "" for x in is_el.iter(S + "t")) if is_el is not None else ""
                    elif t == "b":
                        val = "TRUE" if raw == "1" else "FALSE"
                        align = "center"
                    elif t == "e":
                        val = raw or "#ERR"
                        align = "center"
                    elif t == "str":
                        val = raw or ""
                    else:
                        is_date, is_pct, dec = (False, False, 0)
                        si = _int(c.get("s"), -1)
                        if 0 <= si < len(style_list):
                            is_date, is_pct, dec = style_list[si]
                        if raw is None or raw == "":
                            val = ""
                        elif is_date:
                            try:
                                val = _serial_to_date(float(raw))
                            except ValueError:
                                val = raw
                            align = "right"
                        elif is_pct:
                            try:
                                val = f"{float(raw) * 100:.{dec or 0}f}%"
                            except ValueError:
                                val = raw
                            align = "right"
                        else:
                            val = _fmt_number(raw)
                            align = "right"
                    if val == "":
                        continue
                    grid[(ri, ci)] = {"v": val, "a": align, "n": t != "s" and t != "inlineStr"}
                    max_r = max(max_r, ri + 1)
                    max_c = max(max_c, ci + 1)

            # 合并单元格：左上角存 rowspan/colspan，其余标记为跳过
            for c1, r1, c2, r2 in merges:
                if r1 > c1 and c2 > r2:  # 防呆：ref 顺序正常
                    pass
                anchor = grid.get((r1, c1))
                rs, cs = r2 - r1 + 1, c2 - c1 + 1
                if anchor is None:
                    anchor = {"v": "", "a": "left", "n": False}
                    grid[(r1, c1)] = anchor
                    max_r = max(max_r, r2 + 1)
                    max_c = max(max_c, c2 + 1)
                anchor["rs"] = rs
                anchor["cs"] = cs
                for rr in range(r1, r2 + 1):
                    for cc in range(c1, c2 + 1):
                        if (rr, cc) == (r1, c1):
                            continue
                        grid[(rr, cc)] = {"skip": True}

            rows = []
            for ri in range(max_r):
                line = []
                for ci in range(max_c):
                    cell = grid.get((ri, ci))
                    if cell is None:
                        line.append(None)
                    elif cell.get("skip"):
                        line.append({"skip": True})
                    else:
                        line.append(cell)
                rows.append(line)

            sheets.append({
                "name": name,
                "rows": rows,
                "cols": [_col_name(i) for i in range(max_c)],
                "truncated": truncated,
            })

    if not sheets:
        raise BadFile("工作簿里没有可读的工作表")
    return {"type": "excel", "sheets": sheets}


# --------------------------------------------------------------------------
# PowerPoint (.pptx)
# --------------------------------------------------------------------------
def _pptx_text(txbody, rels: dict, media: set) -> list:
    lines = []
    for p in txbody.findall(A + "p"):
        paras = []
        lvl = 0
        ppr = p.find(A + "pPr")
        if ppr is not None:
            lvl = _int(ppr.get("lvl"), 0)
        for r in p:
            if r.tag == A + "r":
                t = r.find(A + "t")
                if t is None or not t.text:
                    continue
                rpr = r.find(A + "rPr")
                item = {"t": t.text}
                if rpr is not None:
                    # DrawingML 的 b / i / sz 是 rPr 上的属性，不是子元素
                    if (rpr.get("b") or "").lower() in TRUE_VALS:
                        item["b"] = True
                    if (rpr.get("i") or "").lower() in TRUE_VALS:
                        item["i"] = True
                    sz = rpr.get("sz")
                    if sz:
                        item["sz"] = round(_int(sz) / 100, 1) or None
                    sf = rpr.find(A + "solidFill")
                    if sf is not None:
                        clr = sf.find(A + "srgbClr")
                        if clr is not None and _worth_color(clr.get("val") or ""):
                            item["c"] = "#" + clr.get("val")
                paras.append(item)
            elif r.tag == A + "br":
                paras.append({"t": "\n"})
            elif r.tag == A + "fld":
                t = r.find(A + "t")
                if t is not None and t.text:
                    paras.append({"t": t.text})
        if paras:
            lines.append({"lvl": lvl, "runs": paras})
    return lines


def _pptx_table(tbl, rels: dict, media: set) -> dict:
    rows = []
    for tr in tbl.findall(A + "tr"):
        cells = []
        for tc in tr.findall(A + "tc"):
            body = tc.find(A + "txBody")
            text = ""
            if body is not None:
                text = "\n".join(
                    "".join(t.text or "" for t in p.iter(A + "t"))
                    for p in body.findall(A + "p")
                ).strip()
            span = 1
            if tc.get("gridSpan"):
                span = _int(tc.get("gridSpan"), 1)
            cells.append({"text": text, "colspan": span})
        if cells:
            rows.append(cells)
    return {"rows": rows}


def _slide_bg(root) -> str | None:
    bg = root.find(f"{P}cSld/{P}bg")
    if bg is None:
        return None
    for clr in bg.iter(A + "srgbClr"):
        if clr.get("val"):
            return "#" + clr.get("val")
    return None


def parse_pptx(path, max_slides: int = 200) -> dict:
    slides = []
    with zipfile.ZipFile(path) as z:
        rels = _rels(z, "ppt/presentation.xml")
        pres = _xml(z, "ppt/presentation.xml")
        order = []
        lst = pres.find(f"{P}sldIdLst")
        if lst is not None:
            for sid in lst.findall(P + "sldId"):
                target = rels.get(sid.get(R + "id"))
                if target:
                    order.append(target)
        if not order:
            order = sorted(n for n in z.namelist()
                           if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))

        for idx, part in enumerate(order[:max_slides]):
            try:
                root = _xml(z, part)
            except BadFile:
                continue
            srels = _rels(z, part)
            media: set = set()
            title = ""
            blocks, images, tables = [], [], []
            tree = root.find(f"{P}cSld/{P}spTree")
            shapes = list(tree) if tree is not None else []

            def walk_shapes(items):
                nonlocal title
                for node in items:
                    tag = node.tag
                    if tag == P + "sp":
                        ph = node.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
                        ph_type = ph.get("type") if ph is not None else ""
                        body = node.find(P + "txBody")
                        if body is None:
                            continue
                        lines = _pptx_text(body, srels, media)
                        if not lines:
                            continue
                        if ph_type in ("title", "ctrTitle") and not title:
                            title = "".join(r.get("t", "") for ln in lines
                                            for r in ln["runs"]).strip()
                            blocks.append({"type": "title", "lines": lines})
                        elif ph_type in ("ftr", "sldNum", "dt"):
                            continue
                        else:
                            blocks.append({"type": "body", "lines": lines})
                    elif tag == P + "pic":
                        for blip in node.iter(A + "blip"):
                            rid = blip.get(R + "embed")
                            if rid and rid in srels:
                                media.add(srels[rid])
                                images.append(srels[rid])
                                blocks.append({"type": "pic", "src": srels[rid]})
                    elif tag == P + "graphicFrame":
                        tbl = node.find(f".//{A}tbl")
                        if tbl is not None:
                            parsed = _pptx_table(tbl, srels, media)
                            tables.append(parsed)
                            blocks.append({"type": "table", "table": parsed})
                    elif tag == P + "grpSp":
                        walk_shapes(list(node))

            walk_shapes(shapes)
            if not title:
                for b in blocks:
                    if b["type"] == "body":
                        title = "".join(r.get("t", "") for r in b["lines"][0]["runs"]).strip()
                        break
            slides.append({
                "index": idx + 1,
                "title": title or f"第 {idx + 1} 页",
                "bg": _slide_bg(root),
                "blocks": blocks,
                "images": images,
                "tables": tables,
            })

    if not slides:
        raise BadFile("演示文稿里没有幻灯片")
    return {"type": "ppt", "slides": slides,
            "truncated": len(order) > max_slides}


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
PARSERS = {
    ".docx": parse_docx,
    ".docm": parse_docx,
    ".xlsx": parse_xlsx,
    ".xlsm": parse_xlsx,
    ".pptx": parse_pptx,
    ".pptm": parse_pptx,
}


def parse(path) -> dict:
    from pathlib import Path

    p = Path(path)
    fn = PARSERS.get(p.suffix.lower())
    if not fn:
        raise BadFile(f"不支持预览 {p.suffix}")
    try:
        return fn(p)
    except zipfile.BadZipFile:
        raise BadFile("文件不是有效的 Office 压缩包") from None
