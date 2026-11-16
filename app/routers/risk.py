"""Risk, öncelik sıralaması, panel, dışa aktarım ve sözlük uçları."""
from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Mapping
from dataclasses import fields
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import DAMAGE_TYPES, DEFAULT_PARAMS, MASONRY_TYPOLOGIES, RISK_CLASSES
from app.database import get_db
from app.routers.structures import get_component, get_structure
from app.services import assessment

router = APIRouter(tags=["Risk"])

MAX_HISTORY_POINTS = 500


@router.get("/components/{component_id}/risk", response_model=schemas.RiskOut)
def read_risk(
    component: models.Component = Depends(get_component),
    as_of: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    as_of = as_of or datetime.now()
    result, explanation = assessment.compute(db, component, as_of)
    return assessment.to_dict(component.id, as_of, result, explanation)


@router.get("/components/{component_id}/risk/history", response_model=list[schemas.RiskOut])
def read_risk_history(
    component: models.Component = Depends(get_component),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    step_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Ham kayıtlardan, güncel parametrelerle yeniden hesaplanan risk zaman serisi."""
    end = end or datetime.now()
    start = start or end - timedelta(days=365)
    if start > end:
        raise HTTPException(status_code=422, detail="Başlangıç tarihi bitişten sonra olamaz.")
    if (end - start).days / step_days > MAX_HISTORY_POINTS:
        raise HTTPException(status_code=422, detail="Aralık çok geniş; adımı büyütün.")

    points = []
    moment = end
    while moment >= start:
        points.append(moment)
        moment -= timedelta(days=step_days)
    series = []
    for moment in reversed(points):
        result, explanation = assessment.compute(db, component, moment)
        series.append(assessment.to_dict(component.id, moment, result, explanation))
    return series


@router.get("/priorities", response_model=list[schemas.PriorityItem])
def all_priorities(db: Session = Depends(get_db)):
    components = db.scalars(select(models.Component)).all()
    return assessment.priorities(db, list(components))


@router.get("/structures/{structure_id}/priorities", response_model=list[schemas.PriorityItem])
def structure_priorities(structure: models.Structure = Depends(get_structure), db: Session = Depends(get_db)):
    return assessment.priorities(db, structure.components)


@router.get("/structures/{structure_id}/dashboard", response_model=schemas.Dashboard)
def dashboard(structure: models.Structure = Depends(get_structure), db: Session = Depends(get_db)):
    now = datetime.now()
    items = assessment.priorities(db, structure.components, now)
    counts = Counter(item["risk_class"] for item in items)
    return {
        "structure": structure,
        "as_of": now,
        "component_count": len(items),
        "class_counts": {name: counts.get(name, 0) for name, _ in RISK_CLASSES},
        "active_damage_count": sum(
            len(assessment.damage_inputs(c, now)) for c in structure.components
        ),
        "pending_seismic_inspections": sum(i["pending_seismic_inspection"] for i in items),
        "priorities": items,
    }


@router.get("/structures/{structure_id}/export")
def export_structure(
    structure: models.Structure = Depends(get_structure),
    format: Literal["json", "csv"] = "json",
    db: Session = Depends(get_db),
):
    """Paydaşlarla paylaşım için yapı verisi: JSON (tam döküm) veya CSV (öncelik tablosu)."""
    items = assessment.priorities(db, structure.components)
    if format == "csv":
        columns = ["rank", "component_name", "risk_class", "r", "r_chronic", "s", "d",
                   "pending_seismic_inspection", "recommendation"]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            writer.writerow({k: round(v, 2) if isinstance(v, float) else v for k, v in item.items()})
        return Response(
            content=buffer.getvalue().encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="yapi_{structure.id}_oncelikler.csv"'},
        )

    def dump(schema, rows):
        return [schema.model_validate(row).model_dump(mode="json") for row in rows]

    return {
        "exported_at": datetime.now().isoformat(),
        "params_version": DEFAULT_PARAMS.version,
        "structure": schemas.StructureOut.model_validate(structure).model_dump(mode="json"),
        "components": [
            {
                **schemas.ComponentOut.model_validate(c).model_dump(mode="json"),
                "damages": dump(schemas.DamageOut, c.damages),
                "maintenance": dump(schemas.MaintenanceOut, c.maintenance_records),
                "measurement_count": len(c.measurements),
            }
            for c in structure.components
        ],
        "seismic_events": dump(schemas.SeismicEventOut, structure.seismic_events),
        "priorities": items,
    }


# ---------------------------------------------------------------- sözlükler


@router.get("/meta/damage-types", tags=["Sözlükler"])
def damage_types():
    return [{"code": code, "name": name, "weight": weight} for code, (name, weight) in DAMAGE_TYPES.items()]


@router.get("/meta/masonry-typologies", tags=["Sözlükler"])
def masonry_typologies():
    return [{"code": code, "name": name, "vulnerability": v} for code, (name, v) in MASONRY_TYPOLOGIES.items()]


@router.get("/meta/parameters", tags=["Sözlükler"])
def parameters():
    params = {}
    for f in fields(DEFAULT_PARAMS):
        value = getattr(DEFAULT_PARAMS, f.name)
        params[f.name] = dict(value) if isinstance(value, Mapping) else value
    params["risk_classes"] = [{"name": name, "lower_bound": lower} for name, lower in RISK_CLASSES]
    return params
