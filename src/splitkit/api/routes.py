"""HTTP routes. Admin routes need X-API-Key; ingest routes are public and rate-limited."""

from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from splitkit.analysis import ExperimentAnalysis
from splitkit.api.envelope import ApiError, finite, ok
from splitkit.api.repository import ConflictError, ExperimentRepository, NotFoundError
from splitkit.api.schemas import AssignRequest, EventBatch, ExperimentCreate, ExposureBatch, StatusUpdate
from splitkit.assignment import Variant, assign
from splitkit.timeline import evenly_spaced

router = APIRouter()
_api_key = APIKeyHeader(name="X-API-Key", auto_error=False)


def repo(request: Request) -> ExperimentRepository:
    return request.app.state.repo


def require_admin(request: Request, key: str | None = Security(_api_key)) -> None:
    expected = request.app.state.settings.admin_key
    if not key or not hmac.compare_digest(key.encode(), expected.encode()):
        raise ApiError(401, "invalid or missing API key")


def _lookup(r: ExperimentRepository, key: str):
    try:
        return r.get_required(key)
    except NotFoundError as exc:
        raise ApiError(404, str(exc)) from exc


@router.get("/health")
def health(r: ExperimentRepository = Depends(repo)) -> JSONResponse:
    try:
        r.ping()
    except Exception as exc:  # report, don't crash the probe
        raise ApiError(503, "database unavailable") from exc
    return ok({"status": "ok", "database": "ok"})


# ---- admin ---------------------------------------------------------------

@router.post("/v1/experiments", dependencies=[Depends(require_admin)])
def create_experiment(body: ExperimentCreate, r: ExperimentRepository = Depends(repo)) -> JSONResponse:
    variants = tuple(Variant(v.name, v.weight) for v in body.variants)
    salt = body.salt or secrets.token_hex(12)
    try:
        record = r.create(body.key, salt, variants, body.metrics)
    except ConflictError as exc:
        raise ApiError(409, str(exc)) from exc
    return ok(record.admin_view(), status=201)


@router.get("/v1/experiments", dependencies=[Depends(require_admin)])
def list_experiments(r: ExperimentRepository = Depends(repo)) -> JSONResponse:
    return ok([rec.admin_view() for rec in r.list_all()])


@router.get("/v1/experiments/{key}", dependencies=[Depends(require_admin)])
def get_experiment(key: str, r: ExperimentRepository = Depends(repo)) -> JSONResponse:
    return ok(_lookup(r, key).admin_view())


@router.post("/v1/experiments/{key}/status", dependencies=[Depends(require_admin)])
def set_status(key: str, body: StatusUpdate, r: ExperimentRepository = Depends(repo)) -> JSONResponse:
    try:
        return ok(r.set_status(key, body.status).admin_view())
    except NotFoundError as exc:
        raise ApiError(404, str(exc)) from exc
    except ConflictError as exc:
        raise ApiError(409, str(exc)) from exc


def _serialize(report: ExperimentAnalysis) -> dict[str, Any]:
    return {
        "experiment_key": report.experiment_key,
        "control": report.control,
        "treatment": report.treatment,
        "counts": report.counts,
        "srm": {"p_value": report.srm.p_value, "mismatch": report.srm.mismatch, "expected": list(report.srm.expected)},
        "blocked": report.blocked,
        "metrics": [
            {
                "metric": m.metric,
                "type": m.type,
                "mean_a": finite(m.result.mean_a),
                "mean_b": finite(m.result.mean_b),
                "abs_lift": finite(m.result.abs_lift),
                "rel_lift": finite(m.result.rel_lift),
                "ci": [finite(m.result.ci_low), finite(m.result.ci_high)],
                "p_value": m.result.p_value,
                "adjusted_p": m.adjusted_p,
                "significant": m.significant,
                "sql": m.sql,
            }
            for m in report.metrics
        ],
    }


@router.get("/v1/experiments/{key}/results", dependencies=[Depends(require_admin)])
def results(
    key: str, alpha: float = Query(0.05, gt=0, lt=0.5), r: ExperimentRepository = Depends(repo)
) -> JSONResponse:
    record = _lookup(r, key)
    try:
        report = r.analyze(record, alpha)
    except ValueError as exc:
        raise ApiError(409, f"not enough data to analyze yet: {exc}") from exc
    return ok(_serialize(report))


@router.get("/v1/experiments/{key}/timeline", dependencies=[Depends(require_admin)])
def timeline(
    key: str,
    metric: str | None = Query(None, max_length=64),
    points: int = Query(12, ge=2, le=60),
    r: ExperimentRepository = Depends(repo),
) -> JSONResponse:
    record = _lookup(r, key)
    spec = next((m for m in record.metrics if metric is None or m.name == metric), None)
    if spec is None:
        raise ApiError(404, f"metric '{metric}' not found on experiment '{key}'")
    start = r.first_exposure(key)
    end = datetime.now(UTC).replace(tzinfo=None)
    if start is None or end <= start:
        raise ApiError(409, "not enough data to analyze yet: no exposures recorded")
    series = r.timeline(record, spec, evenly_spaced(start, end, points))
    return ok({
        "metric": spec.name,
        "type": spec.type,
        "points": [
            {
                "as_of": p.as_of.isoformat(),
                "n_control": p.n_control,
                "n_treatment": p.n_treatment,
                "mean_a": finite(p.mean_a),
                "mean_b": finite(p.mean_b),
                "abs_lift": finite(p.abs_lift),
                "ci_low": finite(p.ci_low),
                "ci_high": finite(p.ci_high),
                "p_value": p.p_value,
                "always_valid_p": p.always_valid_p,
            }
            for p in series
        ],
    })


# ---- public (SDK) --------------------------------------------------------

@router.get("/v1/experiments/{key}/config")
def experiment_config(key: str, r: ExperimentRepository = Depends(repo)) -> JSONResponse:
    return ok(_lookup(r, key).config())


@router.post("/v1/assign")
def assign_user(body: AssignRequest, r: ExperimentRepository = Depends(repo)) -> JSONResponse:
    record = _lookup(r, body.experiment_key)
    if record.status != "running":
        return ok({"variant": None, "new_exposure": False})
    variant = assign(record.variants, record.salt, body.user_id)
    inserted = r.insert_exposures([(record.key, body.user_id, variant)])
    return ok({"variant": variant, "new_exposure": inserted == 1})


@router.post("/v1/exposures")
def record_exposures(body: ExposureBatch, r: ExperimentRepository = Depends(repo)) -> JSONResponse:
    """Accept only exposures whose variant matches the hash; clients cannot pick arms."""
    records = r.get_many([e.experiment_key for e in body.exposures])
    valid = [
        (e.experiment_key, e.user_id, e.variant)
        for e in body.exposures
        if (rec := records.get(e.experiment_key)) is not None
        and rec.status == "running"
        and assign(rec.variants, rec.salt, e.user_id) == e.variant
    ]
    inserted = r.insert_exposures(valid)
    return ok({
        "accepted": inserted,
        "duplicates": len(valid) - inserted,
        "rejected": len(body.exposures) - len(valid),
    })


@router.post("/v1/events")
def record_events(body: EventBatch, r: ExperimentRepository = Depends(repo)) -> JSONResponse:
    rows = [(e.event_id, e.user_id, e.event_name, e.value, e.ts) for e in body.events]
    inserted = r.insert_events(rows)
    return ok({"accepted": inserted, "duplicates": len(rows) - inserted})
