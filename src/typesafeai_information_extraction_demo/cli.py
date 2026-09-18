"""Offline extraction and repeatable evaluation after `uv sync --locked`."""

import argparse
import json
from pathlib import Path
from typing import Any, cast

from .evaluation import evaluate, load_corpus, report_markdown
from .fhir_mapping import map_fhir
from .models import Note
from .pipeline import ClassicPipeline, Layer


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Track A: MedSpaCy clinical extraction and FHIR R4B")
    commands = root.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="Extract a UTF-8 text note")
    extract.add_argument("--input", required=True, type=Path)
    extract.add_argument("--patient-id", default="demo-001")
    extract.add_argument("--note-id", default="note-001")
    extract.add_argument(
        "--reference-date", help="Optional ISO YYYY-MM-DD; relative intervals remain explicit"
    )
    extract.add_argument("--output-dir", type=Path, default=Path("output"))
    evaluation = commands.add_parser("evaluate", help="Evaluate the packaged annotated corpus")
    evaluation.add_argument(
        "--split",
        choices=["development", "validation", "evaluation", "challenge"],
        default="development",
    )
    evaluation.add_argument(
        "--layer", choices=["targets", "context", "full", "all"], default="full"
    )
    evaluation.add_argument("--output-dir", type=Path, default=Path("reports"))
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    try:
        if args.command == "extract":
            note = Note(
                args.input.read_text(encoding="utf-8"),
                args.note_id,
                args.patient_id,
                args.reference_date,
            )
            extraction = ClassicPipeline().extract(note)
            mapping = map_fhir(extraction)
            if not mapping.validation["model_validation"]:
                raise ValueError(f"Bundle validation failed: {mapping.validation['errors']}")
            args.output_dir.mkdir(parents=True, exist_ok=True)
            write_json(args.output_dir / "facts.json", extraction.to_dict())
            write_json(args.output_dir / "bundle.json", mapping.bundle)
            write_json(
                args.output_dir / "diagnostics.json",
                {
                    "metadata": extraction.metadata,
                    "diagnostics": extraction.diagnostics,
                    "mapping_dispositions": mapping.dispositions,
                    "validation": mapping.validation,
                },
            )
            mapped = sum(d["status"] == "mapped" for d in mapping.dispositions)
            print(
                f"Extracted {len(extraction.facts)} facts; mapped {mapped}; "
                f"retained {len(extraction.facts) - mapped} unmapped. Output: {args.output_dir}"
            )
        else:
            corpus = load_corpus()
            cases = [c for c in corpus["cases"] if c["split"] == args.split]
            layers = ["targets", "context", "full"] if args.layer == "all" else [args.layer]
            report = {
                "split": args.split,
                "corpus_version": corpus["version"],
                "corpus_sha256": corpus["sha256"],
                "evaluation_policy": corpus["evaluation_policy"],
                "layers": {
                    layer: evaluate(ClassicPipeline(cast(Layer, layer)), cases) for layer in layers
                },
            }
            args.output_dir.mkdir(parents=True, exist_ok=True)
            write_json(args.output_dir / "report.json", report)
            (args.output_dir / "report.md").write_text(report_markdown(report), encoding="utf-8")
            for layer, result in report["layers"].items():
                print(
                    f"{layer}: {result['cases']} cases; span F1={result['strict_spans']['f1']}; "
                    f"complete facts={result['complete_facts']['accuracy_over_gold']}. "
                    f"Report: {args.output_dir}"
                )
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"Error: {exc}") from exc


if __name__ == "__main__":
    main()
