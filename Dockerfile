FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-gdal gdal-bin ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /opt/venv
ENV PATH="/opt/venv/bin:$PATH" QC_JOB_ROOT=/app/qc_jobs
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "from osgeo import gdal; assert gdal.GetDriverByName('OpenFileGDB')"
RUN useradd --create-home gisapp && mkdir /app/qc_jobs && chown gisapp:gisapp /app/qc_jobs
COPY . .
USER gisapp
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
