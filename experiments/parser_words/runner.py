

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import platform
import re
import sys
import time

from pathlib import Path
from typing import Any

import httpx

from sqlalchemy import select

from experiments.common.io import (
    base_manifest,
    new_experiment_dir,
    sha256_text,
    write_json,
)

from experiments.parser_words.layout import (
    build_layout,
    build_layout_preview,
)

from experiments.parser_words.structure import (
    build_structure,
    build_structure_preview,
)

from experiments.parser_words.schemas import (
    ReceiptHeaderData,
    ReceiptExperimentItemsData,
)

from app.infrastructure.db.session import AsyncSessionLocal
from app.layers.l2_extracted.models import L2Artifact


DECIMAL_FIELDS = {
    "subtotal_amount",
    "discount_amount",
    "tax_amount",
    "total_amount",
}


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Coordinate-aware receipt parser experiment"
    )

    parser.add_argument(
        "--file-hash",
        required=True,
        help="L1 file SHA-256 hash",
    )

    parser.add_argument(
        "--stage",
        choices=["header", "items", "both"],
        default="both",
        help="LLM execution stage",
    )

    parser.add_argument(
        "--structure-only",
        action="store_true",
        help="Run rule-based structure extraction without LLM",
    )

    parser.add_argument(
        "--model",
        required=True,
        help="Ollama model name",
    )

    parser.add_argument(
        "--base-url",
        default=os.getenv(
            "OLLAMA_BASE_URL",
            "http://localhost:11434",
        ),
        help="Ollama API base URL",
    )

    parser.add_argument(
        "--prompt-dir",
        type=Path,
        default=Path("experiments/parser_words/prompts"),
        help="Prompt directory",
    )

    parser.add_argument(
        "--header-prompt",
        default="header.txt",
        help="Header prompt filename",
    )

    parser.add_argument(
        "--items-prompt",
        default="items.txt",
        help="Items prompt filename",
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Ollama temperature",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Ollama request timeout in seconds",
    )

    parser.add_argument(
        "--line-tolerance-ratio",
        type=float,
        default=0.45,
        help="Row grouping tolerance relative to median word height",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/parser_words/results"),
        help="Experiment output directory",
    )

    parser.add_argument(
        "--label",
        default=None,
        help="Optional experiment label",
    )

    return parser.parse_args()


# ============================================================
# L2 OCR artifact
# ============================================================

async def load_artifact_words(
    file_hash: str,
) -> tuple[list[dict[str, Any]], str]:
    """
    file_hashからL2 OCR成果物を取得する。

    対象:
        L2Artifact.file_hash
        L2Artifact.artifact_type == "ocr_text"
        L2Artifact.bounding_box["words"]

    Returns:
        words:
            YomiToku OCR words

        artifact_id:
            取得したL2ArtifactのUUID文字列
    """

    file_hash = file_hash.lower()

    if not re.fullmatch(r"[0-9a-f]{64}", file_hash):
        raise ValueError(
            "file_hash must be a 64-character SHA-256 hash"
        )

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(L2Artifact).where(
                L2Artifact.file_hash == file_hash,
                L2Artifact.artifact_type == "ocr_text",
            )
        )

        artifacts = result.scalars().all()

        if not artifacts:
            raise ValueError(
                "OCR artifact not found for file_hash: "
                f"{file_hash}"
            )

        if len(artifacts) > 1:
            artifact_ids = [
                str(artifact.id)
                for artifact in artifacts
            ]

            raise ValueError(
                "Multiple OCR artifacts found for file_hash. "
                "Cannot select an artifact automatically. "
                f"artifact_ids={artifact_ids}"
            )

        artifact = artifacts[0]

        artifact_id = str(artifact.id)
        bounding_box = artifact.bounding_box

        if not isinstance(bounding_box, dict):
            raise ValueError(
                "Invalid bounding_box in OCR artifact: "
                f"{artifact_id}"
            )

        words = bounding_box.get("words")

        if not isinstance(words, list) or not words:
            raise ValueError(
                "bounding_box['words'] is missing or empty. "
                f"artifact_id={artifact_id}"
            )

        return words, artifact_id


# ============================================================
# Ollama schema preparation
# ============================================================

def prepare_ollama_schema(
    schema: dict[str, Any],
) -> dict[str, Any]:
    """
    Pydantic JSON SchemaをOllama向けに変換する。

    Decimalフィールド:
        number | null

    Pydantic側の元Schemaは変更しない。
    """

    result = copy.deepcopy(schema)

    def convert_node(
        node: Any,
        field_name: str | None = None,
    ) -> Any:

        if isinstance(node, list):
            return [
                convert_node(item, field_name)
                for item in node
            ]

        if not isinstance(node, dict):
            return node

        if field_name in DECIMAL_FIELDS:

            nullable = False

            if "anyOf" in node:
                nullable = any(
                    isinstance(branch, dict)
                    and branch.get("type") == "null"
                    for branch in node["anyOf"]
                )

            if nullable:
                return {
                    "anyOf": [
                        {"type": "number"},
                        {"type": "null"},
                    ]
                }

            return {
                "type": "number",
            }

        output = {}

        for key, value in node.items():

            if key == "properties" and isinstance(value, dict):
                output[key] = {
                    name: convert_node(child, name)
                    for name, child in value.items()
                }

            else:
                output[key] = convert_node(value)

        return output

    return convert_node(result)


# ============================================================
# Prompt
# ============================================================

def load_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {path}"
        )

    content = path.read_text(
        encoding="utf-8"
    ).strip()

    if not content:
        raise ValueError(
            f"Prompt file is empty: {path}"
        )

    return content


# ============================================================
# Ollama
# ============================================================

async def ollama_json(
    *,
    base_url: str,
    model: str,
    system_prompt: str,
    user_content: str,
    schema: dict[str, Any],
    temperature: float,
    timeout: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Ollama Chat APIをJSON Schema指定で実行する。
    """

    request_payload = {
        "model": model,
        "stream": False,
        "format": schema,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        "options": {
            "temperature": temperature,
        },
    }

    started = time.perf_counter()

    async with httpx.AsyncClient(
        timeout=timeout,
    ) as client:

        response = await client.post(
            f"{base_url.rstrip('/')}/api/chat",
            json=request_payload,
        )

        if response.is_error:
            raise RuntimeError(
                "Ollama API error\n"
                f"URL: {response.request.url}\n"
                f"Status: {response.status_code}\n"
                f"Response: {response.text}\n"
            )

        response.raise_for_status()

    elapsed = time.perf_counter() - started

    response_data = response.json()

    message = response_data.get("message", {})
    content = message.get("content", "")

    if not content:
        raise ValueError(
            "Ollama returned empty message content"
        )

    try:
        parsed = json.loads(content)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "Ollama returned invalid JSON\n"
            f"Content: {content}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            "Ollama output must be a JSON object"
        )

    stats = {
        "elapsed_seconds": elapsed,
        "total_duration": response_data.get(
            "total_duration"
        ),
        "load_duration": response_data.get(
            "load_duration"
        ),
        "prompt_eval_count": response_data.get(
            "prompt_eval_count"
        ),
        "prompt_eval_duration": response_data.get(
            "prompt_eval_duration"
        ),
        "eval_count": response_data.get(
            "eval_count"
        ),
        "eval_duration": response_data.get(
            "eval_duration"
        ),
    }

    return parsed, stats


# ============================================================
# Validation
# ============================================================

def validate_output(
    model_class: Any,
    raw: dict[str, Any],
) -> dict[str, Any]:
    """
    Pydanticによる出力検証。
    """

    try:
        validated = model_class.model_validate(raw)

        return {
            "success": True,
            "data": validated.model_dump(mode="json"),
            "errors": None,
        }

    except Exception as exc:

        return {
            "success": False,
            "data": None,
            "errors": str(exc),
        }


# ============================================================
# Parser stage
# ============================================================

async def run_stage(
    *,
    stage_name: str,
    model_class: Any,
    schema: dict[str, Any],
    prompt: str,
    user_content: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """
    ヘッダーまたは商品抽出の1ステージを実行する。
    """

    started = time.perf_counter()

    raw, stats = await ollama_json(
        base_url=args.base_url,
        model=args.model,
        system_prompt=prompt,
        user_content=user_content,
        schema=schema,
        temperature=args.temperature,
        timeout=args.timeout,
    )

    validation = validate_output(
        model_class,
        raw,
    )

    return {
        "stage": stage_name,
        "raw": raw,
        "validation": validation,
        "ollama": stats,
        "elapsed_seconds": time.perf_counter() - started,
    }


# ============================================================
# Manifest helpers
# ============================================================

def build_source_manifest(
    *,
    file_hash: str,
    artifact_id: str,
    words: list[dict[str, Any]],
    input_hash: str,
) -> dict[str, Any]:

    return {
        "file_hash": file_hash.lower(),
        "artifact_id": artifact_id,
        "word_count": len(words),
        "input_sha256": input_hash,
    }


def build_layout_manifest(
    layout: dict[str, Any],
    layout_hash: str,
    line_tolerance_ratio: float,
) -> dict[str, Any]:

    return {
        "method": layout["layout_method"],
        "line_count": layout["line_count"],
        "layout_sha256": layout_hash,
        "line_tolerance_ratio": line_tolerance_ratio,
        "median_word_height": layout["median_word_height"],
        "line_tolerance_pixels": layout["line_tolerance_pixels"],
    }


def build_structure_manifest(
    structure: dict[str, Any],
) -> dict[str, Any]:

    return {
        "method": structure["structure_method"],
        "row_count": structure["row_count"],
        "region_counts": structure["region_counts"],
        "row_type_counts": structure["row_type_counts"],
    }


# ============================================================
# Main
# ============================================================

async def main() -> None:

    args = parse_args()

    started = time.perf_counter()

    experiment_dir = new_experiment_dir(
        args.output_dir
    )

    manifest = base_manifest(
        "receipt_parser_words"
    )

    manifest.update(
        {
            "label": args.label,
            "model": None if args.structure_only else args.model,
            "base_url": None if args.structure_only else args.base_url,
            "stage": (
                "structure_only"
                if args.structure_only
                else args.stage
            ),
            "temperature": (
                None if args.structure_only else args.temperature
            ),
            "timeout": (
                None if args.structure_only else args.timeout
            ),
            "line_tolerance_ratio": args.line_tolerance_ratio,
            "runtime": {
                "python": sys.version,
                "platform": platform.platform(),
            },
        }
    )

    write_json(
        experiment_dir / "manifest.json",
        manifest,
    )

    try:

        # ----------------------------------------------------
        # 1. Load L2 OCR artifact
        # ----------------------------------------------------

        print("[1/6] Loading L2 OCR artifact...")

        words, artifact_id = await load_artifact_words(
            args.file_hash
        )

        # YomiTokuのOCR座標をそのまま使用する。
        # MediaInfoのwidth/heightはEXIF適用前の画素寸法の場合があるため、
        # 画像寸法による座標回転・正規化は行わない。
        layout_words = copy.deepcopy(words)
        orientation_info = {
            "rotation_degrees": 0,
            "rotation_direction": "none",
            "reason": "original_ocr_coordinates",
            "coordinate_transform_applied": False,
        }

        input_payload = {
            "file_hash": args.file_hash.lower(),
            "artifact_id": artifact_id,
            "words": words,
        }

        input_text = json.dumps(
            input_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        input_hash = sha256_text(input_text)

        write_json(
            experiment_dir / "input.json",
            input_payload,
        )

        print(f"  artifact_id: {artifact_id}")
        print(f"  word_count : {len(words)}")
        print(
            "  orientation: "
            f"{orientation_info['rotation_direction']} "
            f"({orientation_info['rotation_degrees']} deg; "
            "original OCR coordinates)"
        )

        write_json(
            experiment_dir / "layout_input_words.json",
            {"image": orientation_info, "words": layout_words},
        )

        # ----------------------------------------------------
        # 2. Coordinate layout
        # ----------------------------------------------------

        print("[2/6] Building coordinate layout...")

        layout = build_layout(
            layout_words,
            line_tolerance_ratio=args.line_tolerance_ratio,
        )

        write_json(
            experiment_dir / "layout.json",
            layout,
        )

        preview = build_layout_preview(layout)

        (
            experiment_dir / "layout_preview.txt"
        ).write_text(
            preview,
            encoding="utf-8",
        )

        print(f"  line_count : {layout['line_count']}")

        # ----------------------------------------------------
        # 3. Prepare layout input
        # ----------------------------------------------------

        print("[3/6] Preparing layout data...")

        user_content = json.dumps(
            layout,
            ensure_ascii=False,
            indent=2,
        )

        layout_hash = sha256_text(user_content)

        # ----------------------------------------------------
        # 3.5 Rule-based structure extraction
        # ----------------------------------------------------

        print("[3.5/6] Building receipt structure...")

        structure = build_structure(layout)

        write_json(
            experiment_dir / "structure.json",
            structure,
        )

        structure_preview = build_structure_preview(
            structure
        )

        (
            experiment_dir / "structure_preview.txt"
        ).write_text(
            structure_preview,
            encoding="utf-8",
        )

        print(
            f"  structure rows : {structure['row_count']}"
        )

        print(
            f"  regions        : {structure['region_counts']}"
        )

        # ----------------------------------------------------
        # Structure-only mode
        # ----------------------------------------------------

        if args.structure_only:

            manifest.update(
                {
                    "status": "completed",
                    "source": build_source_manifest(
                        file_hash=args.file_hash,
                        artifact_id=artifact_id,
                        words=words,
                        input_hash=input_hash,
                    ),
                    "image_orientation": orientation_info,
                    "layout": build_layout_manifest(
                        layout,
                        layout_hash,
                        args.line_tolerance_ratio,
                    ),
                    "structure": build_structure_manifest(
                        structure
                    ),
                    "execution": {
                        "llm_executed": False,
                    },
                    "elapsed_seconds": (
                        time.perf_counter() - started
                    ),
                }
            )

            write_json(
                experiment_dir / "manifest.json",
                manifest,
            )

            print()
            print("========================================")
            print("Structure experiment completed")
            print("========================================")
            print(f"Output      : {experiment_dir}")
            print(f"File hash   : {args.file_hash}")
            print(f"Artifact ID : {artifact_id}")
            print(f"Words       : {len(words)}")
            print(f"Lines       : {layout['line_count']}")
            print(f"Rows        : {structure['row_count']}")
            print(f"Regions     : {structure['region_counts']}")
            print("LLM         : Not executed")
            print(
                f"Elapsed     : "
                f"{manifest['elapsed_seconds']:.2f}s"
            )
            print("========================================")

            return

        # ----------------------------------------------------
        # 4. Load prompts
        # ----------------------------------------------------

        print("[4/6] Loading prompts...")

        header_prompt = load_prompt(
            args.prompt_dir / args.header_prompt
        )

        items_prompt = load_prompt(
            args.prompt_dir / args.items_prompt
        )

        write_json(
            experiment_dir / "prompts.json",
            {
                "header": header_prompt,
                "items": items_prompt,
            },
        )

        prompt_hashes = {
            "header": sha256_text(header_prompt),
            "items": sha256_text(items_prompt),
        }

        # ----------------------------------------------------
        # 5. Prepare schemas and execute
        # ----------------------------------------------------

        print("[5/6] Running parser...")

        header_schema = prepare_ollama_schema(
            ReceiptHeaderData.model_json_schema()
        )

        items_schema = prepare_ollama_schema(
            ReceiptExperimentItemsData.model_json_schema()
        )

        outputs: dict[str, Any] = {}

        if args.stage in ("header", "both"):

            print("  Running header parser...")

            outputs["header"] = await run_stage(
                stage_name="header",
                model_class=ReceiptHeaderData,
                schema=header_schema,
                prompt=header_prompt,
                user_content=user_content,
                args=args,
            )

        if args.stage in ("items", "both"):

            print("  Running items parser...")

            outputs["items"] = await run_stage(
                stage_name="items",
                model_class=ReceiptExperimentItemsData,
                schema=items_schema,
                prompt=items_prompt,
                user_content=user_content,
                args=args,
            )
        # ----------------------------------------------------
        # 6. Save results
        # ----------------------------------------------------

        print("[6/6] Saving results...")

        write_json(
            experiment_dir / "parser_output.json",
            outputs,
        )
        validation_summary = {
            name: result["validation"]["success"]
            for name, result in outputs.items()
        }

        manifest.update(
            {
                "status": "completed",

                "source": build_source_manifest(
                    file_hash=args.file_hash,
                    artifact_id=artifact_id,
                    words=words,
                    input_hash=input_hash,
                ),

                "image_orientation": orientation_info,

                "layout": build_layout_manifest(
                    layout,
                    layout_hash,
                    args.line_tolerance_ratio,
                ),

                "structure": build_structure_manifest(
                    structure
                ),

                "prompt_sha256": prompt_hashes,

                "validation": validation_summary,


                "execution": {
                    "llm_executed": True,
                    "stage": args.stage,
                    "model": args.model,
                },

                "elapsed_seconds": (
                    time.perf_counter() - started
                ),
            }
        )

        write_json(
            experiment_dir / "manifest.json",
            manifest,
        )

        print()
        print("========================================")
        print("Experiment completed")
        print("========================================")
        print(f"Output      : {experiment_dir}")
        print(f"File hash   : {args.file_hash}")
        print(f"Artifact ID : {artifact_id}")
        print(f"Words       : {len(words)}")
        print(f"Lines       : {layout['line_count']}")
        print(f"Rows        : {structure['row_count']}")
        print(f"Validation  : {validation_summary}")
        print(
            f"Elapsed     : "
            f"{manifest['elapsed_seconds']:.2f}s"
        )
        print("========================================")

    except Exception as exc:

        manifest.update(
            {
                "status": "failed",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "elapsed_seconds": (
                    time.perf_counter() - started
                ),
            }
        )

        write_json(
            experiment_dir / "manifest.json",
            manifest,
        )

        write_json(
            experiment_dir / "error.json",
            {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        )

        raise


if __name__ == "__main__":
    asyncio.run(main())




