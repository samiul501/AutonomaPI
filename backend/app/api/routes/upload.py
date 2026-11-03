"""Spec ingestion: Swagger/OpenAPI by URL, file upload, or a hand-described
batch of endpoints (no spec document at all — see "/quick").

On success, returns the parsed spec plus the `auth_fields` the frontend's
configuration pane should render (see AuthDetector.required_ui_fields) —
public endpoints never surface a credential prompt.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.agent.auth_detector import AuthDetector
from app.agent.schema_inference import infer_schema_from_example
from app.agent.spec_parser import SpecParseError, SpecParser
from app.schemas.openapi_models import (
    EndpointSpec,
    HttpMethod,
    ParameterSpec,
    ParsedSpec,
    SecurityScheme,
    SecuritySchemeType,
)
from app.state import SPEC_STORE

router = APIRouter(prefix="/api/specs", tags=["specs"])

QUICK_AUTH_SCHEME = "quickAuth"
_PATH_PARAM_PATTERN = re.compile(r"\{([^{}]+)\}")


class SpecFromUrl(BaseModel):
    url: str


class QuickEndpointItem(BaseModel):
    method: Optional[str] = None  # None / "auto" -> detect via OPTIONS
    url: str
    body_example: Optional[Any] = None
    public: bool = False  # True -> this one doesn't need the shared token, skip auth-bypass scoring for it


class QuickBatchRequest(BaseModel):
    token: Optional[str] = None  # shared across every endpoint in the batch
    endpoints: list[QuickEndpointItem]


def _register(parsed):
    spec_id = str(uuid.uuid4())
    SPEC_STORE[spec_id] = parsed
    return {
        "spec_id": spec_id,
        "spec": parsed.model_dump(mode="json"),
        "auth_fields": AuthDetector(parsed).required_ui_fields(),
    }


@router.post("/from-url")
async def ingest_from_url(payload: SpecFromUrl):
    try:
        parser = await SpecParser.from_url(payload.url)
        parsed = parser.parse()
    except SpecParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _register(parsed)


@router.post("/from-file")
async def ingest_from_file(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith((".json", ".yaml", ".yml")):
        raise HTTPException(
            status_code=415,
            detail="Only JSON/YAML OpenAPI documents are supported today; PDF/Markdown ingestion is on the roadmap.",
        )

    raw = (await file.read()).decode("utf-8", errors="ignore")
    try:
        parser = SpecParser.from_text(raw, filename=file.filename)
        parsed = parser.parse()
    except SpecParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _register(parsed)


async def _detect_method(url: str, has_body: bool) -> tuple[str, bool]:
    """Asks the server itself which methods it supports on this URL via an
    OPTIONS preflight, rather than guessing from the URL text (which carries
    no real information about the method).

    Some frameworks (Starlette/FastAPI among them, confirmed by hand: a path
    with GET, PUT, and DELETE routes registered separately still reports
    only `Allow: GET` on an OPTIONS request — always the first-registered
    route, not the full set) don't aggregate every method onto that one path
    the way a fully spec-compliant router would. That makes a single-method
    answer worthless as confirmation: it can just as easily be masking a PUT
    or DELETE as reporting the real, only method — there's no way to tell
    from the response alone, and treating a lucky-looking match (e.g. GET
    reported, no body given) as "confirmed" would silently present a coin
    flip as verified fact. Only a multi-method answer is trusted, since that
    can only come from a router that genuinely aggregates correctly.
    Returns (method, confirmed) — confirmed=False means this is a fallback
    guess and the caller must surface that honestly rather than as verified.
    """
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            response = await client.options(url)
        allowed = [m.strip().upper() for m in response.headers.get("allow", "").split(",") if m.strip()]
        allowed = [m for m in allowed if m not in ("OPTIONS", "HEAD")]

        if len(allowed) > 1:
            preference = ["POST", "PUT", "PATCH"] if has_body else ["GET", "DELETE", "PUT", "PATCH", "POST"]
            for method in preference:
                if method in allowed:
                    return method, True
            return allowed[0], True
    except httpx.HTTPError:
        pass
    return ("POST" if has_body else "GET"), False


def _extract_path_parameters(url: str) -> list[ParameterSpec]:
    return [
        ParameterSpec(name=name, location="path", required=True, schema={"type": "string"})
        for name in _PATH_PARAM_PATTERN.findall(url)
    ]


@router.post("/quick")
async def ingest_quick_batch(payload: QuickBatchRequest):
    """Builds a spec out of hand-described endpoints — no Swagger/OpenAPI
    document at all. Each item's full absolute URL is stored as-is (not
    split into base_url + path), so a batch can even span multiple hosts;
    everything downstream — dependency chaining, fuzzing, auth checks —
    runs unmodified because it only ever sees a normal `ParsedSpec`.
    """
    if not payload.endpoints:
        raise HTTPException(status_code=422, detail="Add at least one endpoint.")

    security_schemes: dict[str, SecurityScheme] = {}
    if payload.token:
        security_schemes[QUICK_AUTH_SCHEME] = SecurityScheme(
            name=QUICK_AUTH_SCHEME, type=SecuritySchemeType.HTTP_BEARER, scheme="bearer"
        )

    endpoints: list[EndpointSpec] = []
    method_detection: list[dict[str, Any]] = []
    for index, item in enumerate(payload.endpoints):
        parts = urlsplit(item.url)
        if not parts.scheme or not parts.netloc:
            raise HTTPException(status_code=422, detail=f"URL must be absolute (include https://...): {item.url}")

        has_body = item.body_example is not None
        if item.method and item.method.lower() != "auto":
            try:
                method = HttpMethod(item.method.lower())
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"Unsupported HTTP method: {item.method}") from exc
            confirmed = True
        else:
            detected, confirmed = await _detect_method(item.url, has_body)
            method = HttpMethod(detected.lower())

        request_body_schema = None
        if has_body:
            request_body_schema = infer_schema_from_example(item.body_example)
            # A hand-typed example is, by definition, a real working request —
            # keep it as the literal positive case (PayloadGenerator already
            # prefers schema["example"] verbatim) rather than re-randomizing
            # fields whose real constraints (an enum, a regex) inference from
            # one sample value can't know about.
            request_body_schema["example"] = item.body_example

        endpoints.append(
            EndpointSpec(
                operation_id=f"quick_{index}_{method.value}",
                path=item.url,
                method=method,
                parameters=_extract_path_parameters(item.url),
                request_body_schema=request_body_schema,
                request_body_required=has_body,
                security=[QUICK_AUTH_SCHEME] if (payload.token and not item.public) else [],
                resource_name=SpecParser._infer_resource_name(item.url),
            )
        )
        method_detection.append({"url": item.url, "method": method.value.upper(), "confirmed_by_server": confirmed})

    parsed = ParsedSpec(
        title="Quick Endpoint Test",
        version="1.0.0",
        base_url=None,
        security_schemes=security_schemes,
        endpoints=endpoints,
    )

    result = _register(parsed)
    result["method_detection"] = method_detection
    return result
