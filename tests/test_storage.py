"""Tests del wrapper de object storage."""

import pytest
from botocore.exceptions import ClientError

from cip.storage import ObjectStorage


def client_error(code: str, status_code: int) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        },
        "HeadObject",
    )


class FakeS3Client:
    def __init__(self, head_error: ClientError | None = None) -> None:
        self.head_error = head_error
        self.presigned_call: dict[str, object] | None = None

    def head_object(self, **kwargs: str) -> None:
        if self.head_error is not None:
            raise self.head_error

    def generate_presigned_url(
        self,
        client_method: str,
        **kwargs: object,
    ) -> str:
        self.presigned_call = {
            "client_method": client_method,
            **kwargs,
        }
        return "http://minio:9000/pubmed-raw/pubmed/12/123.xml?signature=test"


def make_storage(client: FakeS3Client) -> ObjectStorage:
    storage = ObjectStorage.__new__(ObjectStorage)
    storage.bucket = "pubmed-raw"
    storage.client = client
    return storage


def test_object_exists_returns_false_for_404() -> None:
    storage = make_storage(FakeS3Client(client_error("404", 404)))

    assert storage.object_exists("pubmed/12/123.xml") is False


def test_object_exists_raises_for_auth_errors() -> None:
    storage = make_storage(FakeS3Client(client_error("403", 403)))

    with pytest.raises(ClientError):
        storage.object_exists("pubmed/12/123.xml")


def test_presigned_get_url_uses_bucket_key_and_expiry() -> None:
    client = FakeS3Client()
    storage = make_storage(client)

    url = storage.presigned_get_url("pubmed/12/123.xml", expires_seconds=900)

    assert url.startswith("http://minio:9000/")
    assert client.presigned_call == {
        "client_method": "get_object",
        "Params": {"Bucket": "pubmed-raw", "Key": "pubmed/12/123.xml"},
        "ExpiresIn": 900,
    }
