"""Tests for Backblaze B2 off-site backup helper."""


def test_upload_skipped_without_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("B2_APPLICATION_KEY_ID", raising=False)
    monkeypatch.delenv("B2_APPLICATION_KEY", raising=False)
    monkeypatch.delenv("B2_BUCKET_NAME", raising=False)
    from src.offsite_backup import upload_backup_offsite

    path = tmp_path / "golf_model_test.db.gz"
    path.write_bytes(b"data")
    result = upload_backup_offsite(str(path))
    assert result["skipped"] is True
    assert result["ok"] is False
