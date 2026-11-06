from __future__ import annotations

import csv
import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = DATA / "ops_marts"
SEED = 20261105


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write(name: str, fields: list[str], rows: list[dict[str, object]]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def generate(seed: int = SEED) -> dict[str, int]:
    rng = random.Random(seed)
    customers = _read(DATA / "2_intermediate" / "int_customer_segments.csv")
    segments = sorted({row["segment"] for row in customers})
    user_ids = [row["user_id"] for row in customers]
    campaign_types = ["EDM", "SMS", "Retargeting", "Lookalike"]
    campaigns: list[dict[str, object]] = []
    base_date = date(2026, 6, 1)
    for index, segment in enumerate(segments, start=1):
        audience = rng.randint(300, 1200)
        sent = rng.randint(int(audience * 0.85), audience)
        opened = rng.randint(int(sent * 0.2), int(sent * 0.65))
        clicked = rng.randint(int(opened * 0.1), int(opened * 0.5))
        converted = rng.randint(0, clicked)
        revenue = round(converted * rng.uniform(60, 300), 2)
        cost = round(sent * rng.uniform(0.5, 2.0), 2)
        start = base_date + timedelta(days=(index - 1) * 3)
        campaigns.append(
            {
                "campaign_id": f"CMP{index:04d}",
                "campaign_name": f"Synthetic {segment} Campaign",
                "campaign_type": campaign_types[(index - 1) % len(campaign_types)],
                "start_date": start.isoformat(),
                "end_date": (start + timedelta(days=6)).isoformat(),
                "target_segment": segment,
                "offer_type": "percentage_discount",
                "discount_pct": 10.0,
                "audience_size": audience,
                "sent": sent,
                "opened": opened,
                "clicked": clicked,
                "converted": converted,
                "revenue": f"{revenue:.2f}",
                "cost": f"{cost:.2f}",
                "open_rate": round(opened / sent, 6),
                "click_rate": round(clicked / sent, 6),
                "conversion_rate": round(converted / sent, 6),
                "roas": round(revenue / cost, 6),
            }
        )
    campaign_fields = list(campaigns[0])
    _write("mart_ops_campaign_performance", campaign_fields, campaigns)

    outcomes = ["opened", "clicked", "converted", "none"]
    channels = ["email", "sms", "retargeting"]
    touches: list[dict[str, object]] = []
    sample_size = min(500, len(user_ids))
    for index, user_id in enumerate(rng.sample(user_ids, sample_size), start=1):
        campaign = campaigns[(index - 1) % len(campaigns)]
        touches.append(
            {
                "touch_id": f"TCH{index:06d}",
                "user_id": user_id,
                "channel": channels[(index - 1) % len(channels)],
                "campaign_id": campaign["campaign_id"],
                "touch_date": (base_date + timedelta(days=rng.randint(0, 35))).isoformat(),
                "offer_type": campaign["offer_type"],
                "discount_pct": campaign["discount_pct"],
                "outcome": rng.choice(outcomes),
            }
        )
    _write("mart_ops_customer_touch_log", list(touches[0]), touches)

    pipeline: list[dict[str, object]] = []
    run_date = date(2026, 7, 7)
    mart_paths = sorted((DATA / "3_marts").glob("mart_*.csv"))
    mart_paths.append(DATA / "3_marts/marketing/mart_lookalike_hashed_email.csv")
    for path in mart_paths:
        with path.open(encoding="utf-8") as handle:
            row_count = sum(1 for _ in handle) - 1
        pipeline.append(
            {
                "model_name": path.stem,
                "layer": "marts",
                "run_date": run_date.isoformat(),
                "run_finished_at": datetime(
                    2026, 7, 7, 2, 0, tzinfo=UTC
                ).isoformat(),
                "status": "success",
                "row_count": row_count,
                "data_as_of": date(2026, 7, 6).isoformat(),
            }
        )
    _write("mart_ops_pipeline_status", list(pipeline[0]), pipeline)
    return {
        "mart_ops_campaign_performance": len(campaigns),
        "mart_ops_customer_touch_log": len(touches),
        "mart_ops_pipeline_status": len(pipeline),
    }


if __name__ == "__main__":
    for table, count in generate().items():
        print(f"{table}: {count} rows")

