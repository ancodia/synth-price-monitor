"""
Generate realistic sample price history for portfolio demonstration.

Creates 7 demo products with 14 days of randomised price history,
including occasional drops and stock changes.

Usage:
    python scripts/generate_sample_data.py
"""

import os
import random
import sqlite3
from datetime import datetime, timedelta

from pathlib import Path
import numpy as np

DB_PATH = Path(__file__).parent.parent / "price_monitor.db"


def generate_sample_data() -> None:
    """Insert 7 demo products and 14 days of price history."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Ensure schema exists (in case this is run before main.py)
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

    # Demo products: (name, site, url, base_price_gbp)
    products = [
        (
            "Korg Minilogue XD",
            "thomann",
            "https://www.thomann.co.uk/korg_minilogue_xd.htm",
            589.00,
        ),
        (
            "Korg Minilogue XD",
            "gear4music",
            "https://www.gear4music.com/Keyboards-and-Pianos/Korg-Minilogue-XD/2TGY",
            599.00,
        ),
        (
            "Behringer DeepMind 12",
            "thomann",
            "https://www.thomann.co.uk/behringer_deepmind12.htm",
            725.00,
        ),
        (
            "Behringer DeepMind 12",
            "gear4music",
            "https://www.gear4music.com/Keyboards-and-Pianos/Behringer-Deepmind-12X-Synthesizer/73A2",
            729.00,
        ),
        (
            "Arturia MiniFreak",
            "thomann",
            "https://www.thomann.co.uk/arturia_minifreak.htm",
            539.00,
        ),
        (
            "Arturia MiniFreak",
            "juno",
            "https://www.juno.co.uk/products/arturia-minifreak-vocoder-edition-6-voice-polyphonic-hybrid/1093044-01/",
            549.00,
        ),
        (
            "Moog Subsequent 37",
            "thomann",
            "https://www.thomann.co.uk/moog_subsequent_37.htm",
            1599.00,
        ),
        (
            "Moog Subsequent 37",
            "juno",
            "https://www.juno.co.uk/products/moog-subsequent-37-paraphonic-analogue-synthesiser/661865-01/",
            1619.00,
        ),
    ]

    inserted_products = 0

    for name, site, url, base_price in products:
        # Skip if already in DB (idempotent re-runs)
        existing = cursor.execute(
            "SELECT id FROM products WHERE url = ?", (url,)
        ).fetchone()
        if existing:
            print(f"  Skipping existing: {name} ({site})")
            continue

        cursor.execute(
            "INSERT INTO products (name, site, url, added_date) VALUES (?, ?, ?, ?)",
            (name, site, url, (datetime.now() - timedelta(days=14)).isoformat()),
        )
        product_id = cursor.lastrowid
        inserted_products += 1

        # --- Generate 14 days of price history ---
        current_price = base_price
        stock = "in_stock"

        for days_ago in range(14, 0, -1):
            # Random walk with realistic patterns
            rand = random.random()
            if rand < 0.15:
                # 15% chance: meaningful price drop (3–8%)
                drop = random.uniform(0.03, 0.08)
                current_price *= 1 - drop
            elif rand < 0.20:
                # 5% chance: small price increase (1–3%)
                increase = random.uniform(0.01, 0.03)
                current_price *= 1 + increase
            else:
                # Small daily noise
                noise = np.random.normal(0, 0.005)
                current_price *= 1 + noise

            current_price = max(current_price, base_price * 0.7)  # floor at -30%

            # Occasional stock changes
            if random.random() < 0.05:
                stock = random.choice(["low_stock", "out_of_stock"])
            elif stock != "in_stock" and random.random() < 0.3:
                stock = "in_stock"

            # Realistic time variation (scraper doesn't always run at exactly 6am)
            hour_offset = random.randint(-2, 2)
            minute_offset = random.randint(0, 59)
            scraped_at = (datetime.now() - timedelta(days=days_ago)).replace(
                hour=max(0, min(23, 6 + hour_offset)),
                minute=minute_offset,
                second=0,
                microsecond=0,
            )

            cursor.execute(
                """INSERT INTO price_history
                   (product_id, price, currency, stock_status, scraped_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    product_id,
                    round(current_price, 2),
                    "GBP",
                    stock,
                    scraped_at.isoformat(),
                ),
            )

        # Add alert config
        cursor.execute(
            """INSERT INTO alert_config
               (product_id, threshold_percent, alert_on_stock_change)
               VALUES (?, ?, ?)""",
            (product_id, 5.0, 1),
        )

        # Simulate some products having had recent alerts
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
    print("  14 days of price history per product")
    print("  Realistic price fluctuations and stock changes")
    print(f"\nDB path: {os.path.abspath(DB_PATH)}")
    print("\nNext step: streamlit run dashboard/app.py")


if __name__ == "__main__":
    generate_sample_data()
