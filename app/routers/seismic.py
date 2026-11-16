"""Deprem kayıtları ve deprem sonrası denetim sırası."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import DEFAULT_PARAMS
from app.database import get_db
from app.routers.structures import get_or_404, get_structure
from app.services import assessment, risk_engine
from app.services.seismic import ComponentSeismicInput, inspection_queue

router = APIRouter(tags=["Deprem"])


def _flag_out(flag: models.SeismicFlag) -> dict:
    return {
        "id": flag.id,
        "event_id": flag.event_id,
        "component_id": flag.component_id,
        "component_name": flag.component.name,
        "expected_mu_d": flag.expected_mu_d,
        "status": flag.status,
        "resolved_at": flag.resolved_at,
        "note": flag.note,
    }


def _queue(event: models.SeismicEvent) -> list[dict]:
    flags = sorted(event.flags, key=lambda f: (-f.expected_mu_d, f.component_id))
    return [_flag_out(f) for f in flags]


@router.get("/structures/{structure_id}/seismic-events", response_model=list[schemas.SeismicEventOut])
def list_events(structure: models.Structure = Depends(get_structure)):
    return sorted(structure.seismic_events, key=lambda e: e.occurred_at, reverse=True)


@router.post("/structures/{structure_id}/seismic-events", response_model=schemas.SeismicEventResult, status_code=201)
def create_event(
    body: schemas.SeismicEventIn,
    structure: models.Structure = Depends(get_structure),
    db: Session = Depends(get_db),
):
    """Depremi kaydeder ve her bileşen için beklenen hasarı hesaplar.

    Beklenen hasar bir tahmindir; gerçek hasar denetimden sonra hasar kaydı olarak girilir.
    """
    event = models.SeismicEvent(structure_id=structure.id, **body.model_dump())
    db.add(event)

    inputs = [
        ComponentSeismicInput(
            component_id=c.id,
            base_vulnerability=DEFAULT_PARAMS.typology_vulnerability[c.masonry_typology],
            damage_score=risk_engine.damage_score(assessment.damage_inputs(c, body.occurred_at)),
        )
        for c in structure.components
    ]
    for item in inspection_queue(inputs, body.intensity):
        event.flags.append(
            models.SeismicFlag(
                component_id=item.component_id,
                expected_mu_d=item.mu_d,
                status="bekliyor" if item.needs_inspection else "gerekmiyor",
            )
        )
    db.commit()
    return {"event": event, "inspection_queue": _queue(event)}


@router.get("/seismic-events/{event_id}/inspection-queue", response_model=list[schemas.SeismicFlagOut])
def read_queue(event_id: int, db: Session = Depends(get_db)):
    return _queue(get_or_404(db, models.SeismicEvent, event_id, "Deprem kaydı"))


@router.post("/seismic-flags/{flag_id}/resolve", response_model=schemas.SeismicFlagOut)
def resolve_flag(flag_id: int, body: schemas.FlagResolveIn, db: Session = Depends(get_db)):
    """Bileşen denetlendi. Bulunan hasar ayrıca hasar kaydı olarak girilmelidir."""
    flag = get_or_404(db, models.SeismicFlag, flag_id, "Denetim işareti")
    if flag.status == "denetlendi":
        raise HTTPException(status_code=409, detail="Bu işaret zaten kapatılmış.")
    flag.status = "denetlendi"
    flag.resolved_at = datetime.now()
    flag.note = body.note
    db.commit()
    return _flag_out(flag)
