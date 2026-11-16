"""Veritabanı kayıtlarını risk motoruna bağlayan katman.

Risk motoru (risk_engine, seismic) veritabanını bilmez; bu modül kayıtları okuyup
motorun beklediği sade girdilere çevirir ve sonucu saklar.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import DEFAULT_PARAMS, RiskParams
from app.services import risk_engine
from app.services.explain import RECOMMENDATIONS, build_explanation
from app.services.risk_engine import DamageInput, Reading, RiskResult

DAYS_PER_MONTH = 30.44
MAINTENANCE_KINDS = ("bakim", "restorasyon")  # "denetim" bakım sayılmaz


def damage_inputs(component: models.Component, as_of: datetime) -> list[DamageInput]:
    """`as_of` anında aktif olan hasarlar, her biri o andaki son gözlem şiddetiyle."""
    result = []
    for damage in component.damages:
        if damage.status == "onarildi" and damage.repaired_at and damage.repaired_at <= as_of:
            continue
        seen = [o for o in damage.observations if o.observed_at <= as_of]
        if seen:
            latest = max(seen, key=lambda o: o.observed_at)
            result.append(DamageInput(damage.type_code, latest.severity))
    return result


def _has_history(component: models.Component, at: datetime) -> bool:
    return any(o.observed_at <= at for dmg in component.damages for o in dmg.observations)


def past_damage_score(
    component: models.Component, as_of: datetime, params: RiskParams
) -> Optional[float]:
    past = as_of - timedelta(days=params.trend_window_days)
    if not _has_history(component, past):
        return None
    return risk_engine.damage_score(damage_inputs(component, past), params)


def months_since_maintenance(component: models.Component, as_of: datetime) -> Optional[float]:
    dates = [
        m.performed_at
        for m in component.maintenance_records
        if m.kind in MAINTENANCE_KINDS and m.performed_at <= as_of
    ]
    if not dates:
        return None
    return (as_of - max(dates)).days / DAYS_PER_MONTH


def window_readings(
    db: Session, component_id: int, as_of: datetime, params: RiskParams
) -> list[Reading]:
    start = as_of - timedelta(days=params.env_window_days)
    rows = db.execute(
        select(
            models.Measurement.measured_at,
            models.Measurement.temperature_c,
            models.Measurement.humidity_pct,
        ).where(
            models.Measurement.component_id == component_id,
            models.Measurement.measured_at > start,
            models.Measurement.measured_at <= as_of,
        )
    ).all()
    return [Reading(*row) for row in rows]


def compute(
    db: Session,
    component: models.Component,
    as_of: Optional[datetime] = None,
    params: RiskParams = DEFAULT_PARAMS,
) -> tuple[RiskResult, str]:
    """Bileşenin `as_of` anındaki risk sonucu ve açıklama metni."""
    as_of = as_of or datetime.now()
    result = risk_engine.assess(
        damages=damage_inputs(component, as_of),
        readings=window_readings(db, component.id, as_of, params),
        as_of=as_of,
        d_past=past_damage_score(component, as_of, params),
        months_since_maintenance=months_since_maintenance(component, as_of),
        base_vulnerability=params.typology_vulnerability[component.masonry_typology],
        scenario_intensity=component.structure.scenario_intensity,
        params=params,
    )
    return result, build_explanation(result)


def to_dict(component_id: int, as_of: datetime, result: RiskResult, explanation: str) -> dict:
    return {
        "component_id": component_id,
        "as_of": as_of,
        "d": result.d,
        "e": result.e,
        "t": result.t,
        "s": result.s,
        "mu_d": result.mu_d,
        "r_chronic": result.r_chronic,
        "r_raw": result.r_raw,
        "r": result.r,
        "risk_class": result.risk_class,
        "contributions": result.contributions,
        "e_parts": result.e_parts,
        "t_parts": result.t_parts,
        "flags": list(result.flags),
        "explanation": explanation,
        "params_version": result.params_version,
    }


def snapshot(db: Session, component: models.Component, as_of: Optional[datetime] = None) -> None:
    """Güncel riski hesaplayıp günün kaydı olarak saklar (varsa günceller)."""
    as_of = as_of or datetime.now()
    db.flush()
    db.refresh(component)
    result, explanation = compute(db, component, as_of)
    row = db.execute(
        select(models.RiskAssessment).where(
            models.RiskAssessment.component_id == component.id,
            models.RiskAssessment.assessed_on == as_of.date(),
        )
    ).scalar_one_or_none()
    if row is None:
        row = models.RiskAssessment(component_id=component.id, assessed_on=as_of.date())
        db.add(row)
    row.as_of = as_of
    row.d, row.e, row.t, row.s = result.d, result.e, result.t, result.s
    row.r_chronic, row.r_raw, row.r = result.r_chronic, result.r_raw, result.r
    row.risk_class = result.risk_class
    row.details = {
        "contributions": result.contributions,
        "e_parts": result.e_parts,
        "t_parts": result.t_parts,
        "flags": list(result.flags),
        "mu_d": result.mu_d,
    }
    row.explanation = explanation
    row.params_version = result.params_version


def has_pending_flag(component: models.Component) -> bool:
    return any(f.status == "bekliyor" for f in component.seismic_flags)


def priorities(
    db: Session, components: list[models.Component], as_of: Optional[datetime] = None
) -> list[dict]:
    """Bileşenleri kırpılmamış risk puanına göre büyükten küçüğe sıralar."""
    as_of = as_of or datetime.now()
    items = []
    for component in components:
        result, _ = compute(db, component, as_of)
        items.append(
            {
                "structure_id": component.structure_id,
                "structure_name": component.structure.name,
                "component_id": component.id,
                "component_name": component.name,
                "r": result.r,
                "r_raw": result.r_raw,
                "r_chronic": result.r_chronic,
                "s": result.s,
                "d": result.d,
                "risk_class": result.risk_class,
                "pending_seismic_inspection": has_pending_flag(component),
                "recommendation": RECOMMENDATIONS[result.risk_class],
            }
        )
    items.sort(key=lambda i: (-i["r_raw"], i["component_id"]))
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
    return items
