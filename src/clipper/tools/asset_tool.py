"""CLI de validação técnica e sincronização do catálogo de assets de motion design."""
import argparse
import json
import logging
import os
import subprocess
import sys
import wave
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

from clipper.core.schemas import (
    AssetItem,
    AssetManifest,
    AssetPosition,
    AssetType,
)
from clipper.runtime.config import PROJECT_ROOT
from clipper.video.asset_resolver import AssetValidationResult

logger = logging.getLogger(__name__)


def inspect_media_file(file_path: Path) -> AssetValidationResult:
    """Inspeciona arquivo de vídeo, imagem ou áudio, verificando canal alfa, codec e dimensões."""
    suffix = file_path.suffix.lower()
    errors: List[str] = []
    warnings: List[str] = []
    has_alpha = False
    dimensions: Optional[Tuple[int, int]] = None
    duration: Optional[float] = None
    asset_type = "unknown"

    if suffix in (".webm", ".mov", ".mp4"):
        asset_type = "animated_video"
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,pix_fmt,duration",
                "-show_entries", "format=duration",
                "-of", "json",
                str(file_path),
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10, check=False
            )
            if result.returncode != 0:
                errors.append(f"ffprobe failed: {result.stderr.strip()}")
            else:
                data = json.loads(result.stdout)
                streams = data.get("streams", [])
                format_info = data.get("format", {})

                if not streams:
                    errors.append("No video stream found in file.")
                else:
                    v_stream = streams[0]
                    w = int(v_stream.get("width", 0))
                    h = int(v_stream.get("height", 0))
                    pix_fmt = v_stream.get("pix_fmt", "")
                    dimensions = (w, h)

                    # Dimensões pares obrigatórias
                    if w % 2 != 0 or h % 2 != 0:
                        errors.append(f"Dimensions {w}x{h} are not even (required for H.264 compatibility).")

                    # Canal alfa
                    if "a" in pix_fmt or pix_fmt in ("yuva420p", "yuva444p", "rgba", "bgra"):
                        has_alpha = True
                    else:
                        errors.append(
                            f"Video stream lacks alpha channel (pix_fmt: '{pix_fmt}'). Transparency requires VP9/VP8 with alpha."
                        )

                    # Duração
                    raw_dur = v_stream.get("duration") or format_info.get("duration")
                    if raw_dur:
                        duration = float(raw_dur)
                        if duration > 5.0:
                            warnings.append(f"Duration {duration:.1f}s exceeds recommended max duration (5.0s).")

        except Exception as exc:
            errors.append(f"Failed to inspect video: {exc}")

    elif suffix in (".png", ".webp"):
        asset_type = "icon_with_card"
        try:
            with Image.open(file_path) as img:
                w, h = img.size
                dimensions = (w, h)
                if w % 2 != 0 or h % 2 != 0:
                    errors.append(f"Dimensions {w}x{h} are not even.")
                if img.mode == "RGBA" or "transparency" in img.info:
                    has_alpha = True
                else:
                    errors.append(f"Image mode '{img.mode}' lacks alpha transparency (RGBA required).")
        except Exception as exc:
            errors.append(f"Failed to inspect image: {exc}")

    elif suffix in (".wav", ".mp3"):
        asset_type = "sfx"
        try:
            if suffix == ".wav":
                with wave.open(str(file_path), "r") as wav:
                    frames = wav.getnframes()
                    rate = wav.getframerate()
                    duration = frames / float(rate)
            else:
                duration = 0.5  # fallback para outros formatos

            if duration and duration > 2.0:
                warnings.append(f"SFX duration {duration:.2f}s is longer than recommended (<1.5s).")
            has_alpha = False
        except Exception as exc:
            errors.append(f"Failed to inspect audio: {exc}")

    else:
        errors.append(f"Unsupported file extension '{suffix}'.")

    return AssetValidationResult(
        file_path=str(file_path),
        valid=(len(errors) == 0),
        asset_type=asset_type,
        has_alpha=has_alpha,
        dimensions=dimensions,
        duration=duration,
        errors=errors,
        warnings=warnings,
    )


def validate_assets_directory(assets_dir: Path) -> Tuple[bool, List[AssetValidationResult]]:
    """Valida todos os arquivos físicos e a integridade de manifest.json."""
    results: List[AssetValidationResult] = []
    all_valid = True

    manifest_path = assets_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"[ERROR] manifest.json not found at {manifest_path}")
        return False, results

    try:
        content = manifest_path.read_text(encoding="utf-8")
        manifest = AssetManifest.model_validate_json(content)
        print(f"[OK] manifest.json is valid (v{manifest.version}, {len(manifest.assets)} assets)")
    except Exception as exc:
        print(f"[ERROR] manifest.json is invalid or unreadable: {exc}")
        return False, results

    # Valida arquivos registrados no manifest
    for item in manifest.assets:
        full_path = assets_dir / item.file
        if not full_path.exists():
            print(f"[ERROR] Registered asset '{item.id}' missing file: {full_path}")
            all_valid = False
            continue

        res = inspect_media_file(full_path)
        results.append(res)
        if not res.valid:
            all_valid = False
            print(f"[ERROR] {item.file}: {', '.join(res.errors)}")
        else:
            dim_str = f"{res.dimensions[0]}x{res.dimensions[1]}" if res.dimensions else "audio"
            dur_str = f", {res.duration:.2f}s" if res.duration else ""
            alpha_str = "alpha" if res.has_alpha else "no-alpha"
            print(f"[OK] {item.file}: {dim_str} ({alpha_str}{dur_str})")

        if item.default_sfx:
            sfx_path = assets_dir / item.default_sfx
            if not sfx_path.exists():
                print(f"[WARNING] {item.file}: default_sfx '{item.default_sfx}' not found on disk.")

    return all_valid, results


def sync_manifest(assets_dir: Path) -> int:
    """Escaneia o diretório assets/ e adiciona stubs no manifest.json para arquivos não registrados."""
    manifest_path = assets_dir / "manifest.json"
    manifest: AssetManifest

    if manifest_path.exists():
        try:
            content = manifest_path.read_text(encoding="utf-8")
            manifest = AssetManifest.model_validate_json(content)
        except Exception:
            manifest = AssetManifest()
    else:
        manifest = AssetManifest()

    existing_files = {item.file for item in manifest.assets}
    new_count = 0

    for root, _, files in os.walk(assets_dir):
        for f in files:
            p = Path(root) / f
            rel = str(p.relative_to(assets_dir)).replace("\\", "/")

            if rel == "manifest.json" or rel in existing_files:
                continue

            suffix = p.suffix.lower()
            if suffix in (".webm", ".mov"):
                asset_type = AssetType.ANIMATED_VIDEO
            elif suffix in (".png", ".webp"):
                asset_type = AssetType.ICON_WITH_CARD
            elif suffix in (".wav", ".mp3"):
                asset_type = AssetType.SFX
            else:
                continue

            item_id = p.stem.lower().replace("-", "_")
            tag_stub = item_id.replace("_", " ")

            manifest.assets.append(
                AssetItem(
                    id=item_id,
                    file=rel,
                    type=asset_type,
                    tags=[tag_stub],
                    default_position=AssetPosition.UPPER_THIRD,
                    default_sfx=None,
                )
            )
            existing_files.add(rel)
            new_count += 1
            print(f"[ADDED] Discovered and registered: {rel} (type: {asset_type.value})")

    if new_count > 0 or not manifest_path.exists():
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        print(f"\nManifest successfully updated with {new_count} new assets at {manifest_path}")
    else:
        print("\nManifest is already up-to-date. No new assets found.")

    return new_count


def main():
    parser = argparse.ArgumentParser(description="Auxiliary CLI tool for validating and indexing motion assets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate asset files, dimensions, and alpha channels.")
    validate_parser.add_argument(
        "--assets-dir", default=str(Path(PROJECT_ROOT) / "assets"), help="Path to assets directory."
    )

    sync_parser = subparsers.add_parser("sync-manifest", help="Sync assets folder with manifest.json.")
    sync_parser.add_argument(
        "--assets-dir", default=str(Path(PROJECT_ROOT) / "assets"), help="Path to assets directory."
    )

    args = parser.parse_args()
    assets_dir = Path(args.assets_dir)

    if args.command == "validate":
        print(f"=== Validating assets in: {assets_dir} ===")
        all_valid, results = validate_assets_directory(assets_dir)
        total = len(results)
        valid_count = sum(1 for r in results if r.valid)
        print(f"\nValidation Summary: {valid_count}/{total} assets valid.")
        sys.exit(0 if all_valid else 1)

    elif args.command == "sync-manifest":
        print(f"=== Syncing manifest in: {assets_dir} ===")
        sync_manifest(assets_dir)
        sys.exit(0)


if __name__ == "__main__":
    main()
