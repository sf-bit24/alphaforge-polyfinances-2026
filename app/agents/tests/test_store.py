import io

import pytest
from botocore.exceptions import ClientError

from alphaforge.store import ConflictError, StoreError
from alphaforge.store.local import LocalStore
from alphaforge.store.s3 import S3Store


def test_local_store_round_trip_and_listing(tmp_path):
    store = LocalStore(tmp_path)
    etag = store.put_text("clients/a/profil.md", "bonjour")
    obj = store.get("clients/a/profil.md")
    assert obj.text == "bonjour" and obj.etag == etag
    store.put_json("staging/r1/press/x.json", {"é": 1})
    assert store.get_json("staging/r1/press/x.json") == {"é": 1}
    assert store.get("clients/a/missing.md") is None
    assert [i.key for i in store.list("clients/")] == ["clients/a/profil.md"]
    assert store.list("nothing/") == []


def test_local_store_conditional_writes(tmp_path):
    store = LocalStore(tmp_path)
    first = store.put_text("k/doc.md", "v1", if_none_match=True)
    with pytest.raises(ConflictError):
        store.put_text("k/doc.md", "v2", if_none_match=True)
    second = store.put_text("k/doc.md", "v2", if_match=first)
    with pytest.raises(ConflictError):
        store.put_text("k/doc.md", "v3", if_match=first)
    assert store.put_text("k/doc.md", "v3", if_match=second)


@pytest.mark.parametrize("key", ["../etc/passwd", "/abs", "a//b", "a/../b", "", "a/", "a b"])
def test_keys_are_validated(tmp_path, key):
    with pytest.raises(StoreError):
        LocalStore(tmp_path).get(key)


def client_error(code, status):
    return ClientError(
        {"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}}, "GetObject"
    )


class FakeS3:
    def __init__(self, error=None, listing=None, list_error=None):
        self.error = error
        self.listing = listing or []
        self.list_error = list_error
        self.list_calls = []
        self.puts = []

    def get_object(self, Bucket, Key):
        if self.error:
            raise self.error
        return {"Body": io.BytesIO(b"x"), "ETag": '"e"'}

    def head_object(self, Bucket, Key):
        if self.error:
            raise self.error
        return {}

    def list_objects_v2(self, Bucket, Prefix, MaxKeys):
        self.list_calls.append(Prefix)
        if self.list_error:
            raise self.list_error
        return {"Contents": [{"Key": key} for key in self.listing if key.startswith(Prefix)][:MaxKeys]}

    def put_object(self, **params):
        self.puts.append(params)
        if self.error:
            raise self.error
        return {"ETag": '"new"'}


def test_s3_no_such_key_is_none():
    store = S3Store("b", region="us-east-1", client=FakeS3(error=client_error("NoSuchKey", 404)))
    assert store.get("clients/x/profil.md") is None


def test_s3_access_denied_on_a_missing_key_is_none():
    fake = FakeS3(error=client_error("AccessDenied", 403), listing=["clients/x/profil.md.bak"])
    store = S3Store("b", region="us-east-1", client=fake)
    assert store.get("clients/x/profil.md") is None
    assert fake.list_calls == ["clients/x/profil.md"]
    assert store.exists("clients/x/profil.md") is False


def test_s3_access_denied_on_an_existing_key_is_raised():
    fake = FakeS3(error=client_error("AccessDenied", 403), listing=["clients/x/profil.md"])
    store = S3Store("b", region="us-east-1", client=fake)
    with pytest.raises(ClientError):
        store.get("clients/x/profil.md")
    with pytest.raises(ClientError):
        store.exists("clients/x/profil.md")


def test_s3_access_denied_and_list_failure_raises_the_original_error():
    fake = FakeS3(error=client_error("AccessDenied", 403), list_error=client_error("AccessDenied", 403))
    store = S3Store("b", region="us-east-1", client=fake)
    with pytest.raises(ClientError) as exc:
        store.get("general/index.md")
    assert exc.value.operation_name == "GetObject"


def test_s3_conditional_write_parameters_and_conflicts():
    fake = FakeS3()
    store = S3Store("b", region="us-east-1", client=fake)
    store.put_text("clients/x/profil.md", "a", if_match='"e"')
    store.put_text("clients/x/journal.md", "b", if_none_match=True)
    assert fake.puts[0]["IfMatch"] == '"e"' and "IfNoneMatch" not in fake.puts[0]
    assert fake.puts[1]["IfNoneMatch"] == "*"
    assert "ServerSideEncryption" not in fake.puts[0]
    failing = S3Store("b", region="us-east-1", client=FakeS3(error=client_error("PreconditionFailed", 412)))
    with pytest.raises(ConflictError):
        failing.put_text("clients/x/profil.md", "a", if_match='"e"')
