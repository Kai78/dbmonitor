# Running the DBMonitor Platform

This guide explains how to run the DBMonitor Platform locally—both as a single combined command and by running the Python backend and React frontend separately.

---

## 1. Prerequisites

Before starting, make sure you have the following installed:

- **Python 3.11 or newer** (uses only the Python standard library—no `pip install` required)
  ```bash
  python3 --version
  ```
- **Node.js 22 or newer** and **npm**
  ```bash
  node --version
  npm --version
  ```

---

## 2. Install Frontend Dependencies

From the project root directory, install the Node.js packages required by the web server and React dashboard:

```bash
npm install
```

> Note: The Python backend (`dbmonitor/`) uses zero third-party `pip` packages in local mode—everything runs on Python 3.11's built-in standard library (`sqlite3`, `http.server`, `threading`, `json`, `unittest`).

---

## 3. Quick Start (Recommended: Single Command)

The easiest way to run the entire application is with `npm run dev`. This starts the Express/Vite web server on **port 3000**, automatically launches the Python backend on **port 8000**, runs migrations and plugin bundle exports, and proxies `/api/*` requests to Python.

```bash
npm run dev
```

Once started:

- Open your browser to **`http://localhost:3000`**
- The Python control-plane API runs internally at **`http://127.0.0.1:8000`**

On first startup, the Python platform automatically:
1. Exports data-only plugin bundles to `dbmonitor/build/plugin-bundles/`.
2. Generates `dbmonitor/deploy/rabbitmq/topology.generated.json`.
3. Initializes the SQLite database at `dbmonitor/data/dbmonitor.sqlite3` (WAL mode) and applies platform + plugin schema migrations.
4. Seeds default pools (`high_frequency`, `low_frequency`), polling profiles, discovery provider instances (`cmdb-enterprise`, `cloud-prod-eu`, `cloud-staging-eu`), and assignment rules.
5. Starts the Scheduler, Outbox Relay, Lease Reaper, Inventory Consumer, Discovery Worker, per-engine/per-pool Poller Workers (`postgresql`, `oracle`, `mssql`), Results Processors, and Maintenance Jobs.

---

## 4. Running Backend & Frontend Separately (Optional)

If you want to run or debug the Python backend and frontend in two separate terminals:

### Terminal 1 — Start the Python Backend

```bash
python3 dbmonitor/run_platform.py
```

Verify the Python API is healthy:

```bash
curl http://127.0.0.1:8000/health
# Expected: {"status": "ok", "service": "dbmonitor-api"}
```

### Terminal 2 — Start the Frontend Dev Server

If you want Vite alone (proxying `/api` manually) or to build the production frontend bundle:

```bash
npm run build
```

> Note: `server.ts` is configured to spawn `dbmonitor/run_platform.py` automatically when you run `npm run dev` or `npm start`. If port `8000` is already occupied by a manually started Python process, stop that process before running `npm run dev`, or set a different port via `DBMONITOR_API_PORT`.

---

## 5. Production Build & Start

To build the static React UI and run the production server:

```bash
npm run build
NODE_ENV=production npm start
```

This serves the compiled files from `dist/` and starts the Python backend on port `8000`, listening on **`http://0.0.0.0:3000`**.

---

## 6. Dependent Build-Time Tools & Verification Checks

You can run the platform's build-time generators, architectural boundary checks, and test suites manually at any time:

### Export Data-Only Plugin Bundles
Builds manifests, JSON Schemas, and SQL migration checksums into `dbmonitor/build/plugin-bundles/`:
```bash
python3 dbmonitor/tools/export_plugin_bundles.py
```

### Generate RabbitMQ Queue Topology
Generates `dbmonitor/deploy/rabbitmq/topology.generated.json` from configured pools and database types:
```bash
python3 dbmonitor/tools/generate_rabbitmq_topology.py
```

### Check Architectural Import Boundaries
Verifies via Python AST inspection that workers do not import central DB packages and services do not import plugin code or sibling services:
```bash
python3 dbmonitor/tools/check_import_boundaries.py
```

### Run Python Contract & End-to-End Tests
Runs all SDK contract tests (`provider`, `poller`, `profile`, `schema`) and the full discovery-to-metrics pipeline integration test:
```bash
python3 -m unittest discover -s dbmonitor/tests -v
```

### Type-Check & Build the Frontend
```bash
npm run lint
npm run build
```

---

## 7. Environment Variables (Optional)

All variables have sensible defaults and do not require a `.env` file for local development:

| Variable | Default | Description |
|---|---|---|
| `PORT` | `3000` | Port for the web server and UI |
| `DBMONITOR_API_HOST` | `127.0.0.1` | Bind host for the Python REST API |
| `DBMONITOR_API_PORT` | `8000` | Port for the Python REST API |
| `DBMONITOR_DB_PATH` | `dbmonitor/data/dbmonitor.sqlite3` | SQLite database file path |
| `DBMONITOR_BUNDLE_DIR` | `dbmonitor/build/plugin-bundles` | Directory for exported data-only plugin bundles |
| `DBMONITOR_PLATFORM_MIN_INTERVAL_SECONDS` | `30` | Platform-wide minimum polling interval floor |
| `DBMONITOR_MAX_RESULT_BYTES` | `1048576` | Maximum poll result payload size (1 MiB) |

---

## 8. Troubleshooting

- **Port 3000 or 8000 already in use**: Stop any existing `node`, `tsx`, or `python3 dbmonitor/run_platform.py` process, or override the ports using `PORT=3001 DBMONITOR_API_PORT=8001 npm run dev`.
- **Resetting local database state**: Stop the server and delete `dbmonitor/data/dbmonitor.sqlite3*`, then restart—all tables, migrations, bundles, and seed data are recreated automatically.
- **Container / Docker worker references**: Parameterized worker Dockerfiles and pool configs are located under `dbmonitor/deploy/docker/` and `dbmonitor/deploy/pools/` for multi-container deployment with external PostgreSQL and RabbitMQ.
