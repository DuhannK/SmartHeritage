"""Hasar, gözlem, ölçüm ve bakım kayıtları.

Her yazma işleminden sonra bileşenin risk anlık görüntüsü güncellenir.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.structures import get_component, get_or_404
from app.services import assessment

router = APIRouter(tags=["Kayıtlar"])

MAX_BULK = 10_000


def get_damage(damage_id: int, db: Session = Depends(get_db)) -> models.Damage:
    return get_or_404(db, models.Damage, damage_id, "Hasar")


# ---------------------------------------------------------------- hasar


@router.get("/components/{component_id}/damages", response_model=list[schemas.DamageOut])
def list_damages(component: models.Component = Depends(get_component)):
    return component.damages


@router.post("/components/{component_id}/damages", response_model=schemas.DamageOut, status_code=201)
def create_damage(
    body: schemas.DamageIn,
    component: models.Component = Depends(get_component),
    db: Session = Depends(get_db),
):
    if body.seismic_event_id is not None:
        event = get_or_404(db, models.SeismicEvent, body.seismic_event_id, "Deprem kaydı")
        if event.structure_id != component.structure_id:
            raise HTTPException(status_code=422, detail="Deprem kaydı bu bileşenin yapısına ait değil.")
    damage = models.Damage(
        component_id=component.id,
        type_code=body.type_code,
        description=body.description,
        seismic_event_id=body.seismic_event_id,
        data_source=body.data_source,
    )
    damage.observations.append(
        models.DamageObservation(
            observed_at=body.observed_at,
            severity=body.severity,
            note=body.note,
            photo_path=body.photo_path,
            phase=body.phase,
        )
    )
    db.add(damage)
    assessment.snapshot(db, component)
    db.commit()
    return damage


@router.post("/damages/{damage_id}/observations", response_model=schemas.DamageOut, status_code=201)
def add_observation(
    body: schemas.ObservationIn,
    damage: models.Damage = Depends(get_damage),
    db: Session = Depends(get_db),
):
    damage.observations.append(models.DamageObservation(**body.model_dump()))
    assessment.snapshot(db, damage.component)
    db.commit()
    db.refresh(damage)
    return damage


@router.put("/damages/{damage_id}", response_model=schemas.DamageOut)
def update_damage(
    body: schemas.DamageUpdate,
    damage: models.Damage = Depends(get_damage),
    db: Session = Depends(get_db),
):
    if body.description is not None:
        damage.description = body.description
    if body.status == "onarildi":
        damage.status = "onarildi"
        damage.repaired_at = body.repaired_at or datetime.now()
    elif body.status == "aktif":
        damage.status = "aktif"
        damage.repaired_at = None
    assessment.snapshot(db, damage.component)
    db.commit()
    return damage


# ---------------------------------------------------------------- ölçüm


@router.get("/components/{component_id}/measurements", response_model=list[schemas.MeasurementOut])
def list_measurements(
    component: models.Component = Depends(get_component),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(1000, ge=1, le=MAX_BULK),
    db: Session = Depends(get_db),
):
    query = select(models.Measurement).where(models.Measurement.component_id == component.id)
    if start:
        query = query.where(models.Measurement.measured_at >= start)
    if end:
        query = query.where(models.Measurement.measured_at <= end)
    return db.scalars(query.order_by(models.Measurement.measured_at.desc()).limit(limit)).all()


@router.post("/components/{component_id}/measurements", response_model=schemas.MeasurementOut, status_code=201)
def create_measurement(
    body: schemas.MeasurementIn,
    component: models.Component = Depends(get_component),
    db: Session = Depends(get_db),
):
    measurement = models.Measurement(component_id=component.id, **body.model_dump())
    db.add(measurement)
    assessment.snapshot(db, component)
    db.commit()
    return measurement


@router.post("/components/{component_id}/measurements/bulk", status_code=201)
def create_measurements_bulk(
    body: list[schemas.MeasurementIn],
    component: models.Component = Depends(get_component),
    db: Session = Depends(get_db),
):
    """Toplu ölçüm girişi (sensör aktarımı). Tek bir geçersiz satır tüm isteği reddeder."""
    if not body:
        raise HTTPException(status_code=422, detail="En az bir ölçüm gönderilmelidir.")
    if len(body) > MAX_BULK:
        raise HTTPException(status_code=422, detail=f"Bir istekte en fazla {MAX_BULK} ölçüm gönderilebilir.")
    db.add_all(models.Measurement(component_id=component.id, **m.model_dump()) for m in body)
    assessment.snapshot(db, component)
    db.commit()
    return {"created": len(body)}


# ---------------------------------------------------------------- bakım


@router.get("/components/{component_id}/maintenance", response_model=list[schemas.MaintenanceOut])
def list_maintenance(component: models.Component = Depends(get_component)):
    return sorted(component.maintenance_records, key=lambda m: m.performed_at, reverse=True)


@router.post("/components/{component_id}/maintenance", response_model=schemas.MaintenanceOut, status_code=201)
def create_maintenance(
    body: schemas.MaintenanceIn,
    component: models.Component = Depends(get_component),
    db: Session = Depends(get_db),
):
    record = models.MaintenanceRecord(component_id=component.id, **body.model_dump())
    db.add(record)
    assessment.snapshot(db, component)
    db.commit()
    return record
