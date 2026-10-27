from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

EventName = Literal["product_impression", "product_click", "product_view", "search", "add_to_wishlist", "add_to_cart", "purchase", "remove_from_cart"]


class Event(BaseModel):
    event_id: UUID
    timestamp: datetime
    distinct_id: str = Field(min_length=1, max_length=100)
    event_name: EventName
    product_id: str | None = None
    query: str | None = Field(default=None, max_length=200)
    order_id: str | None = Field(default=None, max_length=100)
    source: Literal["website", "simulator"] = "website"
    synthetic: bool = True
    environment: Literal["dev", "staging", "production"] = "dev"
    session_id: str | None = Field(None, max_length=150)
    order_item_id: str | None = Field(None, max_length=150)
    consent: bool = False
    request_id: str | None = Field(None, max_length=150)
    page: Literal["home", "catalog", "search", "product_detail", "cart"] | None = None
    list_id: str | None = Field(None, max_length=150)
    position: int | None = Field(None, ge=1)
    bot: bool = False

    @model_validator(mode="after")
    def validate_event(self):
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must include timezone")
        self.timestamp = self.timestamp.astimezone(timezone.utc)
        if self.event_name == "search":
            if not self.query or not self.query.strip():
                raise ValueError("search requires query")
        elif not self.product_id:
            raise ValueError("product event requires product_id")
        if self.event_name == "purchase" and not self.order_id:
            raise ValueError("purchase requires order_id")
        if not self.synthetic and not self.consent:
            raise ValueError("real analytics requires consent")
        if not self.synthetic and self.source == "simulator":
            raise ValueError("simulator cannot emit real events")
        if self.synthetic and self.environment == "production":
            raise ValueError("synthetic events cannot use production environment")
        if self.event_name == "purchase" and not self.order_item_id:
            if not self.synthetic:
                raise ValueError("real purchase requires order_item_id")
            self.order_item_id = f"{self.order_id}:{self.product_id}"
        return self


class Checkout(BaseModel):
    order_id: UUID
    user_id: str
    product_ids: list[str] = Field(min_length=1, max_length=100)
    session_id: str | None = Field(None, max_length=150)


class ProductVariant(BaseModel):
    sku: str = Field(min_length=1, max_length=16)
    price: int = Field(ge=0, description="Demo USD, whole-dollar units")
    quantity: int = Field(ge=0)


class ProductSpecification(BaseModel):
    specification_name: str = Field(min_length=1, max_length=255)
    specification_value: str = Field(min_length=1)


class Product(BaseModel):
    domain_id: int | None = Field(None, ge=1)
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str
    avg_rating: float | None = Field(None, ge=0, le=5)
    sold_count: int = Field(0, ge=0)
    is_published: bool = True
    category_id: str
    category: str
    brand_id: str
    brand: str
    color: str
    attributes: dict[str, str | int | float | bool]
    variants: list[ProductVariant] = Field(min_length=1)
    specifications: list[ProductSpecification] = Field(min_length=1)
    price: int = Field(ge=0)
    stock: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_projection(self):
        if self.price != self.variants[0].price or self.stock != self.variants[0].quantity:
            raise ValueError("Demo price/stock must match its default SKU")
        if len({v.sku for v in self.variants}) != len(self.variants):
            raise ValueError("Duplicate SKU")
        if len({s.specification_name for s in self.specifications}) != len(self.specifications):
            raise ValueError("Duplicate specification name")
        return self
