"""
Build local file artifacts for Google Drive backup from a JobLog JSON file.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_FILES_ROOT = Path(__file__).parent.parent.parent / "frontend" / "api" / "files"
_NA = "#N/A"

_DISPENSING_CSV_COLUMNS = ["well", "target", "actual", "status"]
_HARDNESS_CSV_COLUMNS = ["tray_index", "sample_index", "target", "actual", "status"]


@dataclass
class LocalFile:
    """One file to place under the job folder staging root."""

    relative_path: str
    source_path: Optional[Path] = None
    content: Optional[str] = None


@dataclass
class JobArtifacts:
    """Staged files for one job, rooted at ``stem/``."""

    stem: str
    files: list[LocalFile] = field(default_factory=list)


def job_folder_stem(json_path: Path) -> str:
    return json_path.stem


def load_job_payload(json_path: Path) -> dict:
    return json.loads(json_path.read_text(encoding="utf-8"))


def build_artifacts(json_path: Path, files_root: Optional[Path] = None) -> JobArtifacts:
    """Return all files to upload for one completed job log."""
    root = files_root or _FILES_ROOT
    payload = load_job_payload(json_path)
    meta = payload.get("metadata", {})
    job_type = meta.get("job_type", "")

    stem = job_folder_stem(json_path)
    artifacts = JobArtifacts(stem=stem)
    artifacts.files.append(
        LocalFile(relative_path=f"{stem}/{json_path.name}", source_path=json_path)
    )

    if job_type == "dispensing":
        _add_dispensing_csv(artifacts, stem, meta, payload)
    elif job_type == "hardness":
        job_id = meta.get("id")
        _add_hardness_tree(artifacts, stem, meta, payload, root, job_id)
    else:
        raise ValueError(f"Unsupported job_type for Drive export: {job_type!r}")

    return artifacts


def format_csv(
    metadata: dict,
    rows: list[dict[str, Any]],
    columns: list[str],
) -> str:
    """Metadata row (alternating key/value), header row, then data."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")

    meta_row: list[Any] = []
    for key, value in metadata.items():
        meta_row.extend([key, _cell(value)])
    writer.writerow(meta_row)

    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(col)) for col in columns])
    return buf.getvalue()


def resolve_image_path(
    job_id: Optional[int],
    image_ref: Optional[str],
    files_root: Path,
    tray_index: Any,
    sample_index: int,
    pass_mode: str,
) -> Optional[Path]:
    """Resolve a local image path from a JSON URL or predictable filename."""
    if image_ref:
        m = re.search(r"/api/files/images/(\d+)/([^/]+)$", str(image_ref))
        if m:
            path = files_root / "images" / m.group(1) / m.group(2)
            if path.is_file():
                return path

    if job_id is not None:
        filename = f"{tray_index}_{sample_index}_{pass_mode}.jpg"
        path = files_root / "images" / f"{int(job_id):04d}" / filename
        if path.is_file():
            return path
    return None


def _cell(value: Any) -> str:
    if value is None or value == "":
        return _NA
    return str(value)


def _hardness_passes(sample_mode: str) -> list[str]:
    if sample_mode == "shore_a":
        return ["shore_a"]
    if sample_mode == "shore_d":
        return ["shore_d"]
    if sample_mode == "shore_a_d":
        return ["shore_a", "shore_d"]
    return []


def _pass_actual(sample: dict, pass_mode: str) -> Any:
    if pass_mode == "shore_a":
        return sample.get("result_shore_a")
    return sample.get("result_shore_d")


def _pass_status(sample: dict, pass_mode: str) -> str:
    """Per-pass status is always set by JobLog for passes that apply to the sample."""
    return str(sample[f"status_{pass_mode}"])


def _sample_in_pass(sample: dict, pass_mode: str) -> bool:
    mode = sample.get("mode", "")
    if pass_mode not in _hardness_passes(mode):
        return False
    if _pass_actual(sample, pass_mode) is not None:
        return True
    return bool(sample.get(f"image_path_{pass_mode}"))


def _hardness_csv_row(sample: dict, pass_mode: str) -> dict[str, Any]:
    tray_index = sample.get("tray_index")
    if tray_index is None:
        tray_index = _NA
    return {
        "tray_index": tray_index,
        "sample_index": sample.get("sample_index", _NA),
        "target": None,
        "actual": _pass_actual(sample, pass_mode),
        "status": _pass_status(sample, pass_mode),
    }


def _add_dispensing_csv(artifacts: JobArtifacts, stem: str, meta: dict, payload: dict) -> None:
    rows = []
    for mold in payload.get("state", {}).get("molds", []):
        rows.append({
            "well": mold.get("well_id"),
            "target": mold.get("target_weight"),
            "actual": mold.get("actual_weight"),
            "status": mold.get("status"),
        })
    csv_text = format_csv(meta, rows, _DISPENSING_CSV_COLUMNS)
    artifacts.files.append(
        LocalFile(relative_path=f"{stem}/results.csv", content=csv_text)
    )


def _add_hardness_tree(
    artifacts: JobArtifacts,
    stem: str,
    meta: dict,
    payload: dict,
    files_root: Path,
    job_id: Optional[int],
) -> None:
    samples = payload.get("state", {}).get("samples", [])
    passes_needed: set[str] = set()
    for sample in samples:
        passes_needed.update(_hardness_passes(sample.get("mode", "")))

    for pass_mode in ("shore_a", "shore_d"):
        if pass_mode not in passes_needed:
            continue
        pass_samples = [s for s in samples if _sample_in_pass(s, pass_mode)]
        if not pass_samples:
            continue

        pass_meta = {**meta, "pass": pass_mode}
        rows = []
        for sample in pass_samples:
            rows.append(_hardness_csv_row(sample, pass_mode))
        csv_text = format_csv(pass_meta, rows, _HARDNESS_CSV_COLUMNS)
        artifacts.files.append(
            LocalFile(
                relative_path=f"{stem}/{pass_mode}/results.csv",
                content=csv_text,
            )
        )

        for sample in pass_samples:
            tray = int(sample.get("tray_index", 0))
            sample_index = sample.get("sample_index")
            if sample_index is None:
                continue
            img_key = f"image_path_{pass_mode}"
            img_path = resolve_image_path(
                job_id,
                sample.get(img_key),
                files_root,
                tray,
                int(sample_index),
                pass_mode,
            )
            if img_path is None:
                continue
            filename = img_path.name
            artifacts.files.append(
                LocalFile(
                    relative_path=f"{stem}/{pass_mode}/images/{filename}",
                    source_path=img_path,
                )
            )


def stage_artifacts(artifacts: JobArtifacts, staging_root: Path) -> Path:
    """Write all artifact files under ``staging_root / stem``."""
    job_dir = staging_root / artifacts.stem
    job_dir.mkdir(parents=True, exist_ok=True)

    for entry in artifacts.files:
        dest = staging_root / entry.relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if entry.source_path is not None:
            shutil.copy2(entry.source_path, dest)
        elif entry.content is not None:
            dest.write_text(entry.content, encoding="utf-8")
        else:
            raise ValueError(f"LocalFile has no content or source: {entry.relative_path}")

    return job_dir
