# First cloud GDB QC update

This package replaces the GDB QC ArcPy engine with Python, GDAL/OGR OpenFileGDB, Shapely and pyproj. It runs on a Linux cloud server. Users upload two ZIP files through the browser and download an Excel report. No ArcGIS installation or Windows Python clone is required for QC.

## Curved geometry update

The uploaded QC report identified curves as the cause of incomplete checks in AccessRoutes, OtherAreaFeatures, OtherlineFeatures, Structure_line and Structure_Outline. This update adds `curve_geometry.py` and modifies `cloud_qc.py` to process supported circular strings, compound curves, curve polygons and multipart curve containers.

For this update, replace the backend files using the included package, including the **new `curve_geometry.py`** module. The key changed backend files are `cloud_qc.py` and `curve_geometry.py`. Replace the frontend index as well to show processing/failure notes directly in the result table. Keep the existing Render key and repository connection, redeploy, and rerun QC. The old workbook cannot be recalculated without the actual GDB inputs.

- Curved line lengths use a private GDAL line approximation with maximum **0.25 degrees per arc step**, followed by geodesic XY measurement. These lengths are approximate and identified in `Curve_Processing`, `Run_Details` and short-feature detail sheets. The uploaded GDBs remain read-only.
- Curved duplicates compare exact native arc/line control records **as returned by GDAL/OGR**, including its XY/Z/M coordinates. Direction, ring starts at stored segment boundaries, part order and hole order are normalized. The length approximation is never used for duplicate matching.
- Curves with different control records representing the same mathematical curve, and native curves versus already-densified straight geometry, may not match. GDAL's reconstructed curve control ordinates can depend on the driver; validation against an ArcGIS-created Z/M curve dataset is still needed. The update does not claim identical ArcGIS FindIdentical behavior.
- Curved features no longer fail solely because they are curved. Unsupported/invalid geometry, excessive line-measurement point counts or other failed checks still produce `INCOMPLETE`, with reasons. Approximation/method notes are shown separately and can produce a completed-with-warnings job without an INCOMPLETE class.
- The actual input/reference GDBs have not been supplied; this update passed real synthetic curved File GDB tests but has not recomputed the uploaded project report. Rerun the portal with those GDBs after deployment.

## Separate frontend and cloud QC backend

| Component | Website | GitHub repository |
|---|---|---|
| Main index / portal | https://harikrishnanpnair-alt.github.io/gis-processing-portal/ | `harikrishnanpnair-alt/gis-processing-portal` |
| GDB QC Python backend | https://gdb-qc-cloud.onrender.com | `harikrishnanpnair-alt/gdb_qc_cloud` |

The index contains the fixed public QC backend address. Users do not enter a URL or access key. It starts an anonymous, signed session automatically using `POST /gdb/session`, then includes its session token in QC requests. The server keeps `QC_API_KEY` private. Cross-origin QC requests do not depend on third-party cookies.

This is a public trial: anyone who can open an allowed frontend can start a session and submit QC jobs. Uploads, job status and report downloads are restricted to the session that created them. This is session separation, not user authentication. Trusted administrative API-key clients can access all jobs.

GDB Transfer is disabled with a Coming soon label until its cloud conversion. Existing conversion, map, terrain profile, Excel and CAD tools remain in the portal and use the original conversion service.

## Install this update

1. Upload `frontend/index.html` to the root of **`gis-processing-portal`**, replacing that repository's index. Its name must be exactly `index.html`, not `index(1).html`. Keep GitHub Pages enabled for this repository.
2. Upload **all files inside `gdb_qc_cloud`** to the root of the backend repository **`gdb_qc_cloud`**, replacing its old files. Do not put the entire folder one level below the Dockerfile. The changed backend files for this connection are `main.py`, `cloud_gdb_router.py` and `cloud_session.py`; the other modules are included for completeness.
3. In Render, ensure your service is connected to the current **`gdb_qc_cloud`** repository, not the earlier `Docker-web-service` repository. Keep the private `QC_API_KEY` you already set, Docker runtime, Dockerfile path `./Dockerfile`, and health-check path `/health`. Commit/push, then deploy the latest commit if auto-deploy is not enabled.
4. No frontend-origin entry is required for this address: the backend already permits `https://harikrishnanpnair-alt.github.io`. GitHub Pages' `/gis-processing-portal/` path is not part of an origin. No access key is stored in or typed into the index.
5. Open **https://harikrishnanpnair-alt.github.io/gis-processing-portal/**, refresh the page to load the updated index, then select **GDB QC Check**. It should show `Cloud ready · GDAL ...` automatically.
6. ZIP the entire input `.gdb` and reference schema `.gdb` as separate files, including their internal contents. Load both, choose classes and the short-line threshold, then run QC and download Excel/JSON.

The QC backend does not require its own `index.html`. If you open its root URL without an optional index present, it redirects to the main portal. `/health` remains an independent GDAL readiness endpoint. This avoids the previous missing-index server error.

The temporary session token is stored in `sessionStorage` for the frontend/tab, with an in-memory fallback if storage is blocked. It is not the shared backend API key. It lasts up to 24 hours and can be refreshed when the portal opens again while still valid. Expired/cleared sessions or a new tab context can lose access to previous jobs; load and process the GDBs again. Third-party cookies are not needed.

If you later change the main portal address, set `QC_PORTAL_URL` on Render to the full new frontend URL and update the public `QC_API_BASE` constant in the index only if you also change the backend URL. `QC_ALLOWED_ORIGINS` adds optional other allowed origins. Origin configuration is not user authentication.

Render setup: https://render.com/docs/web-services
Docker deployment: https://render.com/docs/docker

The conversion/profile API remains `https://gis-processing-backend.onrender.com`; the QC API is `https://gdb-qc-cloud.onrender.com`.

## QC checks in this version

| Check | Rule |
|---|---|
| Nulls and blanks | Separate counts per field and totals; numeric zero is a value, not a null. System/binary/GlobalID fields are excluded. |
| Short lines | Total feature XY geodesic length in metres on the input CRS ellipsoid, below the selected threshold. Curves are approximated at 0.25 degrees per arc step. Default threshold 2 m; this is not a check of individual vertex-to-vertex segments. |
| Exact duplicates | Straight features: normalized WKB. Curves: native arc/line control records returned by OGR, including XY/Z/M. Direction/ring start/part order normalized. Extras counted after the first matching feature; attributes excluded. Different curve representations may not match. |
| Empty geometry | Missing or empty shape. |
| Schema | Required reference fields, types, string lengths, nullable flags, domain assignments, geometry/Z/M and CRS. Extra input fields are allowed. |
| Domains | Values checked against reference coded-value and numeric range domains; descriptions are flagged when a code is expected. Nulls are handled in the null check. |
| Subtypes | Parses exposed layer XML for subtype field/default/code and per-subtype domain assignments. Native ArcGIS-created subtype GDBs still need comparison testing. |

Feature classes inside feature datasets are supported. Schema matching uses the full dataset/class path, then a unique class name. Both uploaded GDBs are opened read-only. Private copies are made for each QC job.

Workbook styling follows the earlier blue-header QC report. Known issue indicator severity is Critical at 15+, Warning at 5–14, Minor at 1–4. These are issue indicators, not counts of distinct affected features. Failed or unsupported checks produce **INCOMPLETE** and `NOT CHECKED`, with reasons in `Check_Coverage`. A clean report only means that the implemented checks found no issues.

## Differences and limits

- Exact duplicate results can differ from ArcGIS `FindIdentical`: ArcGIS XY/Z snapping tolerance is not applied. Curve lengths are explicitly approximated; curve duplicate matching uses native control records, not the approximation. Unsupported or invalid curve geometry remains incomplete.
- Unknown or unsupported CRS prevents a valid short-line check. Non-numeric range and glob domains are not implemented. Metadata failures are reported.
- Topology rules, connectivity/networks, relationship and attachment integrity, nonspatial tables, raster layers, and project-specific rules not represented by the reference schema are outside this first version.
- The Docker image uses Ubuntu 24.04 GDAL (tested here with 3.8.4). 64-bit OBJECTID geodatabases need a newer, separately validated GDAL build; this package is for ordinary 32-bit OBJECTID GDBs. GDAL also documents restrictions on SDC/CDF compressed data. See https://gdal.org/en/stable/drivers/vector/openfilegdb.html.
- Pilot defaults: 128 MB per ZIP, 1 GB extracted per GDB, 250,000 selected features, 50,000 workbook detail rows, 10 admitted jobs, one processing job at a time and 30-minute processing timeout. Line measurement is limited to 250,000 points per feature. Full summary counts are retained when detail rows are capped; omitted-row counts appear in `Check_Coverage`.
- Private GDB copies can use substantial disk space. Start with small files, measure memory/disk use and choose cloud resources based on your own data. The Docker image has not been built or deployed to Render from this workspace.
- Jobs/uploads/results use local server disk. Completed job folders expire after 24 hours, with cleanup triggered on a new submission. Restarted in-flight jobs become failed; on ephemeral hosting, redeployment may also remove uploads/results. Download promptly.
- This is a public trial with browser-session job separation, not per-user accounts or billing limits. It is not a validated 100-user deployment. Administrative API-key requests can access all jobs. Multiple web workers/instances need an external queue and job store; do not increase `--workers` on this implementation.
- Synthetic real GDB tests passed. Your actual GDB files have not been provided or validated; compare initial cloud results against your existing QC tool, especially subtype/domain rules, before adopting it for project sign-off.

## Files

- `frontend/index.html`: main portal with fixed cloud QC address and automatic cross-origin sessions; install in `gis-processing-portal`.
- `main.py`: FastAPI app, frontend redirect, CORS, request-size limit and public readiness check.
- `cloud_session.py`: signed sessions and frontend origin configuration; keeps the master key on the server.
- `cloud_gdb_router.py`: authenticated inspection/QC queue, bounded ZIP extraction, status and downloads.
- `cloud_gdb_worker.py`: isolated processing process.
- `cloud_gdb_common.py`: read-only GDB inventory and layer XML metadata.
- `cloud_qc.py`: QC calculations and Excel/JSON result data.
- `curve_geometry.py`: curve control-record matching and private XY approximations for length checks.
- `report_style.py`: Excel formatting.
- `Dockerfile`, `.dockerignore`, `requirements.txt`: cloud environment.

Do not copy only `main.py`: it imports the accompanying modules. Do not replace the conversion backend with this app unless you separately integrate its original routes. Upload the backend folder contents to `gdb_qc_cloud`; upload the index to `gis-processing-portal`.

## Optional environment settings

| Variable | Default |
|---|---|
| QC_API_KEY | Required; service refuses startup without it |
| QC_PORTAL_URL | `https://harikrishnanpnair-alt.github.io/gis-processing-portal/` |
| QC_ALLOWED_ORIGINS | Optional additional origins; configured portal is accepted automatically |
| QC_MAX_UPLOAD_MB | `128` |
| QC_MAX_UNPACKED_MB | `1024` |
| QC_MAX_TOTAL_FEATURES | `250000` |
| QC_MAX_DETAIL_ROWS | `50000` |
| QC_MAX_QUEUED_JOBS | `10` |
| QC_JOB_TIMEOUT_SECONDS | `1800` |
| QC_JOB_ROOT | `/app/qc_jobs` in Docker |

## Optional local developer test

If Docker is already available, build from the backend folder:

```bash
docker build -t gdb-qc-cloud .
docker run --rm -p 8000:8000 -e QC_API_KEY=YOUR_OWN_SECRET -e QC_PORTAL_URL=http://localhost:8080/ gdb-qc-cloud
```

Serve the frontend folder on port 8080 with a local static server. For that local test only, change `QC_API_BASE` in the frontend index to `http://localhost:8000`. The delivered index already points to the actual Render service for end users.
