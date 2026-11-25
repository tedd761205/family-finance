from fastapi.testclient import TestClient

from main import app


def test_local_receipt_ocr_pilot_is_available_in_transaction_workspace():
    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/static/local-receipt-ocr.js")

    assert page.status_code == 200
    assert 'id="local-receipt-camera-input"' in page.text
    assert 'id="local-receipt-file-input"' in page.text
    assert 'id="local-receipt-workspace"' in page.text
    assert "不會上傳照片" in page.text
    assert "會使用網路流量" in page.text
    assert script.status_code == 200


def test_local_receipt_ocr_runs_in_browser_without_cloud_ocr_or_attachment_upload():
    with TestClient(app) as client:
        script = client.get("/static/local-receipt-ocr.js").text

    assert 'tesseract.createWorker("chi_tra+eng"' in script
    assert "worker.recognize(file)" in script
    assert "BarcodeDetector" in script
    assert "jsQR" in script
    assert "/ocr/tasks" not in script
    assert "/attachments" not in script
    assert "GOOGLE_CLOUD_VISION_API_KEY" not in script
    assert "FormData" not in script
    assert "XMLHttpRequest" not in script
    assert "fetch(" not in script


def test_local_receipt_ocr_only_suggests_fields_and_requires_manual_transaction_submit():
    with TestClient(app) as client:
        script = client.get("/static/local-receipt-ocr.js").text
        page = client.get("/")

    assert "extractCandidates" in script
    assert 'transaction-amount' in script
    assert 'transaction-date' in script
    assert 'transaction-reference' in script
    assert 'transaction-form-panel' in script
    assert "新增紀錄" in page.text
    assert "自動建立支出" in page.text


def test_local_receipt_ocr_limits_image_types_and_size():
    with TestClient(app) as client:
        script = client.get("/static/local-receipt-ocr.js").text
        page = client.get("/")

    assert "MAX_FILE_BYTES = 10 * 1024 * 1024" in script
    assert 'image/jpeg,image/png,image/webp' in page.text
    assert "PDF 與其他格式尚未開放" in script
