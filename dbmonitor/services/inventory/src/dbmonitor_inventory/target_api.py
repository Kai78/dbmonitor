from __future__ import annotations

import json
from typing import Any

from dbmonitor_platform_db.database import PlatformDatabase
from dbmonitor_sdk.models.target import DatabaseTarget


def fetch_scoped_target(
    db: PlatformDatabase,
    server_id: str,
    worker_db_type: str,
) -> tuple[int, dict[str, Any]]:
    """Target-Config API scoped strictly to the requesting worker's db_type."""
    with db.read() as conn:
        row = conn.execute(
            "SELECT * FROM platform_database_servers WHERE server_id = ?",
            (server_id,),
        ).fetchone()
    if row is None:
        return 404, {"error": f"Server '{server_id}' not found."}
    if row["db_type"] != worker_db_type:
        return 403, {
            "error": (
                f"Worker scoped to db_type '{worker_db_type}' is not authorized "
                f"to access '{row['db_type']}' server '{server_id}'."
            )
        }
    target = DatabaseTarget(
        server_id=row["server_id"],
        hostname=row["hostname"],
        address=row["address"],
        port=int(row["port"]),
        db_type=row["db_type"],
        environment=row["environment"],
        region=row["region"],
        network_zone=row["network_zone"],
        secret_ref=row["secret_ref"],
        config_version=int(row["config_version"]),
        tags=json.loads(row["tags_json"] or "{}"),
        metadata=json.loads(row["metadata_json"] or "{}"),
    )
    return 200, target.to_dict()
