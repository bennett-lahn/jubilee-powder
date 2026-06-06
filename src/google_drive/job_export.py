"""
Build local file artifacts for Google Drive backup from a JobLog JSON file.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_NA = "#N/A"

_DISPENSING_CSV_COLUMNS = ["well", "target", "actual", "status"]
_HARDNESS_CSV_COLUMNS = ["tray_index", "sample_index", "target", "actual", "status"]


@dataclass
class LocalFile:
    """One file to place under the job folder staging root."""

    relative_path: str
    source_path: Path | None = None
    content: str | None = None


@dataclass
class JobArtifacts:
    """Staged files for one job, rooted at ``stem/``."""

    stem: str
    files: list[LocalFile] = field(default_factory=list)


def job_folder_stem(json_path: Path) -> str:
    return json_path.stem


def load_job_payload(json_path: Path) -> dict:
    return json.loads(json_path.read_text(encoding="utf-8"))


def _require_metadata(payload: dict) -> dict:
    meta = payload.get("metadata")
    if not isinstance(meta, dict):
        raise ValueError("Job log metadata is required")
    if "job_type" not in meta:
        raise ValueError("metadata.job_type is required")
    if meta.get("id") is None:
        raise ValueError("metadata.id is required")
    return meta


def _require_state(payload: dict, job_type: str) -> dict:
    state = payload.get("state")
    if not isinstance(state, dict):
        raise ValueError("Job log state is required")
    if job_type == "dispensing":
        if "molds" not in state:
            raise ValueError("state.molds is required for dispensing jobs")
        if not isinstance(state["molds"], list):
            raise ValueError("state.molds must be a list")
    elif job_type == "hardness":
        if "samples" not in state:
            raise ValueError("state.samples is required for hardness jobs")
        if not isinstance(state["samples"], list):
            raise ValueError("state.samples must be a list")
    return state


def build_artifacts(json_path: Path, files_root: Path) -> JobArtifacts:
    """Return all files to upload for one completed job log."""
    root = files_root
    payload = load_job_payload(json_path)
    meta = _require_metadata(payload)
    job_type = meta["job_type"]
    _require_state(payload, job_type)

    stem = job_folder_stem(json_path)
    artifacts = JobArtifacts(stem=stem)
    artifacts.files.append(
        LocalFile(relative_path=f"{stem}/{json_path.name}", source_path=json_path)
    )

    if job_type == "dispensing":
        _add_dispensing_csv(artifacts, stem, meta, payload)
    elif job_type == "hardness":
        job_id = meta["id"]
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
    job_id: int | None,
    image_ref: str | None,
    files_root: Path,
    tray_index: Any,
    sample_index: int,
    pass_mode: str,
) -> Path | None:
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
    mode = sample["mode"]
    if pass_mode not in _hardness_passes(mode):
        return False
    if _pass_actual(sample, pass_mode) is not None:
        return True
    return bool(sample.get(f"image_path_{pass_mode}"))


def _hardness_csv_row(sample: dict, pass_mode: str) -> dict[str, Any]:
    return {
        "tray_index": sample["tray_index"],
        "sample_index": sample["sample_index"],
        "target": None,
        "actual": _pass_actual(sample, pass_mode),
        "status": _pass_status(sample, pass_mode),
    }


def _add_dispensing_csv(
    artifacts: JobArtifacts, stem: str, meta: dict, payload: dict
) -> None:
    rows = []
    for mold in payload["state"]["molds"]:
        rows.append(
            {
                "well": mold["well_id"],
                "target": mold["target_weight"],
                "actual": mold.get("actual_weight"),
                "status": mold["status"],
            }
        )
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
    job_id: int | None,
) -> None:
    samples = payload["state"]["samples"]
    passes_needed: set[str] = set()
    for sample in samples:
        passes_needed.update(_hardness_passes(sample["mode"]))

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
            tray = int(sample["tray_index"])
            sample_index = int(sample["sample_index"])
            img_key = f"image_path_{pass_mode}"
            image_ref = sample.get(img_key)
            img_path = resolve_image_path(
                job_id,
                image_ref,
                files_root,
                tray,
                sample_index,
                pass_mode,
            )
            if img_path is None:
                if image_ref:
                    logger.info(
                        "Skipping hardness image for job %s tray %s sample %s %s: %r not found",
                        job_id,
                        tray,
                        sample_index,
                        pass_mode,
                        image_ref,
                    )
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
            raise ValueError(
                f"LocalFile has no content or source: {entry.relative_path}"
            )

    return job_dir
