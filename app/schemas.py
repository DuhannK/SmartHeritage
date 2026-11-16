"""Giriş doğrulama ve çıkış şemaları (Pydantic)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.config import DAMAGE_TYPES, MASONRY_TYPOLOGIES

DataSource = Literal["sentetik", "gercek"]
Phase = Literal["tani", "mudahale", "bakim"]
MaintenanceKind = Literal["denetim", "bakim", "restorasyon"]


def _naive_not_future(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    if value > datetime.now() + timedelta(minutes=5):
        raise ValueError("Tarih gelecekte olamaz.")
    return value


def _damage_type(value: str) -> str:
    if value not in DAMAGE_TYPES:
        raise ValueError(f"Bilinmeyen hasar türü. Geçerli değerler: {', '.join(DAMAGE_TYPES)}")
    return value


def _typology(value: str) -> str:
    if value not in MASONRY_TYPOLOGIES:
        raise ValueError(f"Bilinmeyen yığma tipi. Geçerli değerler: {', '.join(MASONRY_TYPOLOGIES)}")
    return value


PastDatetime = Annotated[datetime, AfterValidator(_naive_not_future)]
DamageTypeCode = Annotated[str, AfterValidator(_damage_type)]
Typology = Annotated[str, AfterValidator(_typology)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Severity = Annotated[int, Field(ge=1, le=5)]
Intensity = Annotated[float, Field(ge=1, le=12)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- yapı ve bileşen


class StructureIn(BaseModel):
    name: Name
    location: Optional[str] = Field(None, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    period: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    materials: Optional[str] = None
    scenario_intensity: Optional[Intensity] = None


class StructureOut(ORM, StructureIn):
    id: int
    created_at: datetime


class ComponentIn(BaseModel):
    name: Name
    component_type: Optional[str] = Field(None, max_length=100)
    masonry_typology: Typology = "masif_tas"
    description: Optional[str] = None


class ComponentOut(ORM, ComponentIn):
    id: int
    structure_id: int


# ---------------------------------------------------------------- hasar


class ObservationIn(BaseModel):
    severity: Severity
    observed_at: PastDatetime = Field(default_factory=datetime.now)
    note: Optional[str] = None
    photo_path: Optional[str] = Field(None, max_length=500)
    phase: Phase = "tani"


class ObservationOut(ORM, ObservationIn):
    id: int
    damage_id: int


class DamageIn(ObservationIn):
    """Yeni hasar: hasarın kimliği ve ilk gözlemi birlikte girilir."""

    type_code: DamageTypeCode
    description: Optional[str] = None
    seismic_event_id: Optional[int] = None
    data_source: DataSource = "sentetik"


class DamageUpdate(BaseModel):
    status: Optional[Literal["aktif", "onarildi"]] = None
    repaired_at: Optional[PastDatetime] = None
    description: Optional[str] = None


class DamageOut(ORM):
    id: int
    component_id: int
    type_code: str
    status: str
    repaired_at: Optional[datetime]
    description: Optional[str]
    seismic_event_id: Optional[int]
    data_source: str
    observations: list[ObservationOut]


# ---------------------------------------------------------------- ölçüm ve bakım


class MeasurementIn(BaseModel):
    measured_at: PastDatetime = Field(default_factory=datetime.now)
    temperature_c: Optional[float] = Field(None, ge=-40, le=60)
    humidity_pct: Optional[float] = Field(None, ge=0, le=100)
    source: Optional[str] = Field(None, max_length=100)
    data_source: DataSource = "sentetik"

    @model_validator(mode="after")
    def _at_least_one_value(self):
        if self.temperature_c is None and self.humidity_pct is None:
            raise ValueError("Sıcaklık veya nem değerlerinden en az biri girilmelidir.")
        return self


class MeasurementOut(ORM, MeasurementIn):
    id: int
    component_id: int


class MaintenanceIn(BaseModel):
    performed_at: PastDatetime = Field(default_factory=datetime.now)
    kind: MaintenanceKind = "bakim"
    description: Optional[str] = None
    materials_used: Optional[str] = None
    phase: Phase = "bakim"
    data_source: DataSource = "sentetik"


class MaintenanceOut(ORM, MaintenanceIn):
    id: int
    component_id: int


# ---------------------------------------------------------------- deprem


class SeismicEventIn(BaseModel):
    occurred_at: PastDatetime = Field(default_factory=datetime.now)
    intensity: Intensity
    magnitude: Optional[float] = Field(None, ge=0, le=10)
    description: Optional[str] = None
    data_source: DataSource = "sentetik"


class SeismicEventOut(ORM, SeismicEventIn):
    id: int
    structure_id: int


class SeismicFlagOut(ORM):
    id: int
    event_id: int
    component_id: int
    component_name: str
    expected_mu_d: float
    status: str
    resolved_at: Optional[datetime]
    note: Optional[str]


class SeismicEventResult(BaseModel):
    event: SeismicEventOut
    inspection_queue: list[SeismicFlagOut]


class FlagResolveIn(BaseModel):
    note: Optional[str] = None


# ---------------------------------------------------------------- risk


class RiskOut(BaseModel):
    component_id: int
    as_of: datetime
    d: float
    e: Optional[float]
    t: float
    s: float
    mu_d: Optional[float]
    r_chronic: float
    r_raw: float
    r: float
    risk_class: str
    contributions: dict
    e_parts: dict
    t_parts: dict
    flags: list[str]
    explanation: str
    params_version: str


class PriorityItem(BaseModel):
    rank: int
    structure_id: int
    structure_name: str
    component_id: int
    component_name: str
    r: float
    r_raw: float
    r_chronic: float
    s: float
    d: float
    risk_class: str
    pending_seismic_inspection: bool
    recommendation: str


class Dashboard(BaseModel):
    structure: StructureOut
    as_of: datetime
    component_count: int
    class_counts: dict
    active_damage_count: int
    pending_seismic_inspections: int
    priorities: list[PriorityItem]
