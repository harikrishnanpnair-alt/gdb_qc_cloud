# Validation of this first cloud update

Tested with Python 3.12, Ubuntu GDAL 3.8.4 OpenFileGDB bindings, Shapely 2.2.0 / GEOS 3.14.1 and pyproj 3.8.0. The requirements file pins the application packages used in validation.

Passed:
- Real synthetic File GDB creation, dataset/class path inspection and field/domain extraction.
- Null/blank and zero handling, geodesic line length, exact reversed-line duplicates, empty geometry and strict coded/numeric range domains.
- Schema string-length, missing-field and CRS mismatches; missing reference class marked incomplete.
- Geographic degrees and projected feet measured in metres. Z/M preserved in duplicate comparison. Curves explicitly marked incomplete.
- Input GDB file hashes unchanged after QC; Excel opens with summary/details and no executable formulas from source text.
- Authenticated upload, inspection, subprocess QC, polling and Excel download through the FastAPI test client.
- Access-key and origin rejection, preflight CORS, invalid selection/threshold, unsafe ZIP rejection, size limit and download allowlist.
- Browser DOM simulation: QC requests automatically use the page origin and browser session, with no access-key header or URL/key fields. Local Transfer is disabled. Upload, run, download, navigation and expired-session handling passed.
- Automatic session creation, HttpOnly/Secure/SameSite settings, same-browser owner retention on reload and cross-origin rejection passed.
- Two separate browser clients: the second client cannot view, reuse or download the first client's QC jobs; the full session-based upload-to-Excel flow passed with real synthetic GDBs.
- Existing administrative API-key requests still pass the API validation tests.
- Existing profile Excel export, requested/actual gaps, missing elevations and stale-response handling.
- Existing CAD profile settings and export, including a long route; both generated DXFs pass ezdxf audit.

Subtype metadata parser was tested with representative XML. A native ArcGIS-created subtype GDB has not been tested. Actual user GDBs, the Docker image build, live Render deployment and concurrent-user load have not been tested.
