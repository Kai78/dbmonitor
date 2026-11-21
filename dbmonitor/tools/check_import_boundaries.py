#!/usr/bin/env python3
"""Enforces architectural dependency boundaries from Section 16 via AST inspection."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SERVICE_MODULES = {
    "dbmonitor_api",
    "dbmonitor_registry",
    "dbmonitor_scheduler",
    "dbmonitor_inventory",
    "dbmonitor_results",
    "dbmonitor_migrator",
    "dbmonitor_maintenance",
}


def _extract_imports(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module.split(".")[0])
    return modules


def check_boundaries() -> dict:
    violations: list[str] = []
    checked_files = 0

    # 1. Plugins may depend ONLY on dbmonitor_sdk and themselves
    for py_file in (ROOT / "plugins").rglob("*.py"):
        checked_files += 1
        own_pkg = None
        for part in py_file.parts:
            if part.startswith("dbmonitor_poller_") or part.startswith("dbmonitor_provider_"):
                own_pkg = part
                break
        for mod in _extract_imports(py_file):
            if mod.startswith("dbmonitor_") and mod not in ("dbmonitor_sdk", own_pkg):
                violations.append(
                    f"[Plugin boundary] {py_file.relative_to(ROOT)} imports forbidden module '{mod}'"
                )

    # 2. dbmonitor-worker-runtime may NOT import dbmonitor_platform_db, services, or plugins
    wr_dir = ROOT / "packages" / "dbmonitor-worker-runtime"
    for py_file in wr_dir.rglob("*.py"):
        checked_files += 1
        for mod in _extract_imports(py_file):
            if mod == "dbmonitor_platform_db" or mod in SERVICE_MODULES or mod.startswith("dbmonitor_poller_") or mod.startswith("dbmonitor_provider_"):
                violations.append(
                    f"[Worker boundary] {py_file.relative_to(ROOT)} imports forbidden module '{mod}'"
                )

    # 3. dbmonitor-sdk may NOT import common, platform_db, worker_runtime, services, or plugins
    sdk_dir = ROOT / "packages" / "dbmonitor-sdk"
    for py_file in sdk_dir.rglob("*.py"):
        checked_files += 1
        for mod in _extract_imports(py_file):
            if mod.startswith("dbmonitor_") and mod != "dbmonitor_sdk":
                violations.append(
                    f"[SDK boundary] {py_file.relative_to(ROOT)} imports forbidden module '{mod}'"
                )

    # 4 & 5. Services may NOT import plugins or other services (except composition entrypoints in api/app)
    for svc_dir in (ROOT / "services").iterdir():
        if not svc_dir.is_dir():
            continue
        own_svc = {
            "api": "dbmonitor_api",
            "plugin-registry": "dbmonitor_registry",
            "scheduler": "dbmonitor_scheduler",
            "inventory": "dbmonitor_inventory",
            "results-processor": "dbmonitor_results",
            "schema-migrator": "dbmonitor_migrator",
            "maintenance": "dbmonitor_maintenance",
        }.get(svc_dir.name)
        for py_file in svc_dir.rglob("*.py"):
            checked_files += 1
            for mod in _extract_imports(py_file):
                if mod.startswith("dbmonitor_poller_") or mod.startswith("dbmonitor_provider_"):
                    violations.append(
                        f"[Bundle-only boundary] {py_file.relative_to(ROOT)} imports plugin code '{mod}'"
                    )
                if mod in SERVICE_MODULES and mod != own_svc:
                    violations.append(
                        f"[Service isolation] {py_file.relative_to(ROOT)} imports sibling service '{mod}'"
                    )

    return {
        "passed": len(violations) == 0,
        "checked_files": checked_files,
        "violations": violations,
    }


if __name__ == "__main__":
    report = check_boundaries()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["passed"] else 1)
