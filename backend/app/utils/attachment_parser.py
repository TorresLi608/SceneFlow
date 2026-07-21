from __future__ import annotations

import base64
import binascii
import io
import mimetypes
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePath
from urllib.parse import unquote_to_bytes
from xml.etree import ElementTree as ET


MAX_PARSED_ATTACHMENT_CHARS = 200_000

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".py",
    ".java",
    ".go",
    ".rs",
    ".php",
    ".rb",
    ".swift",
    ".kt",
    ".kts",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".env",
    ".log",
}

TEXT_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/yaml",
    "application/javascript",
    "application/typescript",
    "application/x-sh",
}


@dataclass(frozen=True)
class ParsedAttachment:
    text: str
    parsed: bool


class AttachmentParseError(ValueError):
    pass


def attachment_text_part(data: str, mime_type: str, filename: str) -> str:
    filename = filename.strip() or "file"
    mime_type = _mime_type(mime_type, filename)
    result = parse_attachment(data, mime_type, filename)
    if not result.parsed:
        return f"[Uploaded file: {filename}, {mime_type}]\n无法解析该文件：{result.text}"

    return f"<attachment name={filename!r} mime={mime_type!r}>\n{result.text}\n</attachment>"


def parse_attachment(data: str, mime_type: str, filename: str) -> ParsedAttachment:
    try:
        blob = _decode_data(data)
    except AttachmentParseError as exc:
        return ParsedAttachment(str(exc), False)

    ext = _extension(filename)
    try:
        if _is_text_file(mime_type, ext):
            return ParsedAttachment(_decode_text(blob), True)
        if ext == ".pdf" or mime_type == "application/pdf":
            return ParsedAttachment(_parse_pdf(blob), True)
        if ext == ".docx":
            return ParsedAttachment(_parse_docx(blob), True)
        if ext == ".xlsx":
            return ParsedAttachment(_parse_xlsx(blob), True)
        if ext == ".pptx":
            return ParsedAttachment(_parse_pptx(blob), True)
        if ext == ".odt":
            return ParsedAttachment(_parse_odt(blob), True)
        if ext in {".doc", ".xls", ".ppt"}:
            raise AttachmentParseError("旧版二进制 Office 文件暂不支持，请转换为 .docx/.xlsx/.pptx 后再上传。")
        if not _looks_binary(blob):
            return ParsedAttachment(_decode_text(blob), True)
        raise AttachmentParseError("当前格式不是可直接读取的文本、图片、PDF 或 Office OpenXML 文件。")
    except AttachmentParseError as exc:
        return ParsedAttachment(str(exc), False)
    except Exception as exc:
        return ParsedAttachment(f"解析失败：{exc}", False)


def _decode_data(data: str) -> bytes:
    data = data.strip()
    if not data:
        raise AttachmentParseError("文件内容为空。")
    try:
        if data.startswith("data:"):
            header, encoded = data.split(",", 1)
            if ";base64" in header:
                return base64.b64decode(encoded, validate=True)
            return unquote_to_bytes(encoded)
        return base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AttachmentParseError("文件内容不是有效的数据 URL。") from exc


def _mime_type(mime_type: str, filename: str) -> str:
    guessed = mimetypes.guess_type(filename)[0] or ""
    return (mime_type or guessed or "application/octet-stream").strip().lower()


def _extension(filename: str) -> str:
    return PurePath(filename).suffix.lower()


def _is_text_file(mime_type: str, ext: str) -> bool:
    return mime_type.startswith("text/") or mime_type in TEXT_MIME_TYPES or ext in TEXT_EXTENSIONS


def _looks_binary(blob: bytes) -> bool:
    sample = blob[:4096]
    if b"\x00" in sample:
        return True
    if not sample:
        return False
    control = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 13})
    return control / len(sample) > 0.2


def _decode_text(blob: bytes) -> str:
    if _looks_binary(blob):
        raise AttachmentParseError("文件看起来是二进制内容，无法按文本解析。")
    for encoding in ("utf-8-sig", "utf-16", "gb18030", "latin-1"):
        try:
            return _clip(blob.decode(encoding).strip())
        except UnicodeDecodeError:
            continue
    raise AttachmentParseError("无法识别文本编码。")


def _parse_pdf(blob: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise AttachmentParseError("缺少 pypdf 依赖，暂时无法解析 PDF。") from exc

    reader = PdfReader(io.BytesIO(blob))
    text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise AttachmentParseError("PDF 中没有可提取文本，可能是扫描件，需要 OCR。")
    return _clip(text)


def _parse_docx(blob: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = ["word/document.xml"]
        names.extend(sorted(name for name in zf.namelist() if re.match(r"word/(header|footer)\d+\.xml$", name)))
        parts = [_word_xml_text(zf.read(name)) for name in names if name in zf.namelist()]
    text = "\n\n".join(part for part in parts if part.strip()).strip()
    if not text:
        raise AttachmentParseError("Word 文档中没有可提取文本。")
    return _clip(text)


def _word_xml_text(xml_bytes: bytes) -> str:
    root = ET.fromstring(xml_bytes)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{ns}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{ns}t")).strip()
        if text:
            paragraphs.append(text)
    if paragraphs:
        return "\n".join(paragraphs)
    return "\n".join((node.text or "").strip() for node in root.iter(f"{ns}t") if (node.text or "").strip())


def _parse_xlsx(blob: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        shared_strings = _xlsx_shared_strings(zf)
        sheet_names = sorted(
            (name for name in zf.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", name)),
            key=_natural_key,
        )
        sheets = [_xlsx_sheet_text(zf.read(name), shared_strings, index + 1) for index, name in enumerate(sheet_names)]
    text = "\n\n".join(sheet for sheet in sheets if sheet.strip()).strip()
    if not text:
        raise AttachmentParseError("Excel 文件中没有可提取文本。")
    return _clip(text)


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    strings = []
    for item in root.iter(f"{ns}si"):
        strings.append("".join(node.text or "" for node in item.iter(f"{ns}t")))
    return strings


def _xlsx_sheet_text(xml_bytes: bytes, shared_strings: list[str], sheet_index: int) -> str:
    root = ET.fromstring(xml_bytes)
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rows = []
    for row in root.iter(f"{ns}row"):
        cells = []
        for cell in row.iter(f"{ns}c"):
            cells.append(_xlsx_cell_text(cell, shared_strings, ns))
        line = "\t".join(cell for cell in cells if cell != "").strip()
        if line:
            rows.append(line)
    return f"Sheet {sheet_index}\n" + "\n".join(rows) if rows else ""


def _xlsx_cell_text(cell: ET.Element, shared_strings: list[str], ns: str) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{ns}t")).strip()

    value = cell.find(f"{ns}v")
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        try:
            return shared_strings[int(value.text)].strip()
        except (ValueError, IndexError):
            return ""
    return value.text.strip()


def _parse_pptx(blob: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        slide_names = sorted(
            (name for name in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", name)),
            key=_natural_key,
        )
        slides = [_pptx_slide_text(zf.read(name), index + 1) for index, name in enumerate(slide_names)]
    text = "\n\n".join(slide for slide in slides if slide.strip()).strip()
    if not text:
        raise AttachmentParseError("PowerPoint 文件中没有可提取文本。")
    return _clip(text)


def _pptx_slide_text(xml_bytes: bytes, slide_index: int) -> str:
    root = ET.fromstring(xml_bytes)
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    lines = [(node.text or "").strip() for node in root.iter(f"{ns}t") if (node.text or "").strip()]
    return f"Slide {slide_index}\n" + "\n".join(lines) if lines else ""


def _parse_odt(blob: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        if "content.xml" not in zf.namelist():
            raise AttachmentParseError("ODT 文件缺少 content.xml。")
        root = ET.fromstring(zf.read("content.xml"))
    lines = ["".join(node.itertext()).strip() for node in root.iter() if node.tag.endswith("}p")]
    text = "\n".join(line for line in lines if line).strip()
    if not text:
        raise AttachmentParseError("ODT 文件中没有可提取文本。")
    return _clip(text)


def _natural_key(value: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]


def _clip(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_PARSED_ATTACHMENT_CHARS:
        return text
    return text[:MAX_PARSED_ATTACHMENT_CHARS] + "\n\n[内容过长，已截断]"
