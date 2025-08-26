#!/usr/bin/env python3
"""
S3 Log Uploader

A compact, production-ready Python CLI utility to upload rotated log files to S3.

Features
- Recursive scan for candidate files using pattern and min-age
- Per-file atomic lock via rename to .uploading
- Optional gzip compression to save bandwidth and storage
- Robust upload via boto3 S3Transfer with multipart support and concurrency
- Retries with exponential backoff and jitter
- Optional SSE-S3 or SSE-KMS encryption
- Verification via HEAD (ContentLength) and md5 metadata for single-part uploads
- Optional deletion of local files after successful upload
- Optional daemon mode (polling)
- Cleanup of stale multipart uploads

Usage examples
- One shot (cron-friendly):
  python s3_log_uploader.py \
    --source-dir /var/log/myapp \
    --bucket my-logs-bucket \
    --prefix logs/myapp \
    --compress --delete-after-upload --log-level INFO

- Dry run:
  python s3_log_uploader.py --source-dir /var/log/myapp --bucket my-logs-bucket --dry-run

- Daemon mode (poll every 5 minutes):
  python s3_log_uploader.py --source-dir /var/log/myapp --bucket my-logs-bucket --daemon --poll-interval 300

Cron example
  */10 * * * * /usr/bin/python3 /opt/tools/s3_log_uploader.py --source-dir /var/log/myapp --bucket my-logs-bucket --prefix logs/myapp --compress --delete-after-upload >> /var/log/s3_uploader.log 2>&1

Systemd template (example)
  [Unit]
  Description=S3 Log Uploader
  After=network-online.target

  [Service]
  ExecStart=/usr/bin/python3 /opt/tools/s3_log_uploader.py --source-dir /var/log/myapp --bucket my-logs-bucket --prefix logs/myapp --compress --delete-after-upload --daemon --poll-interval 300
  Restart=always
  Environment=AWS_REGION=us-east-1
  WorkingDirectory=/opt/tools

  [Install]
  WantedBy=multi-user.target

IAM policy (minimal, replace bucket and KMS key if used)
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:HeadObject",
        "s3:ListBucket",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts",
        "s3:ListBucketMultipartUploads"
      ],
      "Resource": [
        "arn:aws:s3:::YOUR_BUCKET",
        "arn:aws:s3:::YOUR_BUCKET/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:GenerateDataKey",
        "kms:Encrypt",
        "kms:Decrypt"
      ],
      "Resource": ["arn:aws:kms:REGION:ACCOUNT_ID:key/KEY_ID"]
    }
  ]
}

Notes
- Use EC2 instance profile (IAM role) with least privilege; do not hard-code credentials.
- Multipart uploads cannot be verified via md5 ETag; verification relies on ContentLength and successful transfer.
- This tool avoids processing files that are still being written by checking min-age and a short stability check.
"""
from __future__ import annotations

import argparse
import fnmatch
import gzip
import hashlib
import json
import logging
import os
import shutil
import socket
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from time import sleep, time
from typing import Dict, Iterable, List, Optional, Tuple

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError, BotoCoreError
from boto3.s3.transfer import S3Transfer, TransferConfig


UPLOADER_VERSION = "1.0.0"
LOCK_SUFFIX = ".uploading"
DEFAULT_PATTERN = "*.log*"

logger = logging.getLogger("s3_log_uploader")


class UploaderError(Exception):
    pass


@dataclass
class Config:
    source_dir: str
    bucket: str
    prefix: str = ""
    region: Optional[str] = None
    pattern: str = DEFAULT_PATTERN
    min_age: int = 30
    compress: bool = False
    delete_after_upload: bool = False
    dry_run: bool = False
    concurrency: int = 4
    multipart_threshold: int = 64 * 1024 * 1024
    multipart_chunk_size: int = 8 * 1024 * 1024
    sse: str = "none"  # none | AES256 | aws:kms
    kms_key_id: Optional[str] = None
    max_retries: int = 5
    abort_mpu_older_than_hours: int = 24
    log_level: str = "INFO"
    daemon: bool = False
    poll_interval: int = 300


def configure_logging(level: str) -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args(argv: Optional[List[str]] = None) -> Config:
    p = argparse.ArgumentParser(description="Upload rotated logs to S3 with optional compression.")
    p.add_argument("--source-dir", required=True, help="Directory to search for files (recursive)")
    p.add_argument("--bucket", required=True, help="S3 bucket name")
    p.add_argument("--prefix", default="", help="S3 key prefix (no leading slash)")
    p.add_argument("--region", default=None, help="AWS region (optional)")
    p.add_argument("--pattern", default=DEFAULT_PATTERN, help=f"Glob pattern for files (default {DEFAULT_PATTERN})")
    p.add_argument("--min-age", type=int, default=30, help="Seconds since last modification to consider file ready")
    p.add_argument("--compress", action="store_true", help="Gzip compress before upload")
    p.add_argument("--delete-after-upload", action="store_true", help="Delete local file after successful upload")
    p.add_argument("--dry-run", action="store_true", help="List actions without uploading")
    p.add_argument("--concurrency", type=int, default=4, help="Max threads for multipart upload")
    p.add_argument("--multipart-threshold", type=int, default=64 * 1024 * 1024, help="Multipart threshold (bytes)")
    p.add_argument("--multipart-chunk-size", type=int, default=8 * 1024 * 1024, help="Multipart chunk size (bytes)")
    p.add_argument("--sse", choices=["none", "AES256", "aws:kms"], default="none", help="Server-side encryption")
    p.add_argument("--kms-key-id", default=None, help="KMS Key ID (if sse=aws:kms)")
    p.add_argument("--max-retries", type=int, default=5, help="Max retries for S3 operations")
    p.add_argument("--abort-multipart-older-than", type=int, default=24, help="Abort stale multipart uploads older than N hours")
    p.add_argument("--log-level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)")
    p.add_argument("--daemon", action="store_true", help="Run continuously, polling")
    p.add_argument("--poll-interval", type=int, default=300, help="Seconds between polls in daemon mode")

    ns = p.parse_args(argv)
    return Config(
        source_dir=ns.source_dir,
        bucket=ns.bucket,
        prefix=ns.prefix,
        region=ns.region,
        pattern=ns.pattern,
        min_age=ns.min_age,
        compress=ns.compress,
        delete_after_upload=ns.delete_after_upload,
        dry_run=ns.dry_run,
        concurrency=ns.concurrency,
        multipart_threshold=ns.multipart_threshold,
        multipart_chunk_size=ns.multipart_chunk_size,
        sse=ns.sse,
        kms_key_id=ns.kms_key_id,
        max_retries=ns.max_retries,
        abort_mpu_older_than_hours=ns.abort_multipart_older_than,
        log_level=ns.log_level,
        daemon=ns.daemon,
        poll_interval=ns.poll_interval,
    )


def build_session(region: Optional[str]):
    return boto3.session.Session(region_name=region)


def build_s3_clients(session: boto3.session.Session) -> Tuple[BaseClient, S3Transfer]:
    s3_client = session.client("s3")
    transfer_cfg = TransferConfig(
        multipart_threshold=config.multipart_threshold,
        max_concurrency=config.concurrency,
        multipart_chunksize=config.multipart_chunk_size,
        use_threads=True,
    )
    transfer = S3Transfer(client=s3_client, config=transfer_cfg)
    return s3_client, transfer


def now_ts() -> float:
    return time()


def is_candidate(path: str, pattern: str) -> bool:
    base = os.path.basename(path)
    if base.endswith(LOCK_SUFFIX):
        return False
    return fnmatch.fnmatch(base, pattern)


def file_mtime(path: str) -> float:
    return os.path.getmtime(path)


def file_size(path: str) -> int:
    return os.path.getsize(path)


def is_file_stable(path: str, wait_seconds: float = 1.0) -> bool:
    size1 = file_size(path)
    sleep(wait_seconds)
    try:
        size2 = file_size(path)
    except FileNotFoundError:
        return False
    return size1 == size2


def select_candidates(source_dir: str, pattern: str, min_age: int) -> List[str]:
    cutoff = now_ts() - min_age
    candidates: List[str] = []
    for root, dirs, files in os.walk(source_dir):
        for name in files:
            path = os.path.join(root, name)
            try:
                if not is_candidate(path, pattern):
                    continue
                mtime = file_mtime(path)
                if mtime > cutoff:
                    continue
                if file_size(path) <= 0:
                    continue
                candidates.append(path)
            except FileNotFoundError:
                continue
    return candidates


def acquire_lock(path: str) -> Optional[str]:
    """Atomically rename file to a locked path with .uploading suffix.
    Returns locked path or None if failed.
    """
    locked = path + LOCK_SUFFIX
    try:
        os.rename(path, locked)
        return locked
    except FileNotFoundError:
        return None
    except PermissionError:
        logger.warning("Permission denied when locking %s", path)
        return None
    except OSError as e:
        logger.warning("Failed to lock %s: %s", path, e)
        return None


def compute_md5(path: str, chunk_size: int = 2 * 1024 * 1024) -> str:
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


def compress_file(src: str) -> str:
    """Create a gzip compressed file alongside src and return its path."""
    dst = src + ".gz"
    with open(src, "rb") as f_in, gzip.open(dst, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out, length=2 * 1024 * 1024)
    return dst


def s3_key_for_file(prefix: str, hostname: str, src_path: str, mtime: float, compressed: bool) -> str:
    # Normalize prefix
    pfx = prefix.strip("/")
    base = os.path.basename(src_path)
    ts = int(mtime)
    dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
    parts = [
        part for part in [pfx, hostname, f"{dt.year:04d}", f"{dt.month:02d}", f"{dt.day:02d}"] if part
    ]
    suffix = ".gz" if compressed else ""
    key = "/".join(parts + [f"{base}.{ts}{suffix}"])
    return key


def extra_args_for_upload(cfg: Config, original_path: str, checksum: Optional[str]) -> Dict[str, str]:
    meta = {
        "uploader_version": UPLOADER_VERSION,
        "hostname": socket.gethostname(),
        "original_path": original_path,
    }
    if checksum:
        meta["md5sum"] = checksum

    extra: Dict[str, str] = {"Metadata": meta}

    if cfg.sse == "AES256":
        extra["ServerSideEncryption"] = "AES256"
    elif cfg.sse == "aws:kms":
        extra["ServerSideEncryption"] = "aws:kms"
        if cfg.kms_key_id:
            extra["SSEKMSKeyId"] = cfg.kms_key_id
    return extra


def retry_op(fn, *, max_retries: int, base_delay: float = 1.0, max_delay: float = 30.0, op_name: str = "operation"):
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except (ClientError, BotoCoreError, OSError) as e:
            last_exc = e
            if attempt >= max_retries:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            # Add simple jitter
            delay = delay * (0.5 + (attempt % 3) * 0.25)
            logger.warning("%s failed (attempt %d/%d): %s; retrying in %.1fs", op_name, attempt, max_retries, e, delay)
            sleep(delay)
    raise UploaderError(f"{op_name} failed after {max_retries} attempts: {last_exc}")


def upload_one(
    cfg: Config,
    s3: BaseClient,
    transfer: S3Transfer,
    original_path: str,
    locked_path: str,
) -> Tuple[bool, Optional[str], int]:
    """Upload one file. Returns (success, s3_key, uploaded_bytes)."""
    hostname = socket.gethostname()
    # Prepare upload file (compress or not)
    upload_path = locked_path
    remove_upload_path_after = False
    try:
        if cfg.compress:
            upload_path = compress_file(locked_path)
            remove_upload_path_after = True
        # Compute checksum for single-part verification case
        upload_size = file_size(upload_path)
        checksum = None
        if upload_size < cfg.multipart_threshold:
            checksum = compute_md5(upload_path)
        mtime = file_mtime(locked_path)
        key = s3_key_for_file(cfg.prefix, hostname, os.path.basename(original_path), mtime, cfg.compress)
        extra = extra_args_for_upload(cfg, original_path, checksum)

        def _do_upload():
            transfer.upload_file(upload_path, cfg.bucket, key, extra_args=extra)

        retry_op(_do_upload, max_retries=cfg.max_retries, op_name="upload_file")

        # Verify via HEAD
        def _head():
            return s3.head_object(Bucket=cfg.bucket, Key=key)

        head = retry_op(_head, max_retries=cfg.max_retries, op_name="head_object")
        remote_len = int(head.get("ContentLength", -1))
        if remote_len != upload_size:
            raise UploaderError(f"Size mismatch for {key}: local={upload_size} remote={remote_len}")
        if checksum and "md5sum" in head.get("Metadata", {}):
            if head["Metadata"]["md5sum"].lower() != checksum.lower():
                raise UploaderError("Checksum mismatch for single-part upload")

        logger.info("Uploaded %s bytes=%d to s3://%s/%s", original_path, upload_size, cfg.bucket, key)
        return True, key, upload_size
    finally:
        # Always remove compressed temp if created
        if remove_upload_path_after:
            try:
                os.remove(upload_path)
            except FileNotFoundError:
                pass
            except OSError as e:
                logger.warning("Failed to remove temp file %s: %s", upload_path, e)


def cleanup_multipart_uploads(cfg: Config, s3: BaseClient) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg.abort_mpu_older_than_hours)
    key_marker = None
    upload_id_marker = None
    more = True
    prefix = cfg.prefix.strip("/")
    try:
        while more:
            params = {"Bucket": cfg.bucket}
            if prefix:
                params["Prefix"] = prefix
            if key_marker:
                params["KeyMarker"] = key_marker
            if upload_id_marker:
                params["UploadIdMarker"] = upload_id_marker
            resp = s3.list_multipart_uploads(**params)
            uploads = resp.get("Uploads", []) or []
            for u in uploads:
                initiated = u.get("Initiated")
                if isinstance(initiated, str):
                    # Some implementations may return str; try parse
                    initiated_dt = datetime.fromisoformat(initiated.replace("Z", "+00:00"))
                else:
                    initiated_dt = initiated
                if initiated_dt and initiated_dt < cutoff:
                    key = u["Key"]
                    upload_id = u["UploadId"]
                    try:
                        s3.abort_multipart_upload(Bucket=cfg.bucket, Key=key, UploadId=upload_id)
                        logger.info("Aborted stale multipart upload for key=%s upload_id=%s", key, upload_id)
                    except Exception as e:
                        logger.warning("Failed to abort multipart upload %s: %s", upload_id, e)
            more = resp.get("IsTruncated", False)
            key_marker = resp.get("NextKeyMarker")
            upload_id_marker = resp.get("NextUploadIdMarker")
    except s3.exceptions.NoSuchUpload:  # type: ignore[attr-defined]
        pass
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in {"NoSuchUpload", "NotImplemented"}:
            return
        logger.debug("Multipart cleanup ClientError: %s", e)
    except Exception as e:
        logger.debug("Multipart cleanup skipped due to error: %s", e)


def process_once(cfg: Config) -> Dict[str, int]:
    session = build_session(cfg.region)
    s3_client = session.client("s3")
    transfer_cfg = TransferConfig(
        multipart_threshold=cfg.multipart_threshold,
        max_concurrency=cfg.concurrency,
        multipart_chunksize=cfg.multipart_chunk_size,
        use_threads=True,
    )
    transfer = S3Transfer(client=s3_client, config=transfer_cfg)

    # Cleanup stale multipart uploads
    try:
        cleanup_multipart_uploads(cfg, s3_client)
    except Exception as e:
        logger.warning("Multipart cleanup encountered an error: %s", e)

    stats = {
        "files_considered": 0,
        "files_selected": 0,
        "files_locked": 0,
        "files_uploaded": 0,
        "bytes_uploaded": 0,
        "files_deleted": 0,
        "errors": 0,
    }

    candidates = select_candidates(cfg.source_dir, cfg.pattern, cfg.min_age)
    stats["files_considered"] = len(candidates)

    hostname = socket.gethostname()

    for path in candidates:
        stats["files_selected"] += 1
        try:
            if not is_file_stable(path, wait_seconds=1.0):
                logger.debug("Skipping unstable file %s", path)
                continue

            if cfg.dry_run:
                mtime = file_mtime(path)
                key = s3_key_for_file(cfg.prefix, hostname, os.path.basename(path), mtime, cfg.compress)
                size = file_size(path)
                logger.info("[DRY-RUN] Would upload %s (%d bytes) to s3://%s/%s", path, size, cfg.bucket, key)
                continue

            locked = acquire_lock(path)
            if not locked:
                logger.debug("Could not lock %s; skipping", path)
                continue
            stats["files_locked"] += 1

            success = False
            key = None
            uploaded_bytes = 0
            try:
                success, key, uploaded_bytes = upload_one(cfg, s3_client, transfer, path, locked)
                if success:
                    stats["files_uploaded"] += 1
                    stats["bytes_uploaded"] += uploaded_bytes
            except Exception as e:
                stats["errors"] += 1
                logger.error("Failed to upload %s: %s", path, e)
            finally:
                # Finalize local file handling
                try:
                    if success and cfg.delete_after_upload:
                        os.remove(locked)
                        stats["files_deleted"] += 1
                    else:
                        # Rename back to original name
                        if os.path.exists(locked):
                            os.rename(locked, path)
                except Exception as e:
                    logger.warning("Cleanup for %s failed: %s", path, e)
        except Exception as e:
            stats["errors"] += 1
            logger.error("Unexpected error on %s: %s", path, e)

    logger.info("Run complete: %s", json.dumps(stats))
    return stats


def run(cfg: Config) -> int:
    configure_logging(cfg.log_level)

    if cfg.sse == "aws:kms" and not cfg.kms_key_id:
        logger.warning("SSE aws:kms selected without --kms-key-id; upload will use AWS managed CMK")

    if cfg.daemon:
        logger.info("Starting daemon mode; polling every %d seconds", cfg.poll_interval)
        try:
            while True:
                process_once(cfg)
                sleep(cfg.poll_interval)
        except KeyboardInterrupt:
            logger.info("Daemon mode interrupted; exiting")
            return 0
    else:
        stats = process_once(cfg)
        # Non-zero exit if there were errors and nothing was uploaded
        if stats.get("errors", 0) > 0 and stats.get("files_uploaded", 0) == 0:
            return 2
        return 0


if __name__ == "__main__":
    config = parse_args()
    sys.exit(run(config))
