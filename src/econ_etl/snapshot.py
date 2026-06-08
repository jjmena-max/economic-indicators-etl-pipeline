"""Optional Azure Blob snapshot of the curated table.

When the pipeline runs in Azure, we keep a timestamped CSV copy of each load in
Blob Storage (ADLS Gen2) for lineage and ad-hoc analysis. This is *opt-in*:
nothing here imports the Azure SDK unless :func:`upload_snapshot` is actually
called, so local runs, the test suite and CI stay fully offline and dependency-free.

Authentication uses ``DefaultAzureCredential`` — in the cloud that resolves to
the job's user-assigned managed identity (no secrets); locally it picks up your
``az login`` session. Set these environment variables to enable it:

    SNAPSHOT_ACCOUNT_URL   e.g. https://econetlst....blob.core.windows.net
    SNAPSHOT_CONTAINER     blob container name (default: "snapshots")
    AZURE_CLIENT_ID        client id of the managed identity (set by the Bicep job)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def snapshot_enabled() -> bool:
    """True when the Blob snapshot target is configured via the environment."""
    return bool(os.getenv("SNAPSHOT_ACCOUNT_URL"))


def upload_snapshot(local_path: str | Path, *, prefix: str = "economic_indicators") -> str | None:
    """Upload ``local_path`` to Blob Storage as a timestamped snapshot.

    Returns the blob URL on success, or ``None`` if snapshotting is not
    configured. Azure imports happen lazily so importing this module never
    pulls in the Azure SDK.
    """
    account_url = os.getenv("SNAPSHOT_ACCOUNT_URL")
    if not account_url:
        logger.debug("SNAPSHOT_ACCOUNT_URL not set; skipping Blob snapshot")
        return None

    container = os.getenv("SNAPSHOT_CONTAINER", "snapshots")
    stamp = datetime.now(timezone.utc).strftime("%Y/%m/%dT%H%M%SZ")
    blob_name = f"{prefix}/{stamp}.csv"

    # Lazy imports: only needed when snapshotting is actually requested.
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    credential = DefaultAzureCredential()
    service = BlobServiceClient(account_url=account_url, credential=credential)
    blob = service.get_blob_client(container=container, blob=blob_name)

    with open(local_path, "rb") as fh:
        blob.upload_blob(fh, overwrite=True)

    logger.info("Uploaded snapshot to %s/%s", container, blob_name)
    return blob.url
