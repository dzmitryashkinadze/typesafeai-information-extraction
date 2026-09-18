import json

import pytest

from typesafeai_information_extraction_demo.cli import main


def test_cli_creates_fact_bundle_and_diagnostics(tmp_path, monkeypatch):
    note = tmp_path / "note.txt"
    note.write_text("Patient denies cough. Return in two weeks.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    main(["extract", "--input", str(note), "--patient-id", "patient-abc", "--output-dir", "result"])
    output = tmp_path / "result"
    facts = json.loads((output / "facts.json").read_text())
    bundle = json.loads((output / "bundle.json").read_text())
    diagnostics = json.loads((output / "diagnostics.json").read_text())
    assert facts["note"]["patient_id"] == "patient-abc"
    assert bundle["resourceType"] == "Bundle"
    assert diagnostics["validation"]["fhir_release"] == "4.3.0"
    assert diagnostics["validation"]["model_validation"]


def test_cli_missing_input_has_readable_error(tmp_path):
    with pytest.raises(SystemExit, match="Error:"):
        main(["extract", "--input", str(tmp_path / "missing.txt")])
