import importlib.util
import csv
import json
import subprocess
import sys
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
    generator.write_payments(first / "payments.csv", rows=250)
    generator.write_employees(first / "employees.csv", rows=250)
    generator.write_cdr(second / "cdr.csv", rows=25)
    generator.write_sales(second / "sales.csv", rows=25)
    generator.write_payments(second / "payments.csv", rows=250)
    generator.write_employees(second / "employees.csv", rows=250)
    assert (first / "cdr.csv").read_bytes() == (second / "cdr.csv").read_bytes()
    assert (first / "sales.csv").read_bytes() == (second / "sales.csv").read_bytes()
    assert (first / "payments.csv").read_bytes() == (second / "payments.csv").read_bytes()
    assert (first / "employees.csv").read_bytes() == (second / "employees.csv").read_bytes()
    assert generator.count_data_rows(first / "cdr.csv") == 25
    assert generator.count_data_rows(first / "sales.csv") == 25
    assert generator.count_data_rows(first / "payments.csv") == 250
    assert generator.count_data_rows(first / "employees.csv") == 250
    assert tuple((first / "cdr.csv").read_text().splitlines()[0].split(",")) == (
        generator.CDR_COLUMNS
    )
    assert tuple((first / "payments.csv").read_text().splitlines()[0].split(",")) == (
        generator.PAYMENT_COLUMNS
    )
    with (first / "employees.csv").open(encoding="utf-8") as stream:
        assert tuple(next(csv.reader(stream))) == generator.EMPLOYEE_COLUMNS


def test_employee_demo_preserves_csv_safe_complex_values(tmp_path):
    generator = load_generator()
    target = tmp_path / "employees.csv"
    generator.write_employees(target, rows=500)

    with target.open(encoding="utf-8") as stream:
        records = list(csv.DictReader(stream))

    assert len(records) == 500
    assert {record["department_code"] for record in records} == {
        "1", "2", "3", "4", "5", "6"
    }
    assert {record["country_code_char"] for record in records} == {
        "TR", "DE", "GB", "NL", "US"
    }
    assert "" in {record["middle_name"] for record in records}
    assert "" in {record["profile_photo"] for record in records}
    assert all(len(record["country_code_char"]) == 2 for record in records)
    assert all(json.loads(record["skills"]) for record in records)
    assert all("cost_center" in json.loads(record["metadata"]) for record in records)
    assert all("postal_code" in json.loads(record["address"]) for record in records)
    assert all(record["employment_tenure"].startswith("P") for record in records)
    assert all(record["avg_daily_commute"].startswith("PT") for record in records)


def test_payment_demo_contains_meaningful_supervised_fraud_signals(tmp_path):
    generator = load_generator()
    target = tmp_path / "payments.csv"
    generator.write_payments(target, rows=10_000)

    with target.open(encoding="utf-8") as stream:
        records = list(csv.DictReader(stream))
    fraud = [record for record in records if record["is_fraud"] == "true"]
    legitimate = [record for record in records if record["is_fraud"] == "false"]

    assert 100 <= len(fraud) <= 500
    assert {record["channel"] for record in records} == {"pos", "online", "atm", "mobile"}
    assert "" in {record["device_id"] for record in records}
    assert len({record["currency"] for record in records}) >= 4
    units_per_try = {"TRY": 1.0, "EUR": 0.029, "GBP": 0.025,
                     "USD": 0.031, "AED": 0.114}
    assert sum(
        float(record["amount"]) / units_per_try[record["currency"]] for record in fraud
    ) / len(fraud) > (
        sum(float(record["amount"]) / units_per_try[record["currency"]]
            for record in legitimate) / len(legitimate)
    ) * 2
    assert sum(record["device_id"].startswith("DEV-NEW-") for record in fraud) > len(fraud) / 2


def test_parallel_cli_generation_matches_sequential_output(tmp_path):
    script = ROOT / "demo" / "generate_data.py"
    sequential = tmp_path / "sequential"
    parallel = tmp_path / "parallel"
    common = ["--cdr-rows", "250", "--sales-rows", "250", "--payment-rows", "250",
              "--employee-rows", "250"]

    subprocess.run(
        [sys.executable, str(script), "--output", str(sequential), *common,
         "--workers", "1"],
        check=True,
    )
    subprocess.run(
        [sys.executable, str(script), "--output", str(parallel), *common,
         "--workers", "4"],
        check=True,
    )

    assert {
        path.name: path.read_bytes() for path in sequential.glob("*.csv")
    } == {
        path.name: path.read_bytes() for path in parallel.glob("*.csv")
    }


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
