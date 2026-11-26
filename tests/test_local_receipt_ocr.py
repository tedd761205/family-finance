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
    assert 'id="local-receipt-type"' in page.text
    assert 'id="local-receipt-merchant"' in page.text
    assert 'id="local-receipt-amount"' in page.text
    assert 'id="local-receipt-date"' in page.text
    assert "不會上傳照片" in page.text
    assert "會使用網路流量" in page.text
    assert script.status_code == 200


def test_local_receipt_ocr_runs_in_browser_without_cloud_ocr_or_attachment_upload():
    with TestClient(app) as client:
        script = client.get("/static/local-receipt-ocr.js").text

    assert 'tesseract.createWorker(["chi_tra", "eng"]' in script
    assert "currentWorker.recognize(ocrCanvas)" in script
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

    assert "FamilyReceiptParser.parseReceiptData" in script
    assert "renderReview(parsedFields)" in script
    assert "hasReviewData()" in script
    assert 'transaction-amount' in script
    assert 'transaction-date' in script
    assert 'transaction-reference' in script
    assert 'transaction-form-panel' in script
    assert "新增紀錄" in page.text
    assert "自動建立支出" in page.text
    assert 'id="local-receipt-fill"' in page.text
    assert "買方統一編號" in page.text


def test_local_receipt_ocr_limits_image_types_and_size():
    with TestClient(app) as client:
        script = client.get("/static/local-receipt-ocr.js").text
        page = client.get("/")

    assert "MAX_FILE_BYTES = 10 * 1024 * 1024" in script
    assert 'image/jpeg,image/png,image/webp' in page.text
    assert "PDF 與其他格式尚未開放" in script

def test_camera_or_photo_picker_return_restores_receipt_workspace_after_page_reload():
    with TestClient(app) as client:
        app_script = client.get("/static/app.js").text
        ocr_script = client.get("/static/local-receipt-ocr.js").text

    assert "RECEIPT_CAPTURE_RETURN_KEY" in app_script
    assert "readReceiptCaptureReturn()" in app_script
    assert "pendingReceiptReturn.familyId" in app_script
    assert "await showTransactions()" in app_script
    assert "window.prepareReceiptCaptureReturn" in ocr_script
    assert "window.clearReceiptCaptureReturn" in ocr_script
    assert 'addEventListener("cancel"' in ocr_script
    assert "window.__familyReceiptPhotoReturned = true" in ocr_script
    assert "不會上傳照片" in ocr_script or "照片不會傳送到伺服器或 Google" in ocr_script

def test_paper_einvoice_uses_full_frame_multi_qr_detection_and_local_pair_validation():
    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/static/local-receipt-ocr.js")

    assert page.status_code == 200
    assert 'id="local-receipt-invoice-scan"' in page.text
    assert 'id="local-receipt-invoice-video"' in page.text
    assert 'id="local-receipt-left-guide"' not in page.text
    assert 'id="local-receipt-right-guide"' not in page.text
    assert "不必分左右、不必拿正" in page.text
    assert "整張發票進入畫面即可" in page.text

    assert "navigator.mediaDevices.getUserMedia" in script.text
    assert "function preferredRearCamera(devices, rememberedId = \"\", activeDeviceId = \"\")" in script.text
    assert "main|primary|standard|normal|主鏡頭" in script.text
    assert "back|rear|facing back|後置" in script.text
    assert "function isUltraWideCameraLabel(label)" in script.text
    assert "video.deviceId = { exact: deviceId }" in script.text
    assert 'id="local-receipt-invoice-camera-select"' in page.text
    assert 'id="local-receipt-invoice-zoom"' in page.text
    assert "getCapabilities?.()" in script.text
    assert "applyConstraints({ advanced: [{ zoom }] })" in script.text
    assert "function acceptInvoiceQrPayload(value)" in script.text
    assert "parseTaiwanInvoiceQr(raw, null)" in script.text
    assert 'raw.startsWith("**")' in script.text
    assert "new api.BarcodeDetectorPolyfill({ formats: formats || [\"qr_code\"] })" in script.text
    assert "invoiceBarcodeDetector.detect(invoiceVideo)" in script.text
    assert "ZBAR_WASM_SRC" in script.text
    assert "BARCODE_POLYFILL_SRC" in script.text
    assert "const detected = await detector.detect(canvas)" in script.text
    assert "horizontal or vertical" in script.text or "orientation" in script.text
    assert "window.setInterval(scanInvoiceCameraFrame, 220)" in script.text
    assert "function configureInvoiceCameraTrack(track)" in script.text
    assert "advanced.zoom = Math.min(maxZoom, Math.max(minZoom, 1))" in script.text
    assert "INVOICE_CAMERA_STORAGE_KEY" in script.text
    assert "rememberInvoiceCameraId(invoiceCameraSelect.value)" in script.text
    assert "The ZBar detector above scans the whole invoice" in script.text
    assert "Classify by payload content, not screen side" in script.text
    assert "async function captureAndDecodeInvoicePhoto()" in script.text
    assert "const codes = await decodeLocalCodes(file)" in script.text
    assert 'id="local-receipt-invoice-capture"' in page.text
    assert "拍照補掃（備用）" in page.text
    assert "MAX_BARCODE_IMAGE_EDGE = 2600" in script.text
    assert "workspace.scrollIntoView({ behavior: \"smooth\", block: \"start\" })" in script.text
    assert 'inversionAttempts: "attemptBoth"' in script.text
    assert "parseTaiwanInvoiceQr(leftValue, rightValue)" in script.text
    assert "handleFile(file, codes)" in script.text


def test_live_invoice_camera_stops_cleanly_and_keeps_receipt_photo_fallback():
    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/static/local-receipt-ocr.js")

    assert 'id="local-receipt-camera"' in page.text
    assert 'id="local-receipt-choose"' in page.text
    assert "一般收據：拍照辨識" in page.text
    assert "選擇照片／收據" in page.text
    assert "track.stop()" in script.text
    assert 'addEventListener("visibilitychange"' in script.text
    assert 'addEventListener("pagehide"' in script.text
    assert "相機權限未開啟" in script.text
    assert "不會上傳照片" in page.text or "照片不會傳送到伺服器或 Google" in script.text

