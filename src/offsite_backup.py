"""
Off-site backup upload to Backblaze B2.

Uses the native B2 HTTP API via ``requests`` (no rclone dependency).
Configured via:
  B2_APPLICATION_KEY_ID
  B2_APPLICATION_KEY
  B2_BUCKET_NAME

Optional:
  B2_OFFSITE_PREFIX  (default: golf-model)
  B2_KEEP            (number of remote backups to retain; default 4)
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger("golf.offsite_backup")

_B2_AUTH_URL = "https://api.backblazeb2.com/b2api/v2/b2_authorize_account"


def _configured() -> tuple[str, str, str] | None:
    key_id = (os.environ.get("B2_APPLICATION_KEY_ID") or "").strip()
    app_key = (os.environ.get("B2_APPLICATION_KEY") or "").strip()
    bucket = (os.environ.get("B2_BUCKET_NAME") or "").strip()
    if not key_id or not app_key or not bucket:
        return None
    return key_id, app_key, bucket


def _sha1_file(path: str) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _authorize(key_id: str, app_key: str) -> dict[str, Any]:
    resp = requests.get(_B2_AUTH_URL, auth=(key_id, app_key), timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def _resolve_bucket_id(api_url: str, auth_token: str, account_id: str, bucket_name: str) -> str:
    resp = requests.post(
        f"{api_url}/b2api/v2/b2_list_buckets",
        headers={"Authorization": auth_token},
        json={"accountId": account_id, "bucketName": bucket_name},
        timeout=30.0,
    )
    resp.raise_for_status()
    buckets = resp.json().get("buckets") or []
    for bucket in buckets:
        if bucket.get("bucketName") == bucket_name:
            return str(bucket["bucketId"])
    raise RuntimeError(f"B2 bucket not found: {bucket_name}")


def _get_upload_url(api_url: str, auth_token: str, bucket_id: str) -> dict[str, Any]:
    resp = requests.post(
        f"{api_url}/b2api/v2/b2_get_upload_url",
        headers={"Authorization": auth_token},
        json={"bucketId": bucket_id},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def upload_backup_offsite(local_path: str) -> dict[str, Any]:
    """Upload a local backup file to Backblaze B2. No-op when credentials are unset."""
    cfg = _configured()
    if not cfg:
        return {
            "ok": False,
            "skipped": True,
            "reason": "B2_APPLICATION_KEY_ID / B2_APPLICATION_KEY / B2_BUCKET_NAME not set",
        }
    if not os.path.isfile(local_path):
        return {"ok": False, "skipped": False, "error": f"local file missing: {local_path}"}

    key_id, app_key, bucket_name = cfg
    prefix = (os.environ.get("B2_OFFSITE_PREFIX") or "golf-model").strip().strip("/")
    remote_name = f"{prefix}/{os.path.basename(local_path)}" if prefix else os.path.basename(local_path)

    try:
        auth = _authorize(key_id, app_key)
        api_url = str(auth["apiUrl"]).rstrip("/")
        auth_token = str(auth["authorizationToken"])
        account_id = str(auth["accountId"])
        bucket_id = _resolve_bucket_id(api_url, auth_token, account_id, bucket_name)
        upload = _get_upload_url(api_url, auth_token, bucket_id)
        upload_url = str(upload["uploadUrl"])
        upload_token = str(upload["authorizationToken"])
        sha1 = _sha1_file(local_path)
        size = os.path.getsize(local_path)

        with open(local_path, "rb") as handle:
            resp = requests.post(
                upload_url,
                headers={
                    "Authorization": upload_token,
                    "X-Bz-File-Name": quote(remote_name, safe=""),
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(size),
                    "X-Bz-Content-Sha1": sha1,
                },
                data=handle,
                timeout=600.0,
            )
        if resp.status_code != 200:
            return {
                "ok": False,
                "skipped": False,
                "error": f"upload status={resp.status_code} body={(resp.text or '')[:300]}",
            }
        payload = resp.json()
        remote_sha = str(payload.get("contentSha1") or "")
        if remote_sha and remote_sha != sha1:
            return {
                "ok": False,
                "skipped": False,
                "error": f"checksum mismatch local={sha1} remote={remote_sha}",
            }

        pruned = prune_remote_backups(
            api_url=api_url,
            auth_token=auth_token,
            bucket_id=bucket_id,
            prefix=f"{prefix}/" if prefix else "",
        )
        return {
            "ok": True,
            "skipped": False,
            "remote_name": remote_name,
            "file_id": payload.get("fileId"),
            "sha1": sha1,
            "size_bytes": size,
            "pruned_remote": pruned,
        }
    except Exception as exc:
        logger.warning("off-site backup upload failed: %s", exc)
        return {"ok": False, "skipped": False, "error": str(exc)}


def prune_remote_backups(
    *,
    api_url: str,
    auth_token: str,
    bucket_id: str,
    prefix: str,
) -> list[str]:
    """Keep the newest ``B2_KEEP`` remote files under prefix; delete older ones."""
    raw_keep = (os.environ.get("B2_KEEP") or "4").strip()
    try:
        keep = max(1, int(raw_keep))
    except ValueError:
        keep = 4

    start_name: str | None = None
    start_id: str | None = None
    files: list[dict[str, Any]] = []
    while True:
        body: dict[str, Any] = {
            "bucketId": bucket_id,
            "prefix": prefix,
            "maxFileCount": 1000,
        }
        if start_name:
            body["startFileName"] = start_name
        if start_id:
            body["startFileId"] = start_id
        resp = requests.post(
            f"{api_url}/b2api/v2/b2_list_file_versions",
            headers={"Authorization": auth_token},
            json=body,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("files") or []
        files.extend(batch)
        start_name = data.get("nextFileName")
        start_id = data.get("nextFileId")
        if not start_name:
            break

    # Prefer newest by uploadTimestamp then fileName.
    files.sort(
        key=lambda row: (int(row.get("uploadTimestamp") or 0), str(row.get("fileName") or "")),
        reverse=True,
    )
    deleted: list[str] = []
    for row in files[keep:]:
        file_id = row.get("fileId")
        file_name = row.get("fileName")
        if not file_id or not file_name:
            continue
        del_resp = requests.post(
            f"{api_url}/b2api/v2/b2_delete_file_version",
            headers={"Authorization": auth_token},
            json={"fileName": file_name, "fileId": file_id},
            timeout=30.0,
        )
        if del_resp.status_code == 200:
            deleted.append(str(file_name))
    return deleted


def download_latest_offsite(dest_path: str) -> dict[str, Any]:
    """Download the newest gzip/db backup from B2 into ``dest_path`` (side copy)."""
    cfg = _configured()
    if not cfg:
        return {
            "ok": False,
            "skipped": True,
            "reason": "B2_APPLICATION_KEY_ID / B2_APPLICATION_KEY / B2_BUCKET_NAME not set",
        }
    key_id, app_key, bucket_name = cfg
    prefix = (os.environ.get("B2_OFFSITE_PREFIX") or "golf-model").strip().strip("/")
    try:
        auth = _authorize(key_id, app_key)
        api_url = str(auth["apiUrl"]).rstrip("/")
        download_url = str(auth.get("downloadUrl") or api_url).rstrip("/")
        auth_token = str(auth["authorizationToken"])
        account_id = str(auth["accountId"])
        bucket_id = _resolve_bucket_id(api_url, auth_token, account_id, bucket_name)
        listed = requests.post(
            f"{api_url}/b2api/v2/b2_list_file_names",
            headers={"Authorization": auth_token},
            json={"bucketId": bucket_id, "prefix": f"{prefix}/" if prefix else "", "maxFileCount": 1000},
            timeout=60.0,
        )
        listed.raise_for_status()
        files = listed.json().get("files") or []
        files.sort(
            key=lambda row: (int(row.get("uploadTimestamp") or 0), str(row.get("fileName") or "")),
            reverse=True,
        )
        if not files:
            return {"ok": False, "skipped": False, "error": "no remote backups"}
        newest = files[0]
        file_name = str(newest.get("fileName") or "")
        resp = requests.get(
            f"{download_url}/file/{quote(bucket_name, safe='')}/{quote(file_name, safe='')}",
            headers={"Authorization": auth_token},
            timeout=600.0,
            stream=True,
        )
        if resp.status_code != 200:
            return {
                "ok": False,
                "skipped": False,
                "error": f"download status={resp.status_code} body={(resp.text or '')[:300]}",
            }
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "wb") as handle:
            for chunk in resp.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)
        return {
            "ok": True,
            "skipped": False,
            "remote_name": file_name,
            "path": dest_path,
            "size_bytes": os.path.getsize(dest_path),
        }
    except Exception as exc:
        logger.warning("off-site download failed: %s", exc)
        return {"ok": False, "skipped": False, "error": str(exc)}
