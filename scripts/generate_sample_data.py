"""
Generate realistic sample price history for portfolio demonstration.

Creates 8 demo products with 30 days of price history:
  - Korg Minilogue XD:      stable price for 8+ days  → filtered out by "Recent price drops"
  - Behringer DeepMind 12:  currently out of stock     → filtered out by "In stock only"
  - Arturia MiniFreak:      occasional realistic drops
  - Moog Subsequent 37:     occasional realistic drops

Prices are stable most days (realistic), only changing every few days.

Usage:
    python scripts/generate_sample_data.py
"""

import os
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "price_monitor.db"

DAYS = 30


def _build_history(base_price, days, freeze_last_n=0, force_out_of_stock=False):
    """
    Return a list of (days_ago, price, stock_status) tuples, oldest first.

    freeze_last_n:       hold price constant for the final N days (no drops/rises)
    force_out_of_stock:  override the most recent entry's stock to 'out_of_stock'
    """
    entries = []
    price = base_price
    stock = "in_stock"

    for days_ago in range(days, 0, -1):
        frozen = days_ago <= freeze_last_n

        if not frozen:
            r = random.random()
            if r < 0.07:
                # ~7% chance of a meaningful price drop
                price *= 1 - random.uniform(0.03, 0.08)
            elif r < 0.10:
                # ~3% chance of a small price rise
                price *= 1 + random.uniform(0.01, 0.03)
            # else: price holds (~90% of days — stable)

            price = max(price, base_price * 0.70)

            # Infrequent stock fluctuations
            if random.random() < 0.04:
                stock = random.choice(["low_stock", "out_of_stock"])
            elif stock != "in_stock" and random.random() < 0.40:
                stock = "in_stock"

        entries.append((days_ago, round(price, 2), stock))

    if force_out_of_stock and entries:
        d, p, _ = entries[-1]
        entries[-1] = (d, p, "out_of_stock")

    return entries


def generate_sample_data() -> None:
    """Insert demo products and 30 days of price history."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            site        TEXT NOT NULL,
            url         TEXT NOT NULL UNIQUE,
            is_active   INTEGER NOT NULL DEFAULT 1,
            added_date  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS price_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER NOT NULL REFERENCES products(id),
            price       REAL NOT NULL,
            currency    TEXT NOT NULL DEFAULT 'GBP',
            stock_status TEXT NOT NULL,
            scraped_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS alert_config (
            product_id          INTEGER PRIMARY KEY REFERENCES products(id),
            threshold_percent   REAL NOT NULL DEFAULT 5.0,
            alert_on_stock_change INTEGER NOT NULL DEFAULT 1,
            last_alert_sent     TEXT
        );
    """)

    # (name, site, url, base_price, freeze_last_n, force_out_of_stock)
    products = [
        # Korg Minilogue XD — price frozen for 8 days (no recent drop)
        (
            "Korg Minilogue XD",
            "thomann",
            "https://www.thomann.co.uk/korg_minilogue_xd.htm",
            589.00,
            8,
            False,
        ),
        (
            "Korg Minilogue XD",
            "gear4music",
            "https://www.gear4music.com/Keyboards-and-Pianos/Korg-Minilogue-XD/2TGY",
            599.00,
            8,
            False,
        ),
        # Behringer DeepMind 12 — currently out of stock on both sites
        (
            "Behringer DeepMind 12",
            "thomann",
            "https://www.thomann.co.uk/behringer_deepmind12.htm",
            725.00,
            0,
            True,
        ),
        (
            "Behringer DeepMind 12",
            "gear4music",
            "https://www.gear4music.com/Keyboards-and-Pianos/Behringer-Deepmind-12X-Synthesizer/73A2",
            729.00,
            0,
            True,
        ),
        # Arturia MiniFreak — normal fluctuations
        (
            "Arturia MiniFreak",
            "thomann",
            "https://www.thomann.co.uk/arturia_minifreak.htm",
            539.00,
            0,
            False,
        ),
        (
            "Arturia MiniFreak",
            "juno",
            "https://www.juno.co.uk/products/arturia-minifreak-vocoder-edition-6-voice-polyphonic-hybrid/1093044-01/",
            549.00,
            0,
            False,
        ),
        # Moog Subsequent 37 — normal fluctuations
        (
            "Moog Subsequent 37",
            "thomann",
            "https://www.thomann.co.uk/moog_subsequent_37.htm",
            1599.00,
            0,
            False,
        ),
        (
            "Moog Subsequent 37",
            "juno",
            "https://www.juno.co.uk/products/moog-subsequent-37-paraphonic-analogue-synthesiser/661865-01/",
            1619.00,
            0,
            False,
        ),
    ]

    inserted_products = 0

    for name, site, url, base_price, freeze_last_n, force_out_of_stock in products:
        existing = cursor.execute(
            "SELECT id FROM products WHERE url = ?", (url,)
        ).fetchone()
        if existing:
            print(f"  Skipping existing: {name} ({site})")
            continue

        added = (datetime.now() - timedelta(days=DAYS)).isoformat()
        cursor.execute(
            "INSERT INTO products (name, site, url, added_date) VALUES (?, ?, ?, ?)",
            (name, site, url, added),
        )
        product_id = cursor.lastrowid
        inserted_products += 1

        history = _build_history(
            base_price,
            DAYS,
            freeze_last_n=freeze_last_n,
            force_out_of_stock=force_out_of_stock,
        )

        for days_ago, price, stock in history:
            hour_offset = random.randint(-2, 2)
            scraped_at = (datetime.now() - timedelta(days=days_ago)).replace(
                hour=max(0, min(23, 6 + hour_offset)),
                minute=random.randint(0, 59),
                second=0,
                microsecond=0,
            )
            cursor.execute(
                """INSERT INTO price_history
                   (product_id, price, currency, stock_status, scraped_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (product_id, price, "GBP", stock, scraped_at.isoformat()),
            )

        cursor.execute(
            """INSERT INTO alert_config
               (product_id, threshold_percent, alert_on_stock_change)
               VALUES (?, ?, ?)""",
            (product_id, 5.0, 1),
        )

        if random.random() < 0.4:
            last_alert = datetime.now() - timedelta(days=random.randint(1, 7))
            cursor.execute(
                "UPDATE alert_config SET last_alert_sent = ? WHERE product_id = ?",
                (last_alert.isoformat(), product_id),
            )

    conn.commit()
    conn.close()

    print("\nSample data generated successfully!")
    print(f"  {inserted_products} products inserted")
    print(f"  {DAYS} days of price history per product")
    print("  Korg Minilogue XD:    price stable for last 8 days (no recent drop)")
    print("  Behringer DeepMind 12: currently out of stock on all sites")
    print("  Arturia MiniFreak / Moog Subsequent 37: realistic occasional fluctuations")
    print(f"\nDB path: {os.path.abspath(DB_PATH)}")
    print("\nNext step: streamlit run dashboard/app.py")


if __name__ == "__main__":
    generate_sample_data()
