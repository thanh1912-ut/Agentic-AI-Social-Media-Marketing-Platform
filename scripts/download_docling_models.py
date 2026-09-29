"""Download only the pinned local Docling layout and table models.

OCR, picture classification/description, VLM, and remote services are excluded.
The resulting manifest records package version and SHA-256 for every artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".data/docling-models"))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    manifest_path = output / "docling-models.sha256.json"

    if not args.verify_only:
        from docling.utils.model_downloader import download_models

        download_models(
            output_dir=output,
            progress=True,
            with_layout=True,
            with_tableformer=True,
            with_tableformer_v2=False,
            with_code_formula=False,
            with_picture_classifier=False,
            with_smolvlm=False,
            with_granitedocling=False,
            with_granitedocling_mlx=False,
            with_granitedocling_2stage=False,
            with_smoldocling=False,
            with_smoldocling_mlx=False,
            with_granite_vision=False,
            with_granite_chart_extraction=False,
            with_granite_chart_extraction_v4=False,
            with_rapidocr=False,
            with_easyocr=False,
            with_nemotron_ocr=False,
        )
        files = sorted(path for path in output.rglob("*") if path.is_file() and path != manifest_path)
        manifest = {
            "docling_version": version("docling-slim"),
            "model_families": ["layout", "tableformer"],
            "ocr": False,
            "pictures": False,
            "files": {str(path.relative_to(output)): _hash(path) for path in files},
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("Docling model manifest is missing or invalid") from exc
    if manifest.get("docling_version") != version("docling-slim"):
        raise SystemExit("Docling model manifest version does not match the installed package")
    for relative, expected in manifest.get("files", {}).items():
        path = output / relative
        if not path.is_file() or _hash(path) != expected:
            raise SystemExit(f"Docling model checksum failed: {relative}")
    print(f"Verified {len(manifest.get('files', {}))} Docling model files; OCR disabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
