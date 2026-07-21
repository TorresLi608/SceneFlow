from __future__ import annotations

from pathlib import Path
import tempfile

from docx import Document
from pypdf import PdfReader

from app.services.artifact_service import create_docx, create_pdf, parse_markdown_blocks


SAMPLE = """# 摘要
SceneFlow 可以把创意内容转换为可下载文件。

## 能力
- 生成图片
- 生成 PDF
1. 选择模型
2. 调用工具
"""


def test_markdown_blocks() -> None:
    blocks = parse_markdown_blocks(SAMPLE)
    assert [block.kind for block in blocks] == ["h1", "body", "h2", "bullet", "bullet", "number", "number"]


def test_document_generation() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pdf_path = root / "sample.pdf"
        docx_path = root / "sample.docx"
        create_pdf(pdf_path, "SceneFlow 功能说明", SAMPLE)
        create_docx(docx_path, "SceneFlow 功能说明", SAMPLE)

        assert pdf_path.stat().st_size > 1_000
        assert len(PdfReader(pdf_path).pages) >= 1
        document = Document(docx_path)
        assert document.core_properties.title == "SceneFlow 功能说明"
        assert any("生成图片" in paragraph.text for paragraph in document.paragraphs)


if __name__ == "__main__":
    test_markdown_blocks()
    test_document_generation()
