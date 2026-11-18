from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.attachment import Attachment
from app.models.ocr_task import OcrTask
from app.services import attachment_storage
from app.services.ocr_provider import OcrProviderError, OcrProviderNotConfigured, recognize_image


MAX_ATTEMPTS = 5


def process_task(db: Session, task: OcrTask) -> OcrTask:
    """Process one durable task. Caller owns transaction and authorization."""
    if task.status == "confirmed":
        raise ValueError("已確認的 OCR 結果不可重新辨識")
    attachment = db.query(Attachment).filter(
        Attachment.id == task.attachment_id,
        Attachment.family_id == task.family_id,
        Attachment.is_voided.is_(False),
    ).first()
    if attachment is None:
        task.status = "failed"
        task.error_code = "ATTACHMENT_UNAVAILABLE"
        task.error_message = "附件不存在或已作廢"
        task.completed_at = datetime.now(timezone.utc)
        return task

    try:
        content = attachment_storage.download_object(attachment.object_key)
        import hashlib
        if hashlib.sha256(content).hexdigest() != attachment.sha256:
            raise ValueError("附件完整性驗證失敗")
        result = recognize_image(content, attachment.content_type)
        task.extracted_text = result["text"]
        task.suggested_fields = result["suggested_fields"]
        task.status = "succeeded"
    except Exception as exc:
        task.status = "failed"
        task.extracted_text = None
        task.suggested_fields = None
        task.error_code = type(exc).__name__[:80]
        if isinstance(exc, OcrProviderNotConfigured):
            task.error_message = "OCR 服務尚未設定，請聯絡系統管理員"
        elif isinstance(exc, OcrProviderError):
            task.error_message = "OCR 服務暫時無法完成辨識，請稍後重試"
        elif isinstance(exc, ValueError):
            task.error_message = "附件完整性驗證失敗"
        else:
            task.error_message = "OCR 執行失敗，請稍後重試"
    task.completed_at = datetime.now(timezone.utc)
    return task
