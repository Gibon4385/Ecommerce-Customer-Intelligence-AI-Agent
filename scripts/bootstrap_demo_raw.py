from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

TABLES = {
    "events": ["event_id", "user_id", "product_id", "event_type", "event_timestamp"],
    "order_items": [
        "order_item_id",
        "order_id",
        "product_id",
        "user_id",
        "quantity",
        "item_price",
        "item_total",
    ],
    "orders": ["order_id", "user_id", "order_date", "order_status", "total_amount"],
    "products": ["product_id", "product_name", "category", "brand", "price", "rating"],
    "reviews": [
        "review_id",
        "order_id",
        "product_id",
        "user_id",
        "rating",
        "review_text",
        "review_date",
    ],
    "users": ["user_id", "name", "email", "gender", "city", "signup_date"],
}

RAW_ROW_LIMITS = {
    "events": 80_000,
    "order_items": 43_525,
    "orders": 20_000,
    "products": 2_000,
    "reviews": 15_001,
    "users": 10_000,
}


def _demo_hash(user_id: str) -> str:
    email = f"{user_id.casefold()}@example.invalid"
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


def bootstrap_demo_identifiers(root: Path, *, force: bool = False) -> None:
    data = root / "data"
    users_path = data / "1_staging/stg_users.csv"
    hashed_users_path = data / "1_staging/stg_users_hashed.csv"
    if users_path.is_file() and (force or not hashed_users_path.exists()):
        with users_path.open(encoding="utf-8", newline="") as input_handle:
            users = list(csv.DictReader(input_handle))
        hashed_users_path.parent.mkdir(parents=True, exist_ok=True)
        with hashed_users_path.open("w", encoding="utf-8", newline="") as output_handle:
            writer = csv.DictWriter(output_handle, fieldnames=["user_id", "hashed_email"])
            writer.writeheader()
            writer.writerows(
                {"user_id": row["user_id"], "hashed_email": _demo_hash(row["user_id"])}
                for row in users
            )

    seed_path = data / "3_marts/mart_lookalike_seed.csv"
    canonical_path = data / "3_marts/marketing/mart_lookalike_hashed_email.csv"
    if seed_path.is_file() and (force or not canonical_path.exists()):
        with seed_path.open(encoding="utf-8", newline="") as input_handle:
            seeds = list(csv.DictReader(input_handle))
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "user_id",
            "segment",
            "recency",
            "frequency",
            "monetary",
            "predicted_profit_90_days",
            "hashed_email",
        ]
        with canonical_path.open("w", encoding="utf-8", newline="") as output_handle:
            writer = csv.DictWriter(output_handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(
                {
                    **{field: row[field] for field in fields[:-1]},
                    "hashed_email": _demo_hash(row["user_id"]),
                }
                for row in seeds
            )


def bootstrap(root: Path, *, force: bool = False) -> dict[str, int]:
    bootstrap_demo_identifiers(root, force=force)
    staging = root / "data/1_staging"
    raw = root / "data/9_raw"
    raw.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, fields in TABLES.items():
        source = staging / f"stg_{name}.csv"
        target = raw / f"{name}.csv"
        if target.exists() and not force:
            with target.open(encoding="utf-8", newline="") as handle:
                counts[name] = sum(1 for _ in handle) - 1
            continue
        if not source.is_file():
            raise FileNotFoundError(f"missing staging source: {source}")
        count = 0
        with source.open(encoding="utf-8", newline="") as input_handle:
            reader = csv.DictReader(input_handle)
            with target.open("w", encoding="utf-8", newline="") as output_handle:
                writer = csv.DictWriter(output_handle, fieldnames=fields)
                writer.writeheader()
                for row in reader:
                    if count >= RAW_ROW_LIMITS[name]:
                        break
                    if name == "users":
                        row["email"] = f"{row['user_id'].casefold()}@example.invalid"
                    writer.writerow({field: row.get(field, "") for field in fields})
                    count += 1
        counts[name] = count
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    counts = bootstrap(args.root.resolve(), force=args.force)
    for name, count in counts.items():
        print(f"raw_{name}: {count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
