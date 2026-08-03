#!/usr/bin/env python3
"""Deterministic, dependency-free demo CSV generation."""

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SALES_ENTITY_ID = "11111111-1111-4111-8111-111111111111"
CDR_COLUMNS = (
    "cdr_id", "event_time", "origin_region", "destination_region",
    "duration_seconds", "call_type", "roaming", "charge_amount", "currency_code",
)
SALES_COLUMNS = (
    "sale_id", "sale_date", "region", "channel", "product_category",
    "quantity", "unit_price", "discount_rate", "net_amount",
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


def count_data_rows(path: Path) -> int:
    with path.open(encoding="utf-8") as stream:
        return sum(1 for _ in stream) - 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("demo/generated"))
    parser.add_argument("--cdr-rows", type=int, default=1_000_000)
    parser.add_argument("--sales-rows", type=int, default=50_000)
    arguments = parser.parse_args()
    if arguments.cdr_rows < 1 or arguments.sales_rows < 1:
        parser.error("row counts must be positive")
    cdr = arguments.output / "cdr.csv"
    sales = arguments.output / (
        f"sales_{SALES_ENTITY_ID}_20260728.csv"
    )
    write_cdr(cdr, arguments.cdr_rows)
    write_sales(sales, arguments.sales_rows)
    print(f"{cdr}: {count_data_rows(cdr)} rows")
    print(f"{sales}: {count_data_rows(sales)} rows")


if __name__ == "__main__":
    main()
