import os

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
