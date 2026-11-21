from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in [
    ROOT / "packages" / "dbmonitor-sdk" / "src",
    ROOT / "plugins" / "providers" / "cmdb" / "src",
    ROOT / "plugins" / "providers" / "cloud" / "src",
    ROOT / "plugins" / "pollers" / "postgresql" / "src",
    ROOT / "plugins" / "pollers" / "oracle" / "src",
    ROOT / "plugins" / "pollers" / "mssql" / "src",
    ROOT / "tools",
]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from check_import_boundaries import check_boundaries
from dbmonitor_poller_mssql.manifest import MANIFEST as MSSQL_M
from dbmonitor_poller_mssql.plugin import plugin as MSSQL_P
from dbmonitor_poller_oracle.manifest import MANIFEST as ORACLE_M
from dbmonitor_poller_oracle.plugin import plugin as ORACLE_P
from dbmonitor_poller_postgresql.manifest import MANIFEST as PG_M
from dbmonitor_poller_postgresql.plugin import plugin as PG_P
from dbmonitor_provider_cloud.manifest import MANIFEST as CLOUD_M
from dbmonitor_provider_cloud.plugin import plugin as CLOUD_P
from dbmonitor_provider_cmdb.manifest import MANIFEST as CMDB_M
from dbmonitor_provider_cmdb.plugin import plugin as CMDB_P
from dbmonitor_sdk.contracts.schema import SchemaManifest
from dbmonitor_sdk.testing import (
    verify_poller_contract,
    verify_profile_contract,
    verify_provider_contract,
    verify_schema_contract,
)


class ContractAndBoundaryTests(unittest.TestCase):
    def test_import_boundaries(self) -> None:
        report = check_boundaries()
        self.assertTrue(report["passed"], msg=str(report["violations"]))

    def test_provider_contracts(self) -> None:
        for plugin, manifest in ((CMDB_P, CMDB_M), (CLOUD_P, CLOUD_M)):
            checks = verify_provider_contract(plugin, manifest)
            self.assertGreaterEqual(len(checks), 2)

    def test_poller_profile_and_schema_contracts(self) -> None:
        specs = [
            (PG_P, PG_M, ROOT / "plugins" / "pollers" / "postgresql" / "src" / "dbmonitor_poller_postgresql" / "schema" / "manifest.json"),
            (ORACLE_P, ORACLE_M, ROOT / "plugins" / "pollers" / "oracle" / "src" / "dbmonitor_poller_oracle" / "schema" / "manifest.json"),
            (MSSQL_P, MSSQL_M, ROOT / "plugins" / "pollers" / "mssql" / "src" / "dbmonitor_poller_mssql" / "schema" / "manifest.json"),
        ]
        for plugin, manifest, sm_path in specs:
            verify_poller_contract(plugin, manifest)
            verify_profile_contract(manifest)
            sm = SchemaManifest.from_dict(json.loads(sm_path.read_text(encoding="utf-8")))
            verify_schema_contract(sm)


if __name__ == "__main__":
    unittest.main()
