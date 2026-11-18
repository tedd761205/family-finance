"""Google Cloud Vision OCR adapter. No provider key means OCR stays safely disabled."""
import base64
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OcrProviderNotConfigured(RuntimeError):
    pass


class OcrProviderError(RuntimeError):
    pass


def _suggest_fields(text: str) -> dict:
    """Conservative hints only; values are never persisted to bills automatically."""
    result = {}
    dates = re.findall(r"(?<!\d)(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?", text)
    if dates:
        y, m, d = dates[0]
        result["date_candidate"] = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    amounts = re.findall(r"(?:NT\$|NTD|TWD|\$|金額|應繳|合計|總計)[：:\s]*([0-9,]+(?:\.[0-9]{1,2})?)", text, re.I)
    if amounts:
        result["amount_candidate"] = amounts[-1].replace(",", "")
    number = re.search(r"(?:帳單編號|繳款編號|單據號碼|Bill\s*No\.?)[：:\s]*([A-Z0-9-]{4,})", text, re.I)
    if number:
        result["bill_number_candidate"] = number.group(1)
    return result


def recognize_image(content: bytes, content_type: str) -> dict:
    api_key = os.getenv("GOOGLE_CLOUD_VISION_API_KEY")
    if not api_key:
        raise OcrProviderNotConfigured("尚未設定 GOOGLE_CLOUD_VISION_API_KEY")
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise OcrProviderError("不支援的 OCR 圖片格式")

    body = {
        "requests": [{
            "image": {"content": base64.b64encode(content).decode("ascii")},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": {"languageHints": ["zh-TW", "en"]},
        }]
    }
    request = Request(
        "https://vision.googleapis.com/v1/images:annotate?key=" + api_key,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
    except HTTPError as exc:
        # Do not expose provider response or API key in application errors/logs.
        raise OcrProviderError(f"OCR_PROVIDER_HTTP_{exc.code}") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise OcrProviderError("OCR_PROVIDER_UNAVAILABLE") from exc

    responses = payload.get("responses") or []
    if not responses:
        raise OcrProviderError("OCR_EMPTY_RESPONSE")
    error = responses[0].get("error")
    if error:
        raise OcrProviderError("OCR_PROVIDER_REJECTED")
    text = (responses[0].get("fullTextAnnotation") or {}).get("text", "").strip()
    if not text:
        raise OcrProviderError("OCR_NO_TEXT")
    return {"text": text[:100000], "suggested_fields": _suggest_fields(text)}
