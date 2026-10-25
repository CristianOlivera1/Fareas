import csv
import math
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.core.config import get_settings

FIELDS = [
    "capture_id", "frame", "timestamp", "true_alias", "condition",
    "face_px", "det_score", "enrolled_alias", "similarity",
]
NON_ENROLLED = "NONE"
CONDITIONS = ("normal", "adversa", "no_enrolado")
WARMUP_SECONDS = 6.0


class PilotCaptureError(Exception):
    pass


def data_file() -> Path:
    return Path(get_settings().PILOT_DATA_FILE)


def alias_map(student_ids: set[int]) -> dict[int, str]:
    return {sid: f"P{index + 1:02d}" for index, sid in enumerate(sorted(student_ids))}


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def run_capture(
    source,
    detector,
    embedder,
    gallery,
    aliases: dict[int, str],
    true_alias: str,
    condition: str,
    seconds: int,
) -> dict:
    if condition not in CONDITIONS:
        raise PilotCaptureError("Condición de captura no válida")
    deadline_open = time.monotonic() + WARMUP_SECONDS
    frame = None
    while time.monotonic() < deadline_open:
        ok, frame = source.read()
        if ok and frame is not None:
            break
        time.sleep(0.1)
    else:
        raise PilotCaptureError("La cámara no entregó imagen")

    capture_id = uuid.uuid4().hex[:8]
    path = data_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    deadline = time.monotonic() + seconds
    frames_logged = 0
    last_frame = None
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        while time.monotonic() < deadline:
            ok, frame = source.read()
            if not ok or frame is None or frame is last_frame:
                time.sleep(0.02)
                continue
            last_frame = frame
            faces = detector.detect(frame, max_faces=5)
            if not faces:
                continue
            face = max(faces, key=lambda f: (f.box[2] - f.box[0]) * (f.box[3] - f.box[1]))
            similarities = gallery.best_similarities(embedder.get(frame, face.kps))
            frames_logged += 1
            side = int(min(face.box[2] - face.box[0], face.box[3] - face.box[1]))
            stamp = datetime.now().isoformat(timespec="milliseconds")
            for sid, value in similarities.items():
                writer.writerow({
                    "capture_id": capture_id, "frame": frames_logged, "timestamp": stamp,
                    "true_alias": true_alias, "condition": condition, "face_px": side,
                    "det_score": round(float(face.score), 3), "enrolled_alias": aliases[sid],
                    "similarity": round(float(value), 4),
                })
    return {"capture_id": capture_id, "frames": frames_logged, "alias": true_alias, "condition": condition}


def load_captures(path: Path | None = None) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    path = path or data_file()
    captures: dict[str, dict[int, dict]] = defaultdict(dict)
    info: dict[str, dict] = {}
    if not path.exists():
        return {}, {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            frame = captures[row["capture_id"]].setdefault(int(row["frame"]), {"scores": {}})
            frame["scores"][row["enrolled_alias"]] = float(row["similarity"])
            info[row["capture_id"]] = {"true": row["true_alias"], "condition": row["condition"]}
    ordered = {cid: [frames[i] for i in sorted(frames)] for cid, frames in captures.items()}
    return ordered, info


def decide(frames: list[dict], threshold: float, margin: float, confirm: int) -> str | None:
    streak_alias, streak = None, 0
    for frame in frames:
        ranked = sorted(frame["scores"].items(), key=lambda item: item[1], reverse=True)
        best_alias, best = ranked[0]
        rival = ranked[1][1] if len(ranked) > 1 else 0.0
        if best >= threshold and best - rival >= margin:
            streak = streak + 1 if best_alias == streak_alias else 1
            streak_alias = best_alias
            if streak >= confirm:
                return best_alias
        else:
            streak_alias, streak = None, 0
    return None


def attempt_metrics(
    captures: dict[str, list[dict]], info: dict[str, dict], threshold: float, margin: float, confirm: int
) -> dict:
    genuine = correct = rejected = misidentified = impostor = accepted = 0
    for cid, frames in captures.items():
        if not frames:
            continue
        decision = decide(frames, threshold, margin, confirm)
        true_alias = info[cid]["true"]
        if true_alias == NON_ENROLLED:
            impostor += 1
            accepted += decision is not None
        else:
            genuine += 1
            if decision is None:
                rejected += 1
            elif decision == true_alias:
                correct += 1
            else:
                misidentified += 1
    return {
        "genuine": genuine, "correct": correct, "rejected": rejected, "misidentified": misidentified,
        "impostor": impostor, "accepted": accepted,
    }


def frame_curve(captures: dict[str, list[dict]], info: dict[str, dict], thresholds: list[float]) -> list[dict]:
    genuine_scores: list[float] = []
    impostor_scores: list[float] = []
    for cid, frames in captures.items():
        true_alias = info[cid]["true"]
        for frame in frames:
            for alias, value in frame["scores"].items():
                (genuine_scores if alias == true_alias else impostor_scores).append(value)
    rows = []
    for tau in thresholds:
        frr = sum(v < tau for v in genuine_scores) / len(genuine_scores) if genuine_scores else None
        far = sum(v >= tau for v in impostor_scores) / len(impostor_scores) if impostor_scores else None
        rows.append({"threshold": tau, "far": far, "frr": frr})
    return rows


def rate(successes: int, total: int) -> dict:
    low, high = wilson(successes, total)
    return {
        "count": successes, "total": total,
        "value": successes / total if total else None,
        "low": low if total else None, "high": high if total else None,
    }


def summarize(threshold: float, margin: float, confirm: int, path: Path | None = None) -> dict:
    captures, info = load_captures(path)
    result = attempt_metrics(captures, info, threshold, margin, confirm)
    per_alias: dict[str, dict[str, int]] = defaultdict(lambda: {"normal": 0, "adversa": 0})
    unenrolled = 0
    for meta in info.values():
        if meta["true"] == NON_ENROLLED:
            unenrolled += 1
        elif meta["condition"] in ("normal", "adversa"):
            per_alias[meta["true"]][meta["condition"]] += 1
    thresholds = [round(0.30 + 0.05 * index, 2) for index in range(10)]
    return {
        "captures": len(captures),
        "unenrolled_captures": unenrolled,
        "per_alias": dict(per_alias),
        "tar": rate(result["correct"], result["genuine"]),
        "frr": rate(result["rejected"], result["genuine"]),
        "misidentified": rate(result["misidentified"], result["genuine"]),
        "far": rate(result["accepted"], result["impostor"]),
        "curve": frame_curve(captures, info, thresholds),
    }
