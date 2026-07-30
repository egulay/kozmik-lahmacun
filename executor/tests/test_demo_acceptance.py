import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_generator():
    path = ROOT / "demo" / "generate_data.py"
    spec = importlib.util.spec_from_file_location("demo_generate_data", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_demo_generators_are_deterministic_and_contract_shaped(tmp_path):
    generator = load_generator()
    first = tmp_path / "first"
    second = tmp_path / "second"
    generator.write_cdr(first / "cdr.csv", rows=25)
    generator.write_sales(first / "sales.csv", rows=25)
    generator.write_cdr(second / "cdr.csv", rows=25)
    generator.write_sales(second / "sales.csv", rows=25)
    assert (first / "cdr.csv").read_bytes() == (second / "cdr.csv").read_bytes()
    assert (first / "sales.csv").read_bytes() == (second / "sales.csv").read_bytes()
    assert generator.count_data_rows(first / "cdr.csv") == 25
    assert generator.count_data_rows(first / "sales.csv") == 25
    assert tuple((first / "cdr.csv").read_text().splitlines()[0].split(",")) == (
        generator.CDR_COLUMNS
    )


def test_demo_scenarios_are_versioned_and_role_separated():
    scenarios = ROOT / "demo" / "scenarios"
    reporter = json.loads((scenarios / "reporter.json").read_text())
    scientist = json.loads((scenarios / "scientist.json").read_text())
    admin = json.loads((scenarios / "admin.json").read_text())
    assert {item["schemaVersion"] for item in (reporter, scientist, admin)} == {"1.0"}
    assert reporter["role"] == "REPORTER"
    assert scientist["role"] == "SCIENTIST"
    assert admin["role"] == "ADMIN"
    assert all(item["algorithm"] == "LINEAR_REGRESSION"
               for item in scientist["scenarios"])
