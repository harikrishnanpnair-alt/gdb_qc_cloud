# Validation of this first cloud update

Tested with Python 3.12, Ubuntu GDAL 3.8.4 OpenFileGDB bindings, Shapely 2.2.0 / GEOS 3.14.1 and pyproj 3.8.0. The requirements file pins the application packages used in validation.

Passed:
- Real synthetic File GDB creation, dataset/class path inspection and field/domain extraction.
- Null/blank and zero handling, geodesic line length, exact reversed-line duplicates, empty geometry and strict coded/numeric range domains.
- Schema string-length, missing-field and CRS mismatches; missing reference class marked incomplete.
- Geographic degrees and projected feet measured in metres. Z/M preserved in duplicate comparison as read by OGR.
- Real curved File GDB tests: circular/compound lines, curved polygons, multipart/ring/hole normalization, reversed curves, endpoint Z/M differences and separate linear approximations.
- Curved geodesic lengths checked against a small semicircle reference; curvature notes appear in Excel and source GDB file hashes remain unchanged.
- Direct native OGR geometry tests include control-point Z/M changes. GDAL File GDB curve control ordinates can be reconstructed differently from the supplied OGR write geometry; an ArcGIS-created curve Z/M dataset has not been validated.
- Input GDB file hashes unchanged after QC; Excel opens with summary/details and no executable formulas from source text.
- Authenticated upload, inspection, subprocess QC, polling and Excel download through the FastAPI test client.
- Access-key and origin rejection, preflight CORS, invalid selection/threshold, unsafe ZIP rejection, size limit and download allowlist.
- Browser DOM simulation at the actual GitHub Pages frontend origin: QC requests use the fixed Render backend, bootstrap their own session, retain the token in tab storage, and never send the master API key. Upload/run/download/navigation, curve processing notes in the result table and expiration handling passed.
- Automatic session creation, HttpOnly/Secure/SameSite settings, same-browser owner retention on reload and cross-origin rejection passed.
- Cross-origin CORS preflight and automatic session bootstrapping passed without cookies. The real GDB upload-to-Excel flow passed with the GitHub Pages Origin header. A backend without an index redirects to the main portal instead of returning 500.
- Two separate browser clients: the second client cannot view, reuse or download the first client's QC jobs; the full session-based upload-to-Excel flow passed with real synthetic GDBs.
- Existing administrative API-key requests still pass the API validation tests.
- Existing profile Excel export, requested/actual gaps, missing elevations and stale-response handling.
- Existing CAD profile settings and export, including a long route; both generated DXFs pass ezdxf audit.

Subtype metadata parser was tested with representative XML. A native ArcGIS-created subtype GDB has not been tested. Actual user GDBs, the Docker image build, the live deployment of this revised frontend/backend connection and concurrent-user load have not been tested.
