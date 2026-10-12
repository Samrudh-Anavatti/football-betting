"""Nightly database backup to Azure Blob storage.

Takes a consistent copy of the SQLite file with SQLite's online backup API
(never a byte copy of the live file), gzips it on local disk and uploads it as
football-YYYY-MM-DD-HHMM.db.gz. The container deletes blobs after 30 days
(a lifecycle rule on the storage account), so there's nothing to prune here.

The web app signs in with its managed identity (Storage Blob Data Contributor
on the container only), so there's no key to keep. Restore steps: DATABASE.md.
"""
import gzip
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime

from .. import config
from ..database import engine


def configured() -> bool:
    return bool(config.BACKUP_CONTAINER_URL) and engine.url.get_backend_name() == "sqlite"


# Test seam: swap in a fake container.
def make_container():
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import ContainerClient

    return ContainerClient.from_container_url(config.BACKUP_CONTAINER_URL, credential=DefaultAzureCredential())


def backup_now(now: datetime | None = None) -> dict:
    """Copy, compress and upload the database. Returns what was uploaded."""
    now = now or datetime.utcnow()
    name = f"football-{now:%Y-%m-%d-%H%M}.db.gz"
    with tempfile.TemporaryDirectory() as tmp:
        copy, packed = os.path.join(tmp, "copy.db"), os.path.join(tmp, name)
        src, dest = sqlite3.connect(engine.url.database), sqlite3.connect(copy)
        try:
            src.backup(dest)  # one step: a consistent snapshot under a read lock
        finally:
            src.close()
            dest.close()
        with open(copy, "rb") as f_in, gzip.open(packed, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
        with open(packed, "rb") as f:
            make_container().upload_blob(name, f, overwrite=True)
        return {"blob": name, "bytes": os.path.getsize(copy), "compressed_bytes": os.path.getsize(packed)}


def job_backup(db, run) -> None:
    """SyncRun job (scheduled nightly, or Admin → Data → Back up now)."""
    try:
        out = backup_now()
        run.items, run.status = 1, "ok"
        run.details_json = json.dumps(out)
    except Exception as e:  # noqa: BLE001  any failure must show on the Schedule card
        run.status, run.message = "error", f"Backup failed: {e}"
    run.progress, run.finished_at = 1, datetime.utcnow()
    db.commit()
