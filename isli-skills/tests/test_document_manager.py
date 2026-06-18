import pytest
from isli_skills.document_manager import generate_pdf, generate_docx, generate_xlsx, HAS_WEASYPRINT

@pytest.mark.skipif(not HAS_WEASYPRINT, reason="weasyprint dependencies missing")
def test_generate_pdf():
    content = "# Test PDF\n\nThis is a test PDF generation."
    pdf_bytes = generate_pdf(content)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")

def test_generate_docx():
    content = "# Test DOCX\n\nThis is a test DOCX generation.\n- Item 1\n- Item 2"
    docx_bytes = generate_docx(content)
    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 0
    # DOCX files are zip files starting with PK
    assert docx_bytes.startswith(b"PK")

def test_generate_xlsx():
    data = [
        {"Name": "Alice", "Age": 30},
        {"Name": "Bob", "Age": 25}
    ]
    xlsx_bytes = generate_xlsx(data)
    assert isinstance(xlsx_bytes, bytes)
    assert len(xlsx_bytes) > 0
    # XLSX files are also zip files starting with PK
    assert xlsx_bytes.startswith(b"PK")

def test_generate_xlsx_list():
    data = [
        ["Name", "Age"],
        ["Alice", 30],
        ["Bob", 25]
    ]
    xlsx_bytes = generate_xlsx(data)
    assert isinstance(xlsx_bytes, bytes)
    assert len(xlsx_bytes) > 0
    assert xlsx_bytes.startswith(b"PK")
