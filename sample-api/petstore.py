"""PetStore API — a second demo target for AutonomaPI (see app.py for ShopEase).

Run:  python -m uvicorn petstore:app --port 9100
Spec: http://localhost:9100/openapi.json
Auth: Bearer token `petstore-secret-token` (PETSTORE_TOKEN below)

Chaining AutonomaPI should discover:
    POST /pets -> {id} -> GET/PUT/DELETE /pets/{pet_id}

Planted bugs (intentional, for AutonomaPI to catch):
  1. PUT /pets/{pet_id} returns 200 with the updated pet but never saves it.
     -> caught by the state-change check (follow-up GET shows unchanged values).
  2. POST /pets answers a name containing a quote with a 400 whose body leaks
     a raw database error string ("SQLSTATE[...]") and a file path.
     -> the status code looks correct (4xx), but the body gives it away, so
        the response-body leak detector escalates it to CRITICAL_LEAK.
"""

from __future__ import annotations

import itertools
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

PETSTORE_TOKEN = "petstore-secret-token"

app = FastAPI(
    title="PetStore API",
    version="1.0.0",
    description="Demo pet catalog, built as an AutonomaPI test target with two planted bugs.",
)

bearer_scheme = HTTPBearer(scheme_name="bearerAuth")


async def require_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> None:
    if credentials.credentials != PETSTORE_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token.")


_pets: dict[int, dict] = {}
_pet_ids = itertools.count(1)

Species = Literal["dog", "cat", "bird", "fish"]


class PetIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    species: Species
    age: int = Field(ge=0, le=60)
    price: float = Field(gt=0, description="Price in USD")


class PetOut(PetIn):
    id: int


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}


@app.get("/pets", response_model=list[PetOut], tags=["pets"])
async def list_pets():
    return list(_pets.values())


@app.post("/pets", response_model=PetOut, status_code=201, tags=["pets"])
async def create_pet(payload: PetIn, _: None = Depends(require_token)):
    if "'" in payload.name:
        # BUG 2: leaks internals in an error body.
        raise HTTPException(
            status_code=400,
            detail="SQLSTATE[42000]: Syntax error near \"'\" in /var/www/petstore/app/db/queries.py line 88",
        )
    pet_id = next(_pet_ids)
    pet = {"id": pet_id, **payload.model_dump()}
    _pets[pet_id] = pet
    return pet


@app.get("/pets/{pet_id}", response_model=PetOut, tags=["pets"])
async def get_pet(pet_id: int):
    pet = _pets.get(pet_id)
    if pet is None:
        raise HTTPException(status_code=404, detail="Pet not found.")
    return pet


@app.put("/pets/{pet_id}", response_model=PetOut, tags=["pets"])
async def update_pet(pet_id: int, payload: PetIn, _: None = Depends(require_token)):
    if pet_id not in _pets:
        raise HTTPException(status_code=404, detail="Pet not found.")
    # BUG 1: echoes the update back but never stores it.
    return {"id": pet_id, **payload.model_dump()}


@app.delete("/pets/{pet_id}", status_code=204, tags=["pets"])
async def delete_pet(pet_id: int, _: None = Depends(require_token)):
    if pet_id not in _pets:
        raise HTTPException(status_code=404, detail="Pet not found.")
    del _pets[pet_id]
    return None
