from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageOps

from . import db, paths

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".bmp", ".gif"}
VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS
GALLERY_EXTS = {".jpg", ".jpeg", ".png", ".webp"} | VIDEO_EXTS

VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
}

MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "AVIF": "image/avif",
    "GIF": "image/gif",
    "BMP": "image/bmp",
}


def is_video(path: Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


def iter_media(root: Path):
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = Path(dirpath) / name
            if path.suffix.lower() in MEDIA_EXTS and path.is_file():
                yield path


def probe_media(path: Path) -> tuple[int, int, str | None] | None:
    if not is_video(path):
        return probe_image(path)
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=s=x:p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode != 0:
            return None
        width, height = result.stdout.strip().splitlines()[0].split("x")
        return int(width), int(height), VIDEO_MIME.get(path.suffix.lower())
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def media_hashes(path: Path, sha256: str) -> tuple[str | None, str | None]:
    if not is_video(path):
        return dhash(path), phash(path)
    thumb = make_thumbnail(path, sha256)
    if thumb is None:
        return None, None
    return dhash(thumb), phash(thumb)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def probe_image(path: Path) -> tuple[int, int, str | None] | None:
    try:
        with Image.open(path) as image:
            width, height = image.size
            return int(width), int(height), MIME_BY_FORMAT.get((image.format or "").upper())
    except Exception:
        return None


def dhash(path: Path, size: int = 8) -> str | None:
    try:
        with Image.open(path) as image:
            image = image.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
            data = image.tobytes()
        bits = 0
        for row in range(size):
            offset = row * (size + 1)
            for column in range(size):
                bits = (bits << 1) | int(data[offset + column] > data[offset + column + 1])
        return f"{bits:0{size * size // 4}x}"
    except Exception:
        return None


def _dct_matrix(size: int = 32) -> np.ndarray:
    k = np.arange(size)[:, None]
    n = np.arange(size)[None, :]
    matrix = np.cos(np.pi * (2 * n + 1) * k / (2 * size))
    matrix[0, :] *= 1 / np.sqrt(2)
    return matrix * np.sqrt(2 / size)


_PHASH_DCT = _dct_matrix(32)


def phash(path: Path, hash_size: int = 8) -> str | None:
    """64-bit DCT perceptual hash (pHash), stable across re-encodes/resizes."""
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
            pixels = np.asarray(image, dtype=np.float64)
        if float(pixels.std()) < 4.0:
            # Solid/near-solid images collide in perceptual hash space. SHA-256
            # still handles exact duplicates, so leave pHash empty here.
            return None
        coefficients = _PHASH_DCT @ pixels @ _PHASH_DCT.T
        low = coefficients[:hash_size, :hash_size]
        median = float(np.median(low))
        bits = 0
        for value in low.ravel():
            bits = (bits << 1) | int(value > median)
        return f"{bits:016x}"
    except Exception:
        return None


def hamming_hex(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _best_similar(
    candidates: list[dict],
    phash_value: str | None,
    threshold: int,
    width: int | None = None,
    height: int | None = None,
) -> tuple[dict, int] | None:
    if not phash_value or threshold <= 0:
        return None
    target = int(phash_value, 16)
    aspect = (width / height) if width and height else None
    best: tuple[dict, int] | None = None
    for candidate in candidates:
        value = candidate.get("phash")
        if not value:
            continue
        if aspect is not None and candidate.get("width") and candidate.get("height"):
            candidate_aspect = candidate["width"] / candidate["height"]
            if max(aspect, candidate_aspect) / min(aspect, candidate_aspect) > 1.08:
                continue
        try:
            distance = (target ^ int(value, 16)).bit_count()
        except ValueError:
            continue
        if distance <= threshold and (best is None or distance < best[1]):
            best = (candidate, distance)
    return best


def find_similar(
    connection,
    phash_value: str | None,
    threshold: int = 8,
    width: int | None = None,
    height: int | None = None,
) -> tuple[dict, int] | None:
    rows = connection.execute(
        "SELECT id, path, sha256, phash, width, height FROM assets WHERE phash IS NOT NULL"
    ).fetchall()
    return _best_similar(
        [dict(row) for row in rows], phash_value, threshold, width, height
    )


def thumb_path(sha256: str) -> Path:
    return paths.THUMB_DIR / sha256[:2] / f"{sha256}.jpg"


def make_thumbnail(source: Path, sha256: str, size: int = 512) -> Path | None:
    destination = thumb_path(sha256)
    if destination.exists():
        return destination
    if is_video(source):
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.stem + ".tmp.jpg")
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale={size}:-2",
                    "-q:v",
                    "2",
                    str(temporary),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode == 0 and temporary.exists():
                temporary.replace(destination)
                return destination
            temporary.unlink(missing_ok=True)
            return None
        except (OSError, subprocess.TimeoutExpired):
            return None
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
            if image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, (12, 12, 14))
                background.paste(image, mask=image.split()[-1])
                image = background
            else:
                image = image.convert("RGB")
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "JPEG", quality=88, optimize=True)
        return destination
    except Exception:
        return None


def _rotate_image_file(source: Path, destination: Path, degrees: int) -> None:
    suffix = source.suffix.lower()
    if suffix in {".gif", ".webp"}:
        with Image.open(source) as image:
            if getattr(image, "n_frames", 1) > 1:
                raise ValueError("animated images cannot be rotated")

    orientation = 1
    if suffix in {".jpg", ".jpeg"}:
        try:
            with Image.open(source) as image:
                orientation = int(image.getexif().get(274, 1) or 1)
        except Exception:
            orientation = 1
        if orientation == 1 and shutil.which("jpegtran"):
            destination.unlink(missing_ok=True)
            result = subprocess.run(
                [
                    "jpegtran",
                    "-rotate",
                    str(degrees % 360),
                    "-copy",
                    "all",
                    "-optimize",
                    "-outfile",
                    str(destination),
                    str(source),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode == 0 and destination.exists() and destination.stat().st_size:
                return
            destination.unlink(missing_ok=True)

    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original)
        if degrees % 360 == 90:
            image = image.transpose(Image.Transpose.ROTATE_270)
        elif degrees % 360 == 180:
            image = image.transpose(Image.Transpose.ROTATE_180)
        elif degrees % 360 == 270:
            image = image.transpose(Image.Transpose.ROTATE_90)
        else:
            raise ValueError("rotation must be a multiple of 90 degrees")
        format_name = {
            ".jpg": "JPEG",
            ".jpeg": "JPEG",
            ".png": "PNG",
            ".webp": "WEBP",
            ".avif": "AVIF",
            ".bmp": "BMP",
            ".gif": "GIF",
        }.get(suffix)
        if format_name is None:
            raise ValueError(f"unsupported image format: {suffix}")
        save_kwargs: dict[str, Any] = {}
        if format_name == "JPEG":
            save_kwargs.update(quality=95, subsampling=0, optimize=True)
            exif = original.getexif()
            if exif:
                exif[274] = 1
                save_kwargs["exif"] = exif.tobytes()
        elif format_name == "PNG":
            save_kwargs["optimize"] = True
        elif format_name == "WEBP":
            save_kwargs.update(lossless=True, method=6)
        elif format_name == "AVIF":
            save_kwargs["quality"] = 95
        elif format_name == "GIF":
            save_kwargs["optimize"] = False
        icc_profile = original.info.get("icc_profile")
        if icc_profile:
            save_kwargs["icc_profile"] = icc_profile
        image.save(destination, format_name, **save_kwargs)


def rotate_asset(db_path: Path, asset_id: int, degrees: int = 90) -> dict[str, Any]:
    """Rotate an image in place and refresh its metadata and thumbnail."""
    if degrees % 90 != 0:
        raise ValueError("rotation must be a multiple of 90 degrees")
    with db.connect(db_path) as connection:
        row = connection.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        raise ValueError("asset not found")
    path = Path(row["path"])
    if not path.is_file():
        raise ValueError("image file is missing")
    if is_video(path) or str(row["mime"] or "").startswith("video/"):
        raise ValueError("only still images can be rotated")

    stat = path.stat()
    temporary = path.with_name(f".{path.name}.rotate-{os.getpid()}{path.suffix}")
    try:
        _rotate_image_file(path, temporary, degrees)
        new_sha = sha256_file(temporary)
        with db.connect(db_path) as connection:
            existing = db.asset_by_sha(connection, new_sha)
        if existing is not None and int(existing["id"]) != asset_id:
            raise ValueError("rotated image duplicates another asset")
        probe = probe_image(temporary)
        if probe is None:
            raise ValueError("rotated image is unreadable")
        width, height, mime = probe
        new_size = temporary.stat().st_size
        new_dhash = dhash(temporary)
        new_phash = phash(temporary)
        os.chmod(temporary, stat.st_mode)
        os.replace(temporary, path)
        make_thumbnail(path, new_sha)
        db.update_asset_media(
            asset_id,
            sha256=new_sha,
            width=width,
            height=height,
            size=new_size,
            mime=mime,
            dhash=new_dhash,
            phash=new_phash,
        )
        old_sha = str(row["sha256"])
        if old_sha != new_sha:
            thumb_path(old_sha).unlink(missing_ok=True)
        return {
            "id": asset_id,
            "path": str(path),
            "sha256": new_sha,
            "width": width,
            "height": height,
            "bytes": new_size,
            "mime": mime,
        }
    finally:
        temporary.unlink(missing_ok=True)


ProgressCallback = Callable[[int, int, Path], None]
CancelCallback = Callable[[], bool]


def import_folder(
    db_path: Path,
    root: Path,
    *,
    on_progress: ProgressCallback | None = None,
    cancel: CancelCallback | None = None,
) -> dict[str, int]:
    root = Path(root)
    counts = {"imported": 0, "duplicate": 0, "skipped": 0, "failed": 0}
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")

    files = list(iter_media(root))
    total = len(files)
    connection = db.connect(db_path)
    try:
        for index, path in enumerate(files, 1):
            if cancel and cancel():
                break
            if on_progress:
                on_progress(index, total, path)
            if db.asset_by_path(connection, path) is not None:
                counts["skipped"] += 1
                continue
            try:
                sha256 = sha256_file(path)
            except OSError:
                counts["failed"] += 1
                continue
            if db.asset_by_sha(connection, sha256) is not None:
                counts["duplicate"] += 1
                continue
            probe = probe_media(path)
            if probe is None:
                counts["failed"] += 1
                continue
            width, height, mime = probe
            stat = path.stat()
            make_thumbnail(path, sha256)
            dhash_value, phash_value = media_hashes(path, sha256)
            asset_id, created = db.insert_asset(
                connection,
                sha256=sha256,
                path=path,
                width=width,
                height=height,
                size=stat.st_size,
                mime=mime,
                origin="local",
                dhash=dhash_value,
                phash=phash_value,
                created_at=int(stat.st_mtime),
            )
            if not created:
                counts["duplicate"] += 1
                continue
            counts["imported"] += 1
            if index % 25 == 0:
                connection.commit()
        connection.commit()
    finally:
        connection.close()
    return counts


def _json_date(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            pass
        try:
            return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    return None


def sidecar_for(path: Path) -> dict[str, Any]:
    for candidate in (Path(str(path) + ".json"), path.with_suffix(".json")):
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (OSError, ValueError):
                pass
    return {}


def _safe_component(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return value or "unknown"


def _source_fields(
    path: Path, metadata: dict[str, Any], requested_user: str
) -> tuple[str, int, str, str, int | None]:
    user = requested_user
    author_info = metadata.get("author") or metadata.get("user") or {}
    if isinstance(author_info, dict):
        author = author_info.get("name") or author_info.get("nick") or user
    else:
        author = str(author_info) or user
    tweet_id = metadata.get("tweet_id") or metadata.get("id")
    match = re.match(r"^(\d+)_(\d+)$", path.stem)
    if tweet_id is None and match:
        tweet_id = match.group(1)
    media_index = metadata.get("num")
    if media_index is None and match:
        media_index = int(match.group(2))
    try:
        media_index = int(media_index) if media_index is not None else 0
    except (TypeError, ValueError):
        media_index = 0
    post_id = str(tweet_id) if tweet_id is not None else path.stem
    posted_at = _json_date(metadata.get("date"))
    if post_id.isdigit():
        url = f"https://x.com/{author}/status/{post_id}"
    else:
        candidate = metadata.get("url")
        url = candidate if isinstance(candidate, str) and candidate.startswith("http") else ""
    return post_id, media_index, author or user, url, posted_at


def import_x_downloads(
    db_path: Path,
    library: Path,
    staging: Path,
    requested_user: str,
    *,
    similar_threshold: int = 8,
    ready: Callable[[Path], bool] | None = None,
    prune: bool = True,
    log: Callable[[str], None] | None = None,
    cancel: CancelCallback | None = None,
) -> dict[str, int]:
    library = Path(library)
    staging = Path(staging)
    counts = {"downloaded": 0, "duplicate": 0, "similar": 0, "skipped": 0, "failed": 0}
    files = [
        path
        for path in iter_media(staging)
        if path.suffix.lower() in GALLERY_EXTS and (ready is None or ready(path))
    ]
    connection = db.connect(db_path)
    candidates = [
        dict(row)
        for row in connection.execute(
            "SELECT id, path, sha256, phash, width, height FROM assets WHERE phash IS NOT NULL"
        ).fetchall()
    ]
    try:
        for path in files:
            if cancel and cancel():
                break
            metadata = sidecar_for(path)
            post_id, media_index, author, url, posted_at = _source_fields(
                path, metadata, requested_user
            )
            source = db.source_by_key(connection, "x", requested_user, post_id, media_index)
            if source is not None and source["asset_id"] is not None:
                counts["skipped"] += 1
                _remove_media(path)
                continue
            try:
                sha256 = sha256_file(path)
            except OSError:
                counts["failed"] += 1
                continue

            existing = db.asset_by_sha(connection, sha256)
            if existing is not None:
                db.add_source(
                    connection,
                    platform="x",
                    user=requested_user,
                    post_id=post_id,
                    media_index=media_index,
                    url=url,
                    author=author,
                    posted_at=posted_at,
                    asset_id=int(existing["id"]),
                    status="duplicate",
                    match_asset_id=int(existing["id"]),
                    match_distance=0,
                    match_kind="sha256",
                )
                make_thumbnail(Path(existing["path"]), sha256)
                counts["duplicate"] += 1
                _remove_media(path)
                continue

            probe = probe_media(path)
            if probe is None:
                counts["failed"] += 1
                if log:
                    log(f"Skipping unreadable media: {path.name}")
                continue
            width, height, mime = probe
            make_thumbnail(path, sha256)
            dhash_value, phash_value = media_hashes(path, sha256)
            similar = _best_similar(candidates, phash_value, similar_threshold, width, height)
            if similar is not None:
                candidate, distance = similar
                db.add_source(
                    connection,
                    platform="x",
                    user=requested_user,
                    post_id=post_id,
                    media_index=media_index,
                    url=url,
                    author=author,
                    posted_at=posted_at,
                    asset_id=int(candidate["id"]),
                    status="similar",
                    match_asset_id=int(candidate["id"]),
                    match_distance=distance,
                    match_kind="phash",
                )
                make_thumbnail(Path(candidate["path"]), candidate["sha256"])
                counts["similar"] += 1
                _remove_media(path)
                if log:
                    log(
                        f"Similar to {Path(candidate['path']).name} "
                        f"(pHash distance {distance}); not storing a duplicate"
                    )
                continue
            destination = library / "x" / _safe_component(requested_user) / (
                f"{post_id}_{media_index}{path.suffix.lower()}"
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                destination = destination.with_name(
                    f"{destination.stem}-{sha256[:8]}{destination.suffix}"
                )
            try:
                shutil.move(str(path), str(destination))
            except OSError as error:
                counts["failed"] += 1
                if log:
                    log(f"Could not move {path.name}: {error}")
                continue
            _remove_media(path)

            asset_id, created = db.insert_asset(
                connection,
                sha256=sha256,
                path=destination,
                width=width,
                height=height,
                size=destination.stat().st_size,
                mime=mime,
                origin="x",
                dhash=dhash_value,
                phash=phash_value,
            )
            db.add_source(
                connection,
                platform="x",
                user=requested_user,
                post_id=post_id,
                media_index=media_index,
                url=url,
                author=author,
                posted_at=posted_at,
                asset_id=asset_id,
                status="downloaded" if created else "duplicate",
            )
            make_thumbnail(destination, sha256)
            counts["downloaded" if created else "duplicate"] += 1
            if created and phash_value:
                candidates.append(
                    {
                        "id": asset_id,
                        "path": str(destination),
                        "sha256": sha256,
                        "phash": phash_value,
                        "width": width,
                        "height": height,
                    }
                )
        connection.commit()
    finally:
        connection.close()
    if prune:
        _prune_empty(staging)
    return counts


def _remove_media(path: Path) -> None:
    for candidate in (path, Path(str(path) + ".json"), path.with_suffix(".json")):
        try:
            candidate.unlink()
        except OSError:
            pass


def _prune_empty(root: Path) -> None:
    for dirpath, _dirnames, _filenames in os.walk(root, topdown=False):
        directory = Path(dirpath)
        if directory == root:
            continue
        try:
            directory.rmdir()
        except OSError:
            pass


def ensure_thumbnail_for(asset: dict[str, Any]) -> None:
    path = Path(asset["path"])
    make_thumbnail(path, asset["sha256"])


def scan_duplicates(
    db_path: Path,
    threshold: int = 8,
    *,
    progress: Callable[[int, int, str], None] | None = None,
    log: Callable[[str], None] | None = None,
    cancel: CancelCallback | None = None,
) -> list[list[dict[str, Any]]]:
    """Compute missing pHashes and return groups of visually similar assets."""
    if threshold <= 0:
        return []
    connection = db.connect(db_path)
    try:
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT a.id, a.path, a.sha256, a.width, a.height, a.bytes, a.phash, a.origin, "
                "  (SELECT user FROM sources s WHERE s.asset_id = a.id AND s.platform = 'x' "
                "   ORDER BY s.id LIMIT 1) AS source_user "
                "FROM assets a ORDER BY a.id"
            ).fetchall()
        ]
        total = len(rows)
        values: dict[int, int] = {}
        for index, row in enumerate(rows, 1):
            if cancel and cancel():
                return []
            value = row.get("phash")
            if not value:
                if is_video(Path(row["path"])):
                    thumb = thumb_path(row["sha256"])
                    if not thumb.exists():
                        make_thumbnail(Path(row["path"]), row["sha256"])
                    value = phash(thumb) if thumb.exists() else None
                else:
                    value = phash(Path(row["path"]))
                if value:
                    connection.execute(
                        "UPDATE assets SET phash = ? WHERE id = ?", (value, row["id"])
                    )
                    row["phash"] = value
                    if index % 25 == 0:
                        connection.commit()
            if value:
                try:
                    values[int(row["id"])] = int(value, 16)
                except (TypeError, ValueError):
                    pass
            if progress and (index == 1 or index == total or index % 10 == 0):
                progress(index, total, "fingerprints")
        connection.commit()

        ids = list(values)
        parent = {asset_id: asset_id for asset_id in ids}

        def find(asset_id: int) -> int:
            while parent[asset_id] != asset_id:
                parent[asset_id] = parent[parent[asset_id]]
                asset_id = parent[asset_id]
            return asset_id

        def union(left: int, right: int) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        count = len(ids)
        for index, left_id in enumerate(ids):
            if cancel and cancel():
                return []
            if progress and index % 25 == 0:
                progress(index, count, "compare")
            left = values[left_id]
            for right_id in ids[index + 1 :]:
                if (left ^ values[right_id]).bit_count() <= threshold:
                    union(left_id, right_id)

        buckets: dict[int, list[int]] = {}
        for asset_id in ids:
            buckets.setdefault(find(asset_id), []).append(asset_id)
        by_id = {row["id"]: row for row in rows}
        groups = [
            sorted((by_id[asset_id] for asset_id in bucket), key=lambda row: row["bytes"] or 0, reverse=True)
            for bucket in buckets.values()
            if len(bucket) > 1
        ]
        groups.sort(key=lambda group: sum(row["bytes"] or 0 for row in group), reverse=True)
        if log:
            log(f"Duplicate scan: {len(groups)} group(s) at pHash threshold {threshold}")
        return groups
    finally:
        connection.close()


def delete_assets(
    db_path: Path,
    delete_ids: set[int],
    keep_by_id: dict[int, int],
    *,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Delete assets, repoint their sources to a kept asset, and trash files."""
    connection = db.connect(db_path)
    deleted = 0
    freed = 0
    trashed = 0
    permanently_deleted = 0
    errors: list[str] = []
    try:
        for asset_id in sorted(delete_ids):
            row = connection.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
            if row is None:
                continue
            keep_id = keep_by_id.get(asset_id)
            if keep_id is None or keep_id == asset_id:
                errors.append(f"no kept asset for {row['path']}")
                continue
            if keep_id in delete_ids:
                errors.append(f"kept asset would also be deleted: {row['path']}")
                continue
            path = Path(row["path"])
            if path.exists():
                method = None
                if shutil.which("gio"):
                    result = subprocess.run(
                        ["gio", "trash", str(path)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                    )
                    if result.returncode == 0:
                        method = "trash"
                        trashed += 1
                if method is None:
                    try:
                        path.unlink()
                        method = "unlink"
                        permanently_deleted += 1
                    except OSError as error:
                        errors.append(f"{path}: {error}")
                        continue
            keep = connection.execute(
                "SELECT id FROM assets WHERE id = ?", (keep_id,)
            ).fetchone()
            if keep is None:
                errors.append(f"kept asset {keep_id} no longer exists")
                continue
            connection.execute(
                "UPDATE sources SET asset_id = ? WHERE asset_id = ?", (keep_id, asset_id)
            )
            connection.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
            try:
                thumb_path(row["sha256"]).unlink(missing_ok=True)
            except OSError:
                pass
            deleted += 1
            freed += int(row["bytes"] or 0)
            connection.commit()
            if log:
                log(f"Deleted {path} (kept asset {keep_id})")
    finally:
        connection.close()
    return {
        "deleted": deleted,
        "freed": freed,
        "trashed": trashed,
        "permanent": permanently_deleted,
        "errors": errors,
    }


def _trash_file(path: Path) -> tuple[bool, str]:
    if shutil.which("gio") is None:
        return False, "gio not found"
    result = subprocess.run(
        ["gio", "trash", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return False, detail or f"gio exited with {result.returncode}"
    return True, ""


def trash_assets(
    db_path: Path,
    asset_ids: set[int],
    *,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Move assets to the system trash and remove their library rows."""
    connection = db.connect(db_path)
    deleted = 0
    freed = 0
    errors: list[str] = []
    try:
        for asset_id in sorted(asset_ids):
            row = connection.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
            if row is None:
                continue
            path = Path(row["path"])
            if path.exists():
                ok, detail = _trash_file(path)
                if not ok:
                    errors.append(f"{path}: {detail}")
                    continue
            connection.execute(
                "UPDATE sources SET asset_id = NULL, status = 'deleted' WHERE asset_id = ?",
                (asset_id,),
            )
            connection.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
            try:
                thumb_path(row["sha256"]).unlink(missing_ok=True)
            except OSError:
                pass
            deleted += 1
            freed += int(row["bytes"] or 0)
            connection.commit()
            if log:
                log(f"Moved to trash: {path}")
    finally:
        connection.close()
    return {"deleted": deleted, "freed": freed, "errors": errors}
