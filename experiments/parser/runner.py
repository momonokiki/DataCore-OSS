
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import platform
import sys
import time

from pathlib import Path
from typing import Any

import httpx

from experiments.common.io import (
    base_manifest,
    new_experiment_dir,
    sha256_text,
    write_json,
)


DECIMAL_FIELDS = {
    "subtotal_amount",
    "discount_amount",
    "tax_amount",
    "total_amount",
}


def prepare_ollama_schema(
    schema: dict[str, Any],
) -> dict[str, Any]:
    """
    Pydantic JSON SchemaをOllama向けに変換する。

    Decimalフィールドについては、Ollamaに渡すスキーマ上で
    string + pattern ではなく number として定義する。

    元のPydanticスキーマは変更しない。
    実際の値の検証はmodel_validate()に任せる。
    """

    result = copy.deepcopy(schema)

    properties = result.get("properties", {})

    for field_name in DECIMAL_FIELDS:
        field_schema = properties.get(field_name)

        if not isinstance(field_schema, dict):
            continue

        # Decimal | None の場合
        if isinstance(field_schema.get("anyOf"), list):
            for branch in field_schema["anyOf"]:
                if (
                    isinstance(branch, dict)
                    and branch.get("type") == "string"
                ):
                    branch.clear()
                    branch["type"] = "number"

        # Decimal単体の場合
        elif field_schema.get("type") == "string":
            field_schema.pop("pattern", None)
            field_schema.pop("format", None)
            field_schema["type"] = "number"

    return result


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run receipt parser experiments "
            "without writing L3 records."
        )
    )

    source = parser.add_mutually_exclusive_group(
        required=True
    )

    source.add_argument(
        "--artifact-id",
        help="Existing L2 OCR artifact UUID",
    )

    source.add_argument(
        "--ocr-text-file",
        type=Path,
        help="Text or Markdown file containing OCR output",
    )

    parser.add_argument(
        "--stage",
        choices=["header", "items", "both"],
        default="both",
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
    )

    parser.add_argument(
        "--prompt-dir",
        type=Path,
        default=Path(
            "experiments/parser/prompts"
        ),
    )

    parser.add_argument(
        "--header-prompt",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--items-prompt",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/results"),
    )

    parser.add_argument(
        "--label",
        default=None,
    )

    return parser.parse_args()


async def load_artifact_text(
    artifact_id: str,
) -> tuple[str, str]:

    import uuid

    from sqlalchemy import select

    from app.infrastructure.db.session import (
        AsyncSessionLocal,
    )

    from app.layers.l2_extracted.models import (
        L2Artifact,
    )

    async with AsyncSessionLocal() as session:

        row = (
            await session.execute(
                select(L2Artifact).where(
                    L2Artifact.id
                    == uuid.UUID(artifact_id)
                )
            )
        ).scalar_one_or_none()

        if row is None:
            raise ValueError(
                f"L2 artifact not found: {artifact_id}"
            )

        if row.artifact_type != "ocr_text":
            raise ValueError(
                "Artifact type must be 'ocr_text', "
                f"got {row.artifact_type!r}"
            )

        if (
            not row.content_text
            or not row.content_text.strip()
        ):
            raise ValueError(
                "OCR artifact content_text is empty"
            )

        return (
            row.content_text,
            str(row.id),
        )


async def ollama_json(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    system_prompt: str,
    user_text: str,
    schema: dict[str, Any],
    temperature: float,
) -> tuple[dict[str, Any], dict[str, Any]]:

    response = await client.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "stream": False,
            "format": schema,
            "options": {
                "temperature": temperature,
            },
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_text,
                },
            ],
        },
    )

    if response.is_error:
        raise RuntimeError(
            f"Ollama API error: "
            f"HTTP {response.status_code}\n"
            f"{response.text}"
        )

    response.raise_for_status()

    body = response.json()

    content = (
        body.get("message", {})
        .get("content")
    )

    if not isinstance(content, str):
        raise ValueError(
            f"Unexpected Ollama response: {body}"
        )

    try:
        parsed = json.loads(content)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "Ollama returned invalid JSON: "
            f"{content[:1000]}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            "Ollama response must be a JSON object"
        )

    stats = {
        "total_duration": body.get(
            "total_duration"
        ),
        "load_duration": body.get(
            "load_duration"
        ),
        "prompt_eval_count": body.get(
            "prompt_eval_count"
        ),
        "prompt_eval_duration": body.get(
            "prompt_eval_duration"
        ),
        "eval_count": body.get(
            "eval_count"
        ),
        "eval_duration": body.get(
            "eval_duration"
        ),
    }

    return parsed, stats


def load_prompt(
    path: Path,
) -> str:

    if not path.is_file():
        raise FileNotFoundError(
            f"Prompt file not found: {path}"
        )

    prompt = path.read_text(
        encoding="utf-8"
    )

    if not prompt.strip():
        raise ValueError(
            f"Prompt file is empty: {path}"
        )

    return prompt


async def main():

    args = parse_args()

    started = time.perf_counter()

    out_dir = new_experiment_dir(
        args.output_dir
    )

    manifest = base_manifest(
        "receipt_parser"
    )

    manifest.update({
        "label": args.label,
        "model": args.model,
        "ollama_base_url": args.base_url,
        "stage": args.stage,
        "temperature": args.temperature,
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
        },
    })

    try:

        # --------------------------------------------------
        # 1. OCRテキスト取得
        # --------------------------------------------------

        if args.artifact_id:

            ocr_text, artifact_id = (
                await load_artifact_text(
                    args.artifact_id
                )
            )

            source = {
                "type": "l2_artifact",
                "artifact_id": artifact_id,
            }

        else:

            text_path = (
                args.ocr_text_file
                .expanduser()
                .resolve()
            )

            if not text_path.is_file():
                raise FileNotFoundError(
                    text_path
                )

            ocr_text = text_path.read_text(
                encoding="utf-8"
            )

            source = {
                "type": "text_file",
                "file_name": text_path.name,
            }

        if not ocr_text.strip():
            raise ValueError(
                "OCR text is empty"
            )

        # --------------------------------------------------
        # 2. 実行する段階に応じてプロンプトを読み込む
        # --------------------------------------------------

        header_prompt_path = (
            args.header_prompt
            or (
                args.prompt_dir
                / "header_system.txt"
            )
        )

        items_prompt_path = (
            args.items_prompt
            or (
                args.prompt_dir
                / "items_system_simple.txt"
            )
        )

        header_prompt = None
        items_prompt = None

        prompt_info: dict[str, Any] = {}

        if args.stage in ("header", "both"):

            header_prompt = load_prompt(
                header_prompt_path
            )

            prompt_info["header"] = {
                "path": str(
                    header_prompt_path
                ),
                "sha256": sha256_text(
                    header_prompt
                ),
                "text": header_prompt,
            }

        if args.stage in ("items", "both"):

            items_prompt = load_prompt(
                items_prompt_path
            )

            prompt_info["items"] = {
                "path": str(
                    items_prompt_path
                ),
                "sha256": sha256_text(
                    items_prompt
                ),
                "text": items_prompt,
            }

        # --------------------------------------------------
        # 3. スキーマ読み込み
        # --------------------------------------------------

        if args.stage in ("header", "both"):

            from app.layers.l3_structured.addons.receipt.schemas import (
                ReceiptHeaderData,
            )

            original_header_schema = (
                ReceiptHeaderData.model_json_schema()
            )

            header_schema = prepare_ollama_schema(
                original_header_schema
            )

        else:
            ReceiptHeaderData = None
            header_schema = None

        if args.stage in ("items", "both"):

            from experiments.parser.schemas import (
                ReceiptExperimentItemsData,
            )

            items_schema = (
                ReceiptExperimentItemsData
                .model_json_schema()
            )

        else:
            ReceiptExperimentItemsData = None
            items_schema = None

        # --------------------------------------------------
        # 4. 入力データ保存
        # --------------------------------------------------

        write_json(
            out_dir / "input.json",
            {
                "source": source,
                "ocr_text": ocr_text,
                "ocr_text_sha256": sha256_text(
                    ocr_text
                ),
            },
        )

        (
            out_dir / "input.txt"
        ).write_text(
            ocr_text,
            encoding="utf-8",
        )

        write_json(
            out_dir / "prompts.json",
            prompt_info,
        )

        # --------------------------------------------------
        # 5. 実験実行
        # --------------------------------------------------

        raw_results: dict[str, Any] = {}

        validation: dict[str, Any] = {}

        timings: dict[str, float] = {}

        stats: dict[str, Any] = {}

        async with httpx.AsyncClient(
            timeout=args.timeout
        ) as client:

            # ----------------------------------------------
            # Header
            # ----------------------------------------------

            if args.stage in ("header", "both"):

                t0 = time.perf_counter()

                raw, stats_header = await ollama_json(
                    client=client,
                    base_url=args.base_url,
                    model=args.model,
                    system_prompt=header_prompt,
                    user_text=ocr_text,
                    schema=header_schema,
                    temperature=args.temperature,
                )

                timings["header_seconds"] = round(
                    time.perf_counter() - t0,
                    3,
                )

                raw_results["header"] = raw

                stats["header"] = stats_header

                try:

                    validated = (
                        ReceiptHeaderData
                        .model_validate(raw)
                    )

                    validation["header"] = {
                        "valid": True,
                        "data": validated.model_dump(
                            mode="json"
                        ),
                    }

                except Exception as exc:

                    validation["header"] = {
                        "valid": False,
                        "error": str(exc),
                    }

            # ----------------------------------------------
            # Items
            # ----------------------------------------------

            if args.stage in ("items", "both"):

                t0 = time.perf_counter()

                raw, stats_items = await ollama_json(
                    client=client,
                    base_url=args.base_url,
                    model=args.model,
                    system_prompt=items_prompt,
                    user_text=ocr_text,
                    schema=items_schema,
                    temperature=args.temperature,
                )

                timings["items_seconds"] = round(
                    time.perf_counter() - t0,
                    3,
                )

                raw_results["items"] = raw

                stats["items"] = stats_items

                try:

                    validated = (
                        ReceiptExperimentItemsData
                        .model_validate(raw)
                    )

                    validation["items"] = {
                        "valid": True,
                        "data": validated.model_dump(
                            mode="json"
                        ),
                    }

                except Exception as exc:

                    validation["items"] = {
                        "valid": False,
                        "error": str(exc),
                    }

        # --------------------------------------------------
        # 6. 結果保存
        # --------------------------------------------------

        result = {
            "raw": raw_results,
            "validation": validation,
            "ollama_stats": stats,
            "timings": timings,
        }

        write_json(
            out_dir / "parser_output.json",
            result,
        )

        valid_count = sum(
            1
            for value in validation.values()
            if value.get("valid")
        )

        prompt_hashes = {
            stage: info["sha256"]
            for stage, info in prompt_info.items()
        }

        manifest.update({
            "status": "success",
            "source": source,
            "ocr_text_sha256": sha256_text(
                ocr_text
            ),
            "prompt_hashes": prompt_hashes,
            "validation": {
                "valid_stages": valid_count,
                "total_stages": len(validation),
                "details": {
                    key: value.get("valid")
                    for key, value in validation.items()
                },
            },
            "timings": timings,
            "elapsed_seconds": round(
                time.perf_counter() - started,
                3,
            ),
        })

        write_json(
            out_dir / "manifest.json",
            manifest,
        )

        print(
            f"Parser experiment saved: {out_dir}"
        )

        print(
            "Schema validation: "
            f"{valid_count}/{len(validation)} stages passed"
        )

        for stage, result in validation.items():

            if not result.get("valid"):

                print(
                    f"{stage}: INVALID - "
                    f"{result.get('error')}"
                )

    except Exception as exc:

        manifest.update({
            "status": "failed",
            "elapsed_seconds": round(
                time.perf_counter() - started,
                3,
            ),
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        })

        write_json(
            out_dir / "manifest.json",
            manifest,
        )

        write_json(
            out_dir / "error.json",
            manifest["error"],
        )

        raise


if __name__ == "__main__":

    asyncio.run(main())

