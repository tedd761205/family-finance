import hashlib
import os
import uuid
from urllib.parse import urlsplit

import boto3
from botocore.config import Config


class AttachmentStorageNotConfigured(RuntimeError):
    pass


def _client():
    endpoint = os.getenv("ATTACHMENT_STORAGE_ENDPOINT_URL")
    access_key = os.getenv("ATTACHMENT_STORAGE_ACCESS_KEY_ID")
    secret_key = os.getenv("ATTACHMENT_STORAGE_SECRET_ACCESS_KEY")
    if not endpoint or not access_key or not secret_key:
        raise AttachmentStorageNotConfigured(
            "附件物件儲存尚未設定，請設定 ATTACHMENT_STORAGE_* 環境變數"
        )
    parsed_endpoint = urlsplit(endpoint)
    if (
        parsed_endpoint.scheme != "https"
        or not parsed_endpoint.hostname
        or parsed_endpoint.username
        or parsed_endpoint.password
        or parsed_endpoint.query
        or parsed_endpoint.fragment
        or parsed_endpoint.path not in ("", "/")
    ):
        raise AttachmentStorageNotConfigured(
            "附件物件儲存端點必須是有效的 HTTPS API 根網址"
        )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.getenv("ATTACHMENT_STORAGE_REGION", "auto"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


def _bucket() -> str:
    value = os.getenv("ATTACHMENT_STORAGE_BUCKET")
    if not value:
        raise AttachmentStorageNotConfigured(
            "附件物件儲存尚未設定 ATTACHMENT_STORAGE_BUCKET"
        )
    return value


def upload_object(object_key: str, content: bytes, content_type: str, sha256: str) -> None:
    _client().put_object(
        Bucket=_bucket(),
        Key=object_key,
        Body=content,
        ContentLength=len(content),
        ContentType=content_type,
        Metadata={"sha256": sha256},
    )


def download_object(object_key: str) -> bytes:
    response = _client().get_object(Bucket=_bucket(), Key=object_key)
    try:
        return response["Body"].read()
    finally:
        response["Body"].close()


def delete_object(object_key: str) -> None:
    _client().delete_object(Bucket=_bucket(), Key=object_key)



def check_storage_connection() -> None:
    """Verify credentials and bucket using a short-lived private object."""
    client = _client()
    bucket = _bucket()
    content = b"family-finance-attachment-storage-check"
    digest = hashlib.sha256(content).hexdigest()
    key = f"system-checks/{uuid.uuid4().hex}.txt"
    uploaded = False
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentLength=len(content),
            ContentType="text/plain",
            Metadata={"sha256": digest},
        )
        uploaded = True
        response = client.get_object(Bucket=bucket, Key=key)
        try:
            downloaded = response["Body"].read()
        finally:
            response["Body"].close()
        if hashlib.sha256(downloaded).hexdigest() != digest:
            raise RuntimeError("附件儲存連線測試的完整性驗證失敗")
    finally:
        if uploaded:
            client.delete_object(Bucket=bucket, Key=key)
