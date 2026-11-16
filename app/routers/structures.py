"""Yapı ve bileşen uçları."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(tags=["Yapılar ve bileşenler"])


def get_or_404(db: Session, model, obj_id: int, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} bulunamadı.")
    return obj


def get_structure(structure_id: int, db: Session = Depends(get_db)) -> models.Structure:
    return get_or_404(db, models.Structure, structure_id, "Yapı")


def get_component(component_id: int, db: Session = Depends(get_db)) -> models.Component:
    return get_or_404(db, models.Component, component_id, "Bileşen")


@router.get("/structures", response_model=list[schemas.StructureOut])
def list_structures(db: Session = Depends(get_db)):
    return db.scalars(select(models.Structure).order_by(models.Structure.name)).all()


@router.post("/structures", response_model=schemas.StructureOut, status_code=201)
def create_structure(body: schemas.StructureIn, db: Session = Depends(get_db)):
    structure = models.Structure(**body.model_dump())
    db.add(structure)
    db.commit()
    return structure


@router.get("/structures/{structure_id}", response_model=schemas.StructureOut)
def read_structure(structure: models.Structure = Depends(get_structure)):
    return structure


@router.put("/structures/{structure_id}", response_model=schemas.StructureOut)
def update_structure(
    body: schemas.StructureIn,
    structure: models.Structure = Depends(get_structure),
    db: Session = Depends(get_db),
):
    for key, value in body.model_dump().items():
        setattr(structure, key, value)
    db.commit()
    return structure


@router.delete("/structures/{structure_id}", status_code=204)
def delete_structure(structure: models.Structure = Depends(get_structure), db: Session = Depends(get_db)):
    db.delete(structure)
    db.commit()


@router.get("/structures/{structure_id}/components", response_model=list[schemas.ComponentOut])
def list_components(structure: models.Structure = Depends(get_structure)):
    return structure.components


@router.post("/structures/{structure_id}/components", response_model=schemas.ComponentOut, status_code=201)
def create_component(
    body: schemas.ComponentIn,
    structure: models.Structure = Depends(get_structure),
    db: Session = Depends(get_db),
):
    component = models.Component(structure_id=structure.id, **body.model_dump())
    db.add(component)
    db.commit()
    return component


@router.get("/components/{component_id}", response_model=schemas.ComponentOut)
def read_component(component: models.Component = Depends(get_component)):
    return component


@router.put("/components/{component_id}", response_model=schemas.ComponentOut)
def update_component(
    body: schemas.ComponentIn,
    component: models.Component = Depends(get_component),
    db: Session = Depends(get_db),
):
    for key, value in body.model_dump().items():
        setattr(component, key, value)
    db.commit()
    return component


@router.delete("/components/{component_id}", status_code=204)
def delete_component(component: models.Component = Depends(get_component), db: Session = Depends(get_db)):
    db.delete(component)
    db.commit()
