#!/usr/bin/env python3
"""Deterministic, dependency-free demo CSV generation."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import random
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

SALES_ENTITY_ID = "11111111-1111-4111-8111-111111111111"
PAYMENT_ENTITY_ID = "33333333-3333-4333-8333-333333333333"
EMPLOYEE_ENTITY_ID = "44444444-4444-4444-8444-444444444444"
CDR_COLUMNS = (
    "cdr_id", "event_time", "origin_region", "destination_region",
    "duration_seconds", "call_type", "roaming", "charge_amount", "currency_code",
)
SALES_COLUMNS = (
    "sale_id", "sale_date", "region", "channel", "product_category",
    "quantity", "unit_price", "discount_rate", "net_amount",
)
PAYMENT_COLUMNS = (
    "transaction_id", "account_id", "amount", "currency", "merchant_id",
    "merchant_category", "channel", "country", "device_id", "created_at",
    "is_fraud",
)
EMPLOYEE_COLUMNS = (
    "employee_id", "national_id_number", "badge_number", "department_code",
    "full_name", "middle_name", "country_code_char", "email", "is_active",
    "profile_photo", "hourly_rate", "performance_score", "annual_salary",
    "hire_date", "last_login_ts", "shift_start_local", "employment_tenure",
    "avg_daily_commute", "skills", "metadata", "address",
)


def write_cdr(path: Path, rows: int = 1_000_000, seed: int = 42) -> None:
    randomizer = random.Random(seed)
    regions = ("Marmara", "Ege", "Akdeniz", "İç Anadolu", "Karadeniz")
    call_types = ("VOICE", "SMS", "DATA")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(CDR_COLUMNS)
        for index in range(rows):
            call_type = call_types[index % len(call_types)]
            duration = 0 if call_type == "SMS" else 10 + randomizer.randrange(1791)
            writer.writerow((
                f"CDR-{index + 1:09d}",
                (start + timedelta(seconds=index * 17)).isoformat().replace("+00:00", "Z"),
                regions[index % len(regions)],
                regions[(index * 3 + 1) % len(regions)],
                duration,
                call_type,
                str(index % 19 == 0).lower(),
                f"{(duration * 0.012 + (2.5 if index % 19 == 0 else 0)):.2f}",
                "TRY",
            ))


def write_sales(path: Path, rows: int = 50_000, seed: int = 84) -> None:
    randomizer = random.Random(seed)
    regions = ("Marmara", "Ege", "Akdeniz", "İç Anadolu", "Karadeniz")
    channels = ("STORE", "WEB", "PARTNER")
    categories = ("Telecom", "Food", "Home", "Office")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(SALES_COLUMNS)
        for index in range(rows):
            quantity = 1 + randomizer.randrange(10)
            unit_price = 20 + randomizer.randrange(1981) / 10
            discount = (index % 5) * 0.025
            writer.writerow((
                f"SALE-{index + 1:07d}",
                (start + timedelta(days=index % 365)).date().isoformat(),
                regions[index % len(regions)],
                channels[(index * 2) % len(channels)],
                categories[(index * 3) % len(categories)],
                quantity,
                f"{unit_price:.2f}",
                f"{discount:.3f}",
                f"{quantity * unit_price * (1 - discount):.2f}",
            ))


def write_payments(path: Path, rows: int = 100_000, seed: int = 126) -> None:
    """Write deterministic payment history with learnable fraud signals.

    `is_fraud` is a synthetic historical outcome for supervised demo models. Its
    value is correlated with realistic risk signals rather than assigned as
    independent random noise.
    """
    randomizer = random.Random(seed)
    countries = ("TR", "DE", "GB", "US", "NL", "AE")
    currencies = {"TR": "TRY", "DE": "EUR", "GB": "GBP", "US": "USD",
                  "NL": "EUR", "AE": "AED"}
    local_units_per_try = {
        "TRY": 1.0, "EUR": 0.029, "GBP": 0.025, "USD": 0.031, "AED": 0.114,
    }
    categories = (
        "GROCERY", "RESTAURANT", "FUEL", "PHARMACY", "UTILITY",
        "ELECTRONICS", "TRAVEL", "JEWELRY", "GAMBLING", "DIGITAL_ASSET",
    )
    category_weights = (22, 18, 13, 9, 10, 10, 7, 4, 4, 3)
    amount_multipliers = {
        "GROCERY": 0.65, "RESTAURANT": 0.55, "FUEL": 0.7,
        "PHARMACY": 0.6, "UTILITY": 0.9, "ELECTRONICS": 2.4,
        "TRAVEL": 3.2, "JEWELRY": 4.0, "GAMBLING": 1.5,
        "DIGITAL_ASSET": 2.8,
    }
    risky_categories = {"JEWELRY", "GAMBLING", "DIGITAL_ASSET"}
    channels = ("pos", "online", "atm", "mobile")
    account_count = max(200, min(12_000, rows // 8))
    merchant_count = max(80, min(2_000, rows // 35))
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    accounts = []
    for index in range(account_count):
        home_country = randomizer.choices(countries, weights=(72, 8, 6, 6, 5, 3))[0]
        typical_amount_try = randomizer.lognormvariate(6.35, 0.55)
        devices = (
            f"DEV-{index + 1:06d}-A",
            f"DEV-{index + 1:06d}-B",
        )
        accounts.append((home_country, typical_amount_try, devices))

    merchants = []
    for index in range(merchant_count):
        category = randomizer.choices(categories, weights=category_weights)[0]
        country = randomizer.choices(countries, weights=(62, 9, 8, 8, 7, 6))[0]
        merchants.append((category, country, f"MER-{index + 1:06d}"))
    merchants_by_category = {
        category: [merchant for merchant in merchants if merchant[0] == category]
        for category in categories
    }

    last_transaction: dict[int, datetime] = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(PAYMENT_COLUMNS)
        for index in range(rows):
            account_index = randomizer.randrange(account_count)
            home_country, typical_amount_try, known_devices = accounts[account_index]
            merchant_category, merchant_country, merchant_id = merchants[
                randomizer.randrange(merchant_count)
            ]
            fraud = randomizer.random() < 0.018

            if fraud:
                merchant_category = randomizer.choices(
                    categories, weights=(2, 2, 1, 1, 1, 8, 8, 18, 28, 31),
                )[0]
                category_merchants = merchants_by_category[merchant_category]
                if category_merchants:
                    _, merchant_country, merchant_id = randomizer.choice(category_merchants)
                country = randomizer.choice(tuple(
                    item for item in countries if item != home_country
                )) if randomizer.random() < 0.78 else home_country
                channel = randomizer.choices(
                    channels, weights=(5, 48, 8, 39),
                )[0]
                device_id = (
                    "" if randomizer.random() < 0.18
                    else f"DEV-NEW-{index + 1:09d}"
                )
                amount_try = typical_amount_try * randomizer.uniform(4.5, 13.0)
                hour = randomizer.choice((0, 1, 2, 3, 4, 23))
            else:
                country = home_country if randomizer.random() < 0.94 else merchant_country
                channel = randomizer.choices(
                    channels, weights=(48, 25, 7, 20),
                )[0]
                device_id = "" if randomizer.random() < 0.025 else randomizer.choices(
                    known_devices, weights=(92, 8),
                )[0]
                amount_try = typical_amount_try * amount_multipliers[merchant_category]
                amount_try *= randomizer.lognormvariate(0, 0.38)
                hour = int(min(23, max(0, randomizer.normalvariate(14, 4.2))))

            day = randomizer.randrange(181)
            minute = randomizer.randrange(60)
            second = randomizer.randrange(60)
            created_at = start + timedelta(
                days=day, hours=hour, minutes=minute, seconds=second,
            )
            previous = last_transaction.get(account_index)
            if fraud and previous is not None and randomizer.random() < 0.42:
                created_at = previous + timedelta(seconds=randomizer.randrange(15, 180))
            last_transaction[account_index] = created_at

            # A few naturally risky-looking transactions remain legitimate, and
            # a few labelled frauds are less obvious, avoiding a perfectly
            # separable toy dataset.
            if not fraud and merchant_category in risky_categories \
                    and country != home_country and amount_try > typical_amount_try * 3:
                fraud = randomizer.random() < 0.12

            currency = currencies[country]
            amount = amount_try * local_units_per_try[currency]

            writer.writerow((
                f"TXN-{index + 1:09d}",
                f"ACC-{account_index + 1:07d}",
                f"{max(0.50, amount):.2f}",
                currency,
                merchant_id,
                merchant_category,
                channel,
                country,
                device_id,
                created_at.isoformat().replace("+00:00", "Z"),
                str(fraud).lower(),
            ))


def write_employees(path: Path, rows: int = 50_000, seed: int = 168) -> None:
    """Write deterministic synthetic HR/payroll records.

    CSV has no native representation for Spark binary, interval, array, map,
    struct, CHAR/VARCHAR, or timestamp-without-time-zone types. Those fields
    therefore use lossless transport representations: base64, ISO-8601
    durations, JSON, or plain bounded strings. The governed CSV discovery path
    can ingest them without entity-specific code and preserve their values in
    the resulting Parquet dataset.
    """
    randomizer = random.Random(seed)
    reference_date = datetime(2026, 8, 7, tzinfo=timezone.utc)
    departments = {
        1: ("Sales", ("negotiation", "crm", "forecasting")),
        2: ("Finance", ("accounting", "budgeting", "risk")),
        3: ("Engineering", ("python", "spark", "sql")),
        4: ("Operations", ("planning", "logistics", "quality")),
        5: ("Human Resources", ("recruiting", "payroll", "development")),
        6: ("Marketing", ("campaigns", "analytics", "content")),
    }
    locations = (
        ("TR", "Türkiye", "İstanbul", "34394", "Büyükdere Cd. 42"),
        ("DE", "Germany", "Frankfurt", "60329", "Bahnhofstrasse 1"),
        ("GB", "United Kingdom", "London", "EC2A 4NE", "Finsbury Sq. 12"),
        ("NL", "Netherlands", "Amsterdam", "1012 JS", "Damrak 70"),
        ("US", "United States", "New York", "10001", "West 31st St. 18"),
    )
    first_names = (
        "Ada", "Ahmet", "Anna", "Can", "Deniz", "Elif", "Emil", "Leyla",
        "Maya", "Mehmet", "Mina", "Noah", "Selin", "Sofia", "Yusuf",
    )
    last_names = (
        "Acar", "Arslan", "Bauer", "Demir", "Ersoy", "Jansen", "Kaya",
        "Keller", "Morgan", "Öztürk", "Schmidt", "Şahin", "Taylor", "Yılmaz",
    )
    salary_bases = {1: 720_000, 2: 780_000, 3: 960_000,
                    4: 690_000, 5: 650_000, 6: 740_000}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(EMPLOYEE_COLUMNS)
        for index in range(rows):
            employee_id = 1001 + index
            department_code = 1 + index % len(departments)
            department, department_skills = departments[department_code]
            country_code, country, city, postal_code, street = locations[
                (index * 3 + department_code) % len(locations)
            ]
            first_name = first_names[index % len(first_names)]
            last_name = last_names[(index * 7 + department_code) % len(last_names)]
            full_name = f"{first_name} {last_name}"
            hire_days_ago = 90 + randomizer.randrange(16 * 365)
            hire_date = (reference_date - timedelta(days=hire_days_ago)).date()
            tenure_months = max(1, (reference_date.date().year - hire_date.year) * 12
                                + reference_date.date().month - hire_date.month)
            is_active = index % 23 != 0
            performance = "" if index % 17 == 0 else f"{min(100, max(35, randomizer.normalvariate(79, 9))):.2f}"
            annual_salary = salary_bases[department_code]
            annual_salary *= 1 + min(0.65, tenure_months / 240)
            annual_salary *= randomizer.uniform(0.88, 1.14)
            hourly_rate = annual_salary / 2080
            last_login = ""
            if is_active and index % 13 != 0:
                last_login = (reference_date - timedelta(
                    hours=randomizer.randrange(1, 24 * 45),
                    minutes=randomizer.randrange(60),
                )).isoformat().replace("+00:00", "Z")
            shift_hour = (7 + department_code + index % 3) % 24
            shift_start = datetime(2026, 8, 7, shift_hour, index % 4 * 15)
            commute_minutes = 15 + randomizer.randrange(106)
            skills = list(department_skills)
            if index % 4 == 0:
                skills.append("leadership")
            metadata = {
                "team": f"{department.lower().replace(' ', '-')}-{1 + index % 8}",
                "level": ("junior", "mid", "senior", "lead")[index % 4],
                "cost_center": f"CC-{department_code:02d}-{1 + index % 5:02d}",
            }
            address = {
                "street": street,
                "city": city,
                "postal_code": postal_code,
                "country": country,
            }
            photo = ""
            if index % 5 != 0:
                thumbnail = b"\x89PNG\r\n\x1a\n" + employee_id.to_bytes(4, "big")
                photo = base64.b64encode(thumbnail).decode("ascii")
            writer.writerow((
                employee_id,
                900_123_456_789 + index,
                1 + index % 32_767,
                department_code,
                full_name,
                "",
                country_code,
                f"{first_name}.{last_name}.{employee_id}@example.test".lower()
                .replace("ı", "i").replace("ş", "s").replace("ö", "o"),
                str(is_active).lower(),
                photo,
                f"{hourly_rate:.2f}",
                performance,
                f"{annual_salary:.2f}",
                hire_date.isoformat(),
                last_login,
                shift_start.isoformat(sep=" ", timespec="seconds"),
                f"P{tenure_months // 12}Y{tenure_months % 12}M",
                f"PT{commute_minutes // 60}H{commute_minutes % 60}M",
                json.dumps(skills, ensure_ascii=False, separators=(",", ":")),
                json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                json.dumps(address, ensure_ascii=False, separators=(",", ":")),
            ))


def count_data_rows(path: Path) -> int:
    with path.open(encoding="utf-8") as stream:
        return sum(1 for _ in stream) - 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("demo/generated"))
    parser.add_argument("--cdr-rows", type=int, default=1_000_000)
    parser.add_argument("--sales-rows", type=int, default=50_000)
    parser.add_argument("--payment-rows", type=int, default=100_000)
    parser.add_argument("--employee-rows", type=int, default=50_000)
    parser.add_argument(
        "--workers", type=int, default=4,
        help="parallel dataset writers (default: 4)",
    )
    arguments = parser.parse_args()
    if (arguments.cdr_rows < 1 or arguments.sales_rows < 1
            or arguments.payment_rows < 1 or arguments.employee_rows < 1):
        parser.error("row counts must be positive")
    if arguments.workers < 1 or arguments.workers > 4:
        parser.error("workers must be between 1 and 4")
    cdr = arguments.output / "cdr.csv"
    sales = arguments.output / (
        f"sales_{SALES_ENTITY_ID}_20260728.csv"
    )
    payments = arguments.output / (
        f"payment_transactions_{PAYMENT_ENTITY_ID}_20260728.csv"
    )
    employees = arguments.output / (
        f"employee_records_{EMPLOYEE_ENTITY_ID}_20260728.csv"
    )
    jobs = (
        (write_cdr, cdr, arguments.cdr_rows),
        (write_sales, sales, arguments.sales_rows),
        (write_payments, payments, arguments.payment_rows),
        (write_employees, employees, arguments.employee_rows),
    )
    if arguments.workers == 1:
        for writer, path, rows in jobs:
            writer(path, rows)
    else:
        with ProcessPoolExecutor(max_workers=arguments.workers) as executor:
            futures = [executor.submit(writer, path, rows) for writer, path, rows in jobs]
            # Resolve in declaration order for stable console output; generation
            # itself runs concurrently and every failure is propagated.
            for future in futures:
                future.result()
    for _, path, rows in jobs:
        print(f"{path}: {rows} rows")


if __name__ == "__main__":
    main()
