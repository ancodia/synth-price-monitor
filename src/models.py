"""
Data models for the Synth Price Monitor.
Pydantic models enforce type safety at every boundary.
"""
from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class StockStatus(str, Enum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"


class ScrapedProduct(BaseModel):
    """Raw data returned directly from a scraper."""
    name: str
    price: float
    currency: str = "GBP"
    stock_status: StockStatus
    url: str
    site: str


class Product(BaseModel):
    """A product record stored in the database."""
    id: int
    name: str
    site: str
    url: str
    is_active: bool = True
    added_date: datetime


class PriceSnapshot(BaseModel):
    """A single price/stock observation for a product."""
    id: Optional[int] = None
    product_id: int
    price: float
    currency: str = "GBP"
    stock_status: StockStatus
    scraped_at: datetime = Field(default_factory=datetime.now)


class AlertConfig(BaseModel):
    """Alert configuration for a tracked product."""
    product_id: int
    threshold_percent: float = 5.0
    alert_on_stock_change: bool = True
    last_alert_sent: Optional[datetime] = None
