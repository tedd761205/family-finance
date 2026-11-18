from fastapi.testclient import TestClient
from main import app


def test_attachment_ocr_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert 'id="open-attachments"' in response.text
    assert 'id="attachments-view"' in response.text
    assert 'id="attachment-upload-form"' in response.text
    assert 'id="attachment-target-record"' in response.text
    assert 'id="ocr-result-panel"' in response.text


def test_attachment_workspace_uses_scoped_private_attachment_endpoints():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
    assert '"/attachments?"+params.toString()' in javascript
    assert '"/attachments/"+row.id+"/content?family_id="+selectedFamilyId' in javascript
    assert '"/attachments?"+params.toString()' in javascript
    assert 'formData.append("file",file)' in javascript
    assert 'Authorization:"Bearer "+token()' in javascript


def test_ocr_workspace_uses_task_lifecycle_without_auto_writing_financial_records():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
    assert '"/ocr/tasks?attachment_id="+row.id+"&family_id="+selectedFamilyId' in javascript
    assert '"/ocr/tasks/"+task.id+"/process?family_id="+selectedFamilyId' in javascript
    assert '"/ocr/tasks/"+task.id+"/retry?family_id="+selectedFamilyId' in javascript
    assert '"/ocr/tasks/"+task.id+"/confirm?family_id="+selectedFamilyId' in javascript
    assert "正式帳單與交易未被修改" in javascript


def test_ocr_result_is_rendered_as_text_not_html():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
    assert '$("ocr-extracted-text").textContent=task.extracted_text' in javascript
    assert 'pre.textContent=JSON.stringify(task.suggested_fields,null,2)' in javascript


def test_attachment_ocr_mobile_layout_and_provider_notice():
    with TestClient(app) as client:
        response = client.get("/")
        css = client.get("/static/styles.css").text
    assert "OCR 服務尚需 Google Cloud Vision API 設定" in response.text
    assert ".attachment-target-grid" in css
    assert ".attachment-admin-card" in css
