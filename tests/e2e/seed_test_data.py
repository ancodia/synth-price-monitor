"""
Seed the test database with Roland TR-8S across three retailers.

Provides functions to:
  - Add the three product URLs as tracked products
  - Insert baseline price history (stable prices)
  - Insert a price drop scenario that triggers alerts
  - Insert enough data points to render charts
"""
from datetime import datetime, timedelta
from typing import Tuple

from database import Database
from models import PriceSnapshot, StockStatus


# ------------------------------------------------------------------
# Test product definitions
# ------------------------------------------------------------------

ROLAND_TR8S = {
    "name": "Roland TR-8S",
    "variants": [
        {
            "site": "thomann",
            "url": "https://www.thomann.co.uk/roland_tr_8s.htm",
            "base_price": 549.00,
        },
        {
            "site": "gear4music",
            "url": "https://www.gear4music.com/Keyboards-and-Pianos/Roland-TR-8S-Rhythm-Performer/2D82",
            "base_price": 569.00,
        },
        {
            "site": "juno",
            "url": "https://www.juno.co.uk/products/roland-aira-tr-8s-rhythm-performer-drum-machine/681276-01/",
            "base_price": 559.00,
        },
    ],
}


def seed_products(db: Database) -> dict:
    """
    Insert the Roland TR-8S across all three retailers.

    Returns:
        Dict mapping site name -> product_id for use in subsequent seeding.
    """
    product_ids = {}

    for variant in ROLAND_TR8S["variants"]:
        product_id = db.add_product(
            name=ROLAND_TR8S["name"],
            site=variant["site"],
            url=variant["url"],
        )
        db.add_alert_config(product_id, threshold_percent=5.0, alert_on_stock_change=True)
        product_ids[variant["site"]] = product_id

    return product_ids


def seed_stable_price_history(db: Database, product_ids: dict, days: int = 14) -> None:
    """
    Insert `days` of stable price history at each variant's base price.

    Creates enough data points for charts to render, with small daily noise
    that stays within the alert threshold so no alerts fire during seeding.
    """
    import random

    for variant in ROLAND_TR8S["variants"]:
        product_id = product_ids[variant["site"]]
        base_price = variant["base_price"]

        for days_ago in range(days, 0, -1):
            # Tiny noise (< 1%) — well below the 5% alert threshold
            noise = random.uniform(-0.005, 0.005)
            price = round(base_price * (1 + noise), 2)

            scraped_at = datetime.now() - timedelta(days=days_ago, hours=6)

            # Bypass idempotency check — we want all rows inserted
            db.conn.execute(
                """INSERT INTO price_history
                   (product_id, price, currency, stock_status, scraped_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (product_id, price, "GBP", "in_stock", scraped_at.isoformat()),
            )

        db.conn.commit()


def seed_price_drop(
    db: Database,
    product_id: int,
    old_price: float,
    new_price: float,
) -> Tuple[PriceSnapshot, PriceSnapshot]:
    """
    Insert two snapshots that represent a price drop large enough to trigger an alert.

    The "old" snapshot is inserted 2 hours ago; the "new" one is inserted now.
    Returns (old_snapshot, new_snapshot) for assertion use.
    """
    old_snapshot = PriceSnapshot(
        product_id=product_id,
        price=old_price,
        currency="GBP",
        stock_status=StockStatus.IN_STOCK,
        scraped_at=datetime.now() - timedelta(hours=2),
    )
    new_snapshot = PriceSnapshot(
        product_id=product_id,
        price=new_price,
        currency="GBP",
        stock_status=StockStatus.IN_STOCK,
        scraped_at=datetime.now(),
    )

    for snap in [old_snapshot, new_snapshot]:
        db.conn.execute(
            """INSERT INTO price_history
               (product_id, price, currency, stock_status, scraped_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                snap.product_id,
                snap.price,
                snap.currency,
                snap.stock_status.value,
                snap.scraped_at.isoformat(),
            ),
        )

    db.conn.commit()
    return old_snapshot, new_snapshot


def seed_stock_change(
    db: Database,
    product_id: int,
    price: float,
) -> Tuple[PriceSnapshot, PriceSnapshot]:
    """
    Insert two snapshots simulating an out-of-stock -> back-in-stock transition.

    Returns (out_of_stock_snapshot, in_stock_snapshot).
    """
    oos_snapshot = PriceSnapshot(
        product_id=product_id,
        price=price,
        currency="GBP",
        stock_status=StockStatus.OUT_OF_STOCK,
        scraped_at=datetime.now() - timedelta(hours=2),
    )
    back_snapshot = PriceSnapshot(
        product_id=product_id,
        price=price,
        currency="GBP",
        stock_status=StockStatus.IN_STOCK,
        scraped_at=datetime.now(),
    )

    for snap in [oos_snapshot, back_snapshot]:
        db.conn.execute(
            """INSERT INTO price_history
               (product_id, price, currency, stock_status, scraped_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                snap.product_id,
                snap.price,
                snap.currency,
                snap.stock_status.value,
                snap.scraped_at.isoformat(),
            ),
        )

    db.conn.commit()
    return oos_snapshot, back_snapshot


def seed_full_scenario(db: Database) -> dict:
    """
    Convenience function: seed products + stable history + a price drop on Thomann.

    Returns a dict with all product_ids and the drop details for assertions.
    """
    product_ids = seed_products(db)
    seed_stable_price_history(db, product_ids, days=14)

    # Thomann drops from 549 -> 499 (~9.1% — well above 5% threshold)
    old_snap, new_snap = seed_price_drop(
        db,
        product_ids["thomann"],
        old_price=549.00,
        new_price=499.00,
    )

    return {
        "product_ids": product_ids,
        "drop": {
            "site": "thomann",
            "product_id": product_ids["thomann"],
            "old_price": 549.00,
            "new_price": 499.00,
            "percent_drop": (549.00 - 499.00) / 549.00 * 100,
            "old_snapshot": old_snap,
            "new_snapshot": new_snap,
        },
    }
