from io import BytesIO
from types import SimpleNamespace

import pytest


def test_storage_client_requires_https_root_endpoint(monkeypatch):
    from app.services import attachment_storage

    monkeypatch.setenv("ATTACHMENT_STORAGE_ENDPOINT_URL", "http://example.com")
    monkeypatch.setenv("ATTACHMENT_STORAGE_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("ATTACHMENT_STORAGE_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("ATTACHMENT_STORAGE_BUCKET", "private-test-bucket")

    with pytest.raises(attachment_storage.AttachmentStorageNotConfigured):
        attachment_storage._client()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com/path",
        "https://user:password@example.com",
        "https://example.com?redirect=1",
        "https:///missing-host",
    ],
)
def test_storage_client_rejects_non_root_or_credentialed_endpoint(monkeypatch, endpoint):
    from app.services import attachment_storage

    monkeypatch.setenv("ATTACHMENT_STORAGE_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("ATTACHMENT_STORAGE_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("ATTACHMENT_STORAGE_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("ATTACHMENT_STORAGE_BUCKET", "private-test-bucket")

    with pytest.raises(attachment_storage.AttachmentStorageNotConfigured):
        attachment_storage._client()


def test_storage_connection_probe_uploads_reads_verifies_and_deletes(monkeypatch):
    from app.services import attachment_storage

    calls = []
    stored = {}

    class Body:
        def __init__(self, value):
            self.value = value

        def read(self):
            return self.value

        def close(self):
            calls.append("close")

    class FakeClient:
        def put_object(self, **kwargs):
            calls.append("put")
            stored[kwargs["Key"]] = kwargs["Body"]

        def get_object(self, **kwargs):
            calls.append("get")
            return {"Body": Body(stored[kwargs["Key"]])}

        def delete_object(self, **kwargs):
            calls.append("delete")
            stored.pop(kwargs["Key"], None)

    monkeypatch.setattr(attachment_storage, "_client", lambda: FakeClient())
    monkeypatch.setattr(attachment_storage, "_bucket", lambda: "private-test-bucket")

    attachment_storage.check_storage_connection()

    assert calls == ["put", "get", "close", "delete"]
    assert stored == {}


def test_storage_connection_probe_deletes_object_after_read_failure(monkeypatch):
    from app.services import attachment_storage

    calls = []

    class Body:
        def read(self):
            return b"wrong content"

        def close(self):
            calls.append("close")

    class FakeClient:
        def put_object(self, **kwargs):
            calls.append("put")

        def get_object(self, **kwargs):
            return {"Body": Body()}

        def delete_object(self, **kwargs):
            calls.append("delete")

    monkeypatch.setattr(attachment_storage, "_client", lambda: FakeClient())
    monkeypatch.setattr(attachment_storage, "_bucket", lambda: "private-test-bucket")

    with pytest.raises(RuntimeError, match="完整性驗證失敗"):
        attachment_storage.check_storage_connection()

    assert calls == ["put", "close", "delete"]
