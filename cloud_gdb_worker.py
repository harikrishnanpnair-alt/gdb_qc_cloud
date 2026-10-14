"""Fresh read-only GDAL process for each inspection or QC job."""
from pathlib import Path
import json
import sys
import traceback
from osgeo import gdal
from cloud_gdb_common import inventory


def write_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def engine_health():
    if gdal.GetDriverByName("OpenFileGDB") is None:
        raise RuntimeError("GDAL OpenFileGDB driver is unavailable.")
    return {"ready": True, "engine": "GDAL/OGR OpenFileGDB", "gdal_version": gdal.VersionInfo("RELEASE_NAME")}


def perform(task_path):
    task_path = Path(task_path).resolve()
    task = json.loads(task_path.read_text(encoding="utf-8"))
    root = task_path.parent
    if task["action"] == "inspect":
        rows = inventory(task["gdb"])
        return {"classes": rows, "class_count": len(rows), "gdb_name": Path(task["gdb"]).name}
    if task["action"] != "qc":
        raise ValueError("This cloud service supports inspection and QC only.")
    from cloud_qc import run_qc
    def progress(fraction, message):
        write_json(root / "worker_status.json", {"progress": round(fraction * 90, 1), "message": message})
    result = run_qc(task["input_gdb"], task["schema_gdb"], root / "GDB_QC_Report.xlsx", task["short_limit_m"], task.get("selected"), progress)
    write_json(root / "QC_Summary.json", result)
    result["artifacts"] = [{"name": "GDB_QC_Report.xlsx", "label": "QC Excel report"}, {"name": "QC_Summary.json", "label": "QC summary JSON"}]
    return result


if __name__ == "__main__":
    try:
        task_file = Path(sys.argv[1])
        write_json(task_file.parent / "result.json", perform(task_file))
    except Exception as exc:
        traceback.print_exc()
        if len(sys.argv) > 1:
            write_json(Path(sys.argv[1]).parent / "worker_error.json", {"error": str(exc)})
        sys.exit(1)
