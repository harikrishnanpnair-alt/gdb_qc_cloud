# First cloud GDB QC update

This package replaces the GDB QC ArcPy engine with Python, GDAL/OGR OpenFileGDB, Shapely and pyproj. It runs on a Linux cloud server. Users upload two ZIP files through the browser and download an Excel report. No ArcGIS installation or Windows Python clone is required for QC.

## Cloud-only automatic connection update

The portal now runs from the QC backend itself. `index.html` uses its own browser origin for QC requests; there are no URL or access-key entry fields. The server creates an anonymous, signed HttpOnly browser session when `/` or `/index.html` is opened. `QC_API_KEY` stays in Render and is used to sign sessions. It is never inserted in HTML.

This is a public trial portal: anyone who can open the service URL can start a browser session and submit QC jobs. Jobs, uploads and downloads are restricted to the browser session that created them. This is session separation, not user authentication. The API-key interface is retained for trusted administrative clients; a valid key can access jobs across sessions.

GDB Transfer is disabled with a Coming soon label in this cloud-only index. Its ArcPy backend has not been converted. The conversion, map, terrain profile, Excel and CAD tools remain in the portal and use the existing conversion service.

## Update your existing Render service

1. Extract this package and upload **all files inside `gdb_qc_cloud`** to the root of your existing `Docker-web-service` GitHub repository. Replace the old files and include the new `cloud_session.py` file. Do not upload only `index.html`: the updated backend is required for automatic sessions and job separation.
2. Keep the `QC_API_KEY` already configured in Render. Choose a private random secret if it has not yet been set. Users will not need to see or enter this value.
3. Keep the Docker runtime, Dockerfile path `./Dockerfile`, and health-check path `/health`. Leave custom Docker Command blank. Commit/push the files and let Render deploy, or use Manual Deploy → Deploy latest commit.
4. Open the actual Render web service URL directly in your browser. Bookmark it and use that page as the portal. Do not open this index by double-clicking a downloaded HTML file, or host it on an unrelated static website: QC uses the address it was opened from.
5. Click **GDB QC Check**. The page checks the cloud service automatically. You should see `Cloud ready · GDAL ...` without entering any connection settings. Refresh connection can be used if the server is waking.
6. ZIP the entire input `.gdb` folder and reference schema `.gdb` folder separately, including their internal files. Use **Load input classes** and **Load reference schema**, select classes and the short-line threshold, then click **Run QC & generate Excel**.
7. Download the Excel and optional JSON report. Review `Summary`, `Check_Coverage`, `Run_Details` and the linked detail sheets.

Browser sessions last 24 hours and are renewed when the portal is reopened. Reopening it in the same browser retains the session owner while the session is valid. Another browser/private window gets its own session. Clearing cookies or allowing the session to expire removes access to that browser's previous jobs; upload and run again. Cookies must be enabled.

The service automatically accepts the origin it serves. `QC_ALLOWED_ORIGINS` is only needed for additional API-key clients and can be left unset for this portal. Browser-session requests always require the portal's own origin, even if extra API-key origins are configured. The existing conversion backend may need its allowed origins updated if it restricts requests from the new portal address.

Render Docker guidance: https://render.com/docs/docker
Render Web Service setup: https://render.com/docs/web-services
Health checks: https://render.com/docs/health-checks

The original conversion/profile API remains `https://gis-processing-backend.onrender.com`. This package still runs as a separate QC service, rather than replacing the conversion backend.

## QC checks in this version

| Check | Rule |
|---|---|
| Nulls and blanks | Separate counts per field and totals; numeric zero is a value, not a null. System/binary/GlobalID fields are excluded. |
| Short lines | Total feature XY geodesic length in metres on the input CRS ellipsoid, below the selected threshold. Default 2 m. This is not a test of each vertex-to-vertex segment. |
| Exact duplicates | Normalized WKB, retaining XY/Z/M where supported; line direction and part order normalized. Each feature after the first matching geometry counts as one extra. Attributes are not part of this comparison. |
| Empty geometry | Missing or empty shape. |
| Schema | Required reference fields, types, string lengths, nullable flags, domain assignments, geometry/Z/M and CRS. Extra input fields are allowed. |
| Domains | Values checked against reference coded-value and numeric range domains; descriptions are flagged when a code is expected. Nulls are handled in the null check. |
| Subtypes | Parses exposed layer XML for subtype field/default/code and per-subtype domain assignments. Native ArcGIS-created subtype GDBs still need comparison testing. |

Feature classes inside feature datasets are supported. Schema matching uses the full dataset/class path, then a unique class name. Both uploaded GDBs are opened read-only. Private copies are made for each QC job.

Workbook styling follows the earlier blue-header QC report. Known issue indicator severity is Critical at 15+, Warning at 5–14, Minor at 1–4. These are issue indicators, not counts of distinct affected features. Failed or unsupported checks produce **INCOMPLETE** and `NOT CHECKED`, with reasons in `Check_Coverage`. A clean report only means that the implemented checks found no issues.

## Differences and limits

- Exact duplicate results can differ from ArcGIS `FindIdentical`: ArcGIS XY/Z snapping tolerance is not applied. Curves are not silently linearized; affected short-line and duplicate checks are incomplete.
- Unknown or unsupported CRS prevents a valid short-line check. Non-numeric range and glob domains are not implemented. Metadata failures are reported.
- Topology rules, connectivity/networks, relationship and attachment integrity, nonspatial tables, raster layers, and project-specific rules not represented by the reference schema are outside this first version.
- The Docker image uses Ubuntu 24.04 GDAL (tested here with 3.8.4). 64-bit OBJECTID geodatabases need a newer, separately validated GDAL build; this package is for ordinary 32-bit OBJECTID GDBs. GDAL also documents restrictions on SDC/CDF compressed data. See https://gdal.org/en/stable/drivers/vector/openfilegdb.html.
- Pilot defaults: 128 MB per ZIP, 1 GB extracted per GDB, 250,000 selected features, 50,000 workbook detail rows, 10 admitted jobs, one processing job at a time and 30-minute processing timeout. Full summary counts are retained when detail rows are capped; omitted-row counts appear in `Check_Coverage`.
- Private GDB copies can use substantial disk space. Start with small files, measure memory/disk use and choose cloud resources based on your own data. The Docker image has not been built or deployed to Render from this workspace.
- Jobs/uploads/results use local server disk. Completed job folders expire after 24 hours, with cleanup triggered on a new submission. Restarted in-flight jobs become failed; on ephemeral hosting, redeployment may also remove uploads/results. Download promptly.
- This is a public trial with browser-session job separation, not per-user accounts or billing limits. It is not a validated 100-user deployment. Administrative API-key requests can access all jobs. Multiple web workers/instances need an external queue and job store; do not increase `--workers` on this implementation.
- Synthetic real GDB tests passed. Your actual GDB files have not been provided or validated; compare initial cloud results against your existing QC tool, especially subtype/domain rules, before adopting it for project sign-off.

## Files

- `index.html`: complete cloud-only portal with automatic same-origin QC requests.
- `main.py`: FastAPI app, session-setting index route, CORS, request-size limit and public readiness check.
- `cloud_session.py`: signed browser sessions; keeps the signing key on the server.
- `cloud_gdb_router.py`: authenticated inspection/QC queue, bounded ZIP extraction, status and downloads.
- `cloud_gdb_worker.py`: isolated processing process.
- `cloud_gdb_common.py`: read-only GDB inventory and layer XML metadata.
- `cloud_qc.py`: QC calculations and Excel/JSON result data.
- `report_style.py`: Excel formatting.
- `Dockerfile`, `.dockerignore`, `requirements.txt`: cloud environment.

Do not copy only `main.py`: it imports the accompanying modules. Do not replace the conversion backend with this app unless you separately integrate its original routes. Upload this complete package to the new QC repository instead.

## Optional environment settings

| Variable | Default |
|---|---|
| QC_API_KEY | Required; service refuses startup without it |
| QC_ALLOWED_ORIGINS | Unset; own portal origin is accepted automatically |
| QC_MAX_UPLOAD_MB | `128` |
| QC_MAX_UNPACKED_MB | `1024` |
| QC_MAX_TOTAL_FEATURES | `250000` |
| QC_MAX_DETAIL_ROWS | `50000` |
| QC_MAX_QUEUED_JOBS | `10` |
| QC_JOB_TIMEOUT_SECONDS | `1800` |
| QC_JOB_ROOT | `/app/qc_jobs` in Docker |

## Optional Docker test on your computer

Only if Docker is already available; a local installation is not needed for the Render method above:

```bash
docker build -t gdb-qc-cloud .
docker run --rm -p 8000:8000 -e QC_API_KEY=YOUR_OWN_SECRET -e QC_ALLOWED_ORIGINS=http://localhost:8000 gdb-qc-cloud
```

Open `http://localhost:8000` directly. The portal connects automatically; local Docker is only an optional developer test. End users use the deployed cloud URL.
