"""
SQLite database layer for the Synth Price Monitor.

Design note: SQLite + Git commit pattern enables zero-cost hosting and built-in
backup via Git history. Not suitable for > ~1000 products or sub-hourly scraping.
Production alternative: PostgreSQL on RDS or DynamoDB for serverless.
"""
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List
from loguru import logger

from models import Product, PriceSnapshot, AlertConfig, StockStatus


class Database:
    def __init__(self, db_path: str = "price_monitor.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        """Explicitly close the database connection."""
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        self.conn.executescript("""
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

            CREATE INDEX IF NOT EXISTS idx_price_history_product
                ON price_history(product_id, scraped_at DESC);
        """)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def add_product(self, name: str, site: str, url: str) -> int:
        cursor = self.conn.execute(
            "INSERT INTO products (name, site, url, added_date) VALUES (?, ?, ?, ?)",
            (name, site, url, datetime.now().isoformat()),
        )
        self.conn.commit()
        logger.success(f"Added product: {name} ({site})")
        return cursor.lastrowid

    def get_product(self, product_id: int) -> Optional[Product]:
        row = self.conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if not row:
            return None
        return Product(
            id=row["id"],
            name=row["name"],
            site=row["site"],
            url=row["url"],
            is_active=bool(row["is_active"]),
            added_date=datetime.fromisoformat(row["added_date"]),
        )

    def get_all_active_products(self) -> List[Product]:
        rows = self.conn.execute(
            "SELECT * FROM products WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        return [
            Product(
                id=r["id"],
                name=r["name"],
                site=r["site"],
                url=r["url"],
                is_active=bool(r["is_active"]),
                added_date=datetime.fromisoformat(r["added_date"]),
            )
            for r in rows
        ]

    def delete_product(self, product_id: int) -> None:
        self.conn.execute(
            "UPDATE products SET is_active = 0 WHERE id = ?", (product_id,)
        )
        self.conn.commit()
        logger.info(f"Soft-deleted product_id={product_id}")

    # ------------------------------------------------------------------
    # Price history
    # ------------------------------------------------------------------

    def should_insert_snapshot(self, product_id: int, new_snapshot: PriceSnapshot) -> bool:
        """
        Idempotency check: only insert if price OR stock status changed.
        Prevents duplicate rows when data hasn't changed between scrapes.
        """
        last = self.get_last_snapshot(product_id)

        if last is None:
            return True  # First snapshot for this product

        price_changed = abs(last.price - new_snapshot.price) > 0.01
        stock_changed = last.stock_status != new_snapshot.stock_status

        if not (price_changed or stock_changed):
            logger.debug(f"Skipping duplicate snapshot for product_id={product_id}")
            return False

        return True

    def insert_snapshot(self, snapshot: PriceSnapshot) -> Optional[int]:
        """Insert a price snapshot, respecting idempotency."""
        if not self.should_insert_snapshot(snapshot.product_id, snapshot):
            return None

        cursor = self.conn.execute(
            """INSERT INTO price_history (product_id, price, currency, stock_status, scraped_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                snapshot.product_id,
                snapshot.price,
                snapshot.currency,
                snapshot.stock_status.value,
                snapshot.scraped_at.isoformat(),
            ),
        )
        self.conn.commit()
        logger.success(f"Inserted snapshot for product_id={snapshot.product_id}")
        return cursor.lastrowid

    def get_last_snapshot(self, product_id: int) -> Optional[PriceSnapshot]:
        row = self.conn.execute(
            """SELECT * FROM price_history
               WHERE product_id = ?
               ORDER BY scraped_at DESC LIMIT 1""",
            (product_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_snapshot(row)

    def get_price_history(self, product_id: int, days: int = 30) -> List[PriceSnapshot]:
        since = (datetime.now() - timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            """SELECT * FROM price_history
               WHERE product_id = ? AND scraped_at >= ?
               ORDER BY scraped_at ASC""",
            (product_id, since),
        ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def _row_to_snapshot(self, row) -> PriceSnapshot:
        return PriceSnapshot(
            id=row["id"],
            product_id=row["product_id"],
            price=row["price"],
            currency=row["currency"],
            stock_status=StockStatus(row["stock_status"]),
            scraped_at=datetime.fromisoformat(row["scraped_at"]),
        )

    # ------------------------------------------------------------------
    # Alert configuration
    # ------------------------------------------------------------------

    def add_alert_config(
        self,
        product_id: int,
        threshold_percent: float = 5.0,
        alert_on_stock_change: bool = True,
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO alert_config
               (product_id, threshold_percent, alert_on_stock_change)
               VALUES (?, ?, ?)""",
            (product_id, threshold_percent, int(alert_on_stock_change)),
        )
        self.conn.commit()

    def get_alert_config(self, product_id: int) -> Optional[AlertConfig]:
        row = self.conn.execute(
            "SELECT * FROM alert_config WHERE product_id = ?", (product_id,)
        ).fetchone()
        if not row:
            return None
        return AlertConfig(
            product_id=row["product_id"],
            threshold_percent=row["threshold_percent"],
            alert_on_stock_change=bool(row["alert_on_stock_change"]),
            last_alert_sent=(
                datetime.fromisoformat(row["last_alert_sent"])
                if row["last_alert_sent"]
                else None
            ),
        )

    def update_alert_config(
        self,
        product_id: int,
        threshold_percent: float,
        alert_on_stock_change: bool,
    ) -> None:
        self.conn.execute(
            """UPDATE alert_config
               SET threshold_percent = ?, alert_on_stock_change = ?
               WHERE product_id = ?""",
            (threshold_percent, int(alert_on_stock_change), product_id),
        )
        self.conn.commit()

    def update_last_alert(self, product_id: int) -> None:
        self.conn.execute(
            "UPDATE alert_config SET last_alert_sent = ? WHERE product_id = ?",
            (datetime.now().isoformat(), product_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Metrics / aggregates (used by dashboard)
    # ------------------------------------------------------------------

    def count_active_alerts(self) -> int:
        """Number of products that have alert configs configured."""
        row = self.conn.execute(
            """SELECT COUNT(*) FROM alert_config ac
               JOIN products p ON ac.product_id = p.id
               WHERE p.is_active = 1"""
        ).fetchone()
        return row[0]

    def count_alerts_last_24h(self) -> int:
        """Number of alert notifications sent in the last 24 hours."""
        since = (datetime.now() - timedelta(hours=24)).isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) FROM alert_config WHERE last_alert_sent >= ?", (since,)
        ).fetchone()
        return row[0]

    def had_price_drop_last_7_days(self, product_id: int) -> bool:
        """Return True if the product had any price decrease in the last 7 days."""
        history = self.get_price_history(product_id, days=7)
        if len(history) < 2:
            return False
        for i in range(1, len(history)):
            if history[i].price < history[i - 1].price:
                return True
        return False

    def get_biggest_drop_last_30_days(self, product_id: int) -> Optional[float]:
        """Return the largest single-day price drop percentage in the last 30 days."""
        history = self.get_price_history(product_id, days=30)
        if len(history) < 2:
            return None
        biggest = 0.0
        for i in range(1, len(history)):
            if history[i - 1].price > 0 and history[i].price < history[i - 1].price:
                drop = (history[i - 1].price - history[i].price) / history[i - 1].price * 100
                if drop > biggest:
                    biggest = drop
        return biggest if biggest > 0 else None
