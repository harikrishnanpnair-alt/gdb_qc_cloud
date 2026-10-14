"""Standalone Docker cloud service. Run exactly one Uvicorn worker."""
from contextlib import asynccontextmanager
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from cloud_gdb_router import router, restore_job_states, MAX_UPLOAD, authorize
from cloud_gdb_worker import engine_health
from cloud_session import issue_cookie


@asynccontextmanager
async def lifespan(app):
    if not os.environ.get("QC_API_KEY", ""):
        raise RuntimeError("Set QC_API_KEY in your cloud environment before starting the service.")
    engine_health()
    restore_job_states()
    yield


app = FastAPI(title="Open-source GDB QC", lifespan=lifespan)
origins = [x.strip() for x in os.environ.get("QC_ALLOWED_ORIGINS", "").split(",") if x.strip()]



class UploadLimit:
    """Count request body bytes before multipart parsing starts."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/gdb/") and scope.get("method") != "OPTIONS":
            try:
                authorize(Request(scope))
            except HTTPException as exc:
                return await JSONResponse({"detail": exc.detail}, status_code=exc.status_code)(scope, receive, send)
        if scope["type"] != "http" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        limit = MAX_UPLOAD + 1024 * 1024  # multipart framing allowance
        headers = dict(scope.get("headers", []))
        try:
            size = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(scope, receive, send)
        if size > limit:
            return await JSONResponse({"detail": "Upload exceeds the configured size limit."}, status_code=413)(scope, receive, send)
        total = 0
        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                raise HTTPException(413, "Upload exceeds the configured size limit.")
            return message
        await self.app(scope, bounded_receive, send)


app.add_middleware(UploadLimit)
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-GDB-Key"])
app.include_router(router)


@app.get("/health", include_in_schema=False)
def readiness():
    return engine_health()


@app.get("/", include_in_schema=False)
def index(request: Request):
    response = FileResponse(Path(__file__).with_name("index.html"), media_type="text/html")
    return issue_cookie(response, request)


@app.get("/index.html", include_in_schema=False)
def index_file(request: Request):
    return index(request)
