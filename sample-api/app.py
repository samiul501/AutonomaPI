"""ShopEase API — a small demo product/order catalog, written specifically to
hand to AutonomaPI as a test target.

FastAPI auto-generates an accurate OpenAPI document for this app from the
route definitions below — that's the point: this file IS the API and its
documentation at once. Run it, then paste http://localhost:9000/openapi.json
into AutonomaPI's "Spec URL" field.

Resource dependency for the chaining engine to discover:
    POST /products  ->  {id}  ->  GET/PUT/DELETE /products/{product_id}
    POST /products  ->  {id}  ->  POST /orders (product_id)  ->  {id}  ->  GET/DELETE /orders/{order_id}

Auth: Bearer token, checked against DEMO_TOKEN below.

Planted bug (intentional, for AutonomaPI to catch):
    DELETE /products/{product_id} is documented as requiring bearerAuth
    (see `openapi_extra` on that route) but the handler never actually
    checks the token — a realistic "declared secure, implemented insecure"
    mistake. AutonomaPI's auth-bypass probe should flag it as a
    CRITICAL_LEAK.
"""

from __future__ import annotations

import itertools
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

DEMO_TOKEN = "shopease-secret-token123"

app = FastAPI(
    title="ShopEase API",
    version="1.2.0",
    description="Demo product & order catalog, built as an AutonomaPI test target.",
)

bearer_scheme = HTTPBearer(scheme_name="bearerAuth")


async def require_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> None:
    if credentials.credentials != DEMO_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token.")


_products: dict[int, dict] = {}
_orders: dict[int, dict] = {}
_product_ids = itertools.count(1)
_order_ids = itertools.count(1)

Category = Literal["electronics", "clothing", "home", "toys"]


class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    price: float = Field(gt=0, description="Price in USD")
    stock: int = Field(ge=0)
    category: Category
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True


class ProductOut(ProductIn):
    id: int


class OrderIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    customer_email: EmailStr


class OrderOut(BaseModel):
    id: int
    product_id: int
    quantity: int
    customer_email: EmailStr
    total_price: float


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}


@app.get("/products", response_model=list[ProductOut], tags=["products"])
async def list_products():
    return list(_products.values())


@app.post("/products", response_model=ProductOut, status_code=201, tags=["products"])
async def create_product(payload: ProductIn, _: None = Depends(require_token)):
    product_id = next(_product_ids)
    product = {"id": product_id, **payload.model_dump()}
    _products[product_id] = product
    return product


@app.get("/products/{product_id}", response_model=ProductOut, tags=["products"])
async def get_product(product_id: int):
    product = _products.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product


@app.put("/products/{product_id}", response_model=ProductOut, tags=["products"])
async def update_product(product_id: int, payload: ProductIn, _: None = Depends(require_token)):
    if product_id not in _products:
        raise HTTPException(status_code=404, detail="Product not found.")
    product = {"id": product_id, **payload.model_dump()}
    _products[product_id] = product
    return product


@app.delete(
    "/products/{product_id}",
    status_code=204,
    tags=["products"],
    # Documented as requiring bearerAuth so AutonomaPI treats this endpoint as
    # protected and runs its auth-bypass probe against it — see module
    # docstring: the handler below never actually checks the token.
    openapi_extra={"security": [{"bearerAuth": []}]},
)
async def delete_product(product_id: int):
    if product_id not in _products:
        raise HTTPException(status_code=404, detail="Product not found.")
    del _products[product_id]
    return None


@app.post("/orders", response_model=OrderOut, status_code=201, tags=["orders"])
async def create_order(payload: OrderIn, _: None = Depends(require_token)):
    product = _products.get(payload.product_id)
    if product is None:
        raise HTTPException(status_code=422, detail="product_id does not reference an existing product.")
    order_id = next(_order_ids)
    order = {
        "id": order_id,
        "product_id": payload.product_id,
        "quantity": payload.quantity,
        "customer_email": payload.customer_email,
        "total_price": round(product["price"] * payload.quantity, 2),
    }
    _orders[order_id] = order
    return order


@app.get("/orders/{order_id}", response_model=OrderOut, tags=["orders"])
async def get_order(order_id: int, _: None = Depends(require_token)):
    order = _orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found.")
    return order


@app.delete("/orders/{order_id}", status_code=204, tags=["orders"])
async def cancel_order(order_id: int, _: None = Depends(require_token)):
    if order_id not in _orders:
        raise HTTPException(status_code=404, detail="Order not found.")
    del _orders[order_id]
    return None
