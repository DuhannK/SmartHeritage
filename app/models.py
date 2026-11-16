"""Veritabanı tabloları.

Hiyerarşi: Yapı -> Bileşen -> Hasar (-> Gözlem), Ölçüm, Bakım kaydı, Risk kaydı.
Depremler yapıya bağlıdır; her deprem bileşenler için denetim işaretleri üretir.

Ortak alanlar:
  data_source: "sentetik" | "gercek"  (sentetik veri açıkça işaretlenir)
  phase:       "tani" | "mudahale" | "bakim"  (ana makaledeki yaşam döngüsü fazları)
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

CASCADE = "all, delete-orphan"


class Structure(Base):
    __tablename__ = "structures"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    location: Mapped[Optional[str]] = mapped_column(String(200))
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    period: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    materials: Mapped[Optional[str]] = mapped_column(Text)
    scenario_intensity: Mapped[Optional[float]] = mapped_column(Float)  # EMS-98
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    components: Mapped[list["Component"]] = relationship(back_populates="structure", cascade=CASCADE)
    seismic_events: Mapped[list["SeismicEvent"]] = relationship(back_populates="structure", cascade=CASCADE)


class Component(Base):
    __tablename__ = "components"

    id: Mapped[int] = mapped_column(primary_key=True)
    structure_id: Mapped[int] = mapped_column(ForeignKey("structures.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    component_type: Mapped[Optional[str]] = mapped_column(String(100))  # burç, kapı, duvar segmenti...
    masonry_typology: Mapped[str] = mapped_column(String(50), default="masif_tas")
    description: Mapped[Optional[str]] = mapped_column(Text)

    structure: Mapped[Structure] = relationship(back_populates="components")
    damages: Mapped[list["Damage"]] = relationship(back_populates="component", cascade=CASCADE)
    measurements: Mapped[list["Measurement"]] = relationship(back_populates="component", cascade=CASCADE)
    maintenance_records: Mapped[list["MaintenanceRecord"]] = relationship(back_populates="component", cascade=CASCADE)
    risk_assessments: Mapped[list["RiskAssessment"]] = relationship(back_populates="component", cascade=CASCADE)
    seismic_flags: Mapped[list["SeismicFlag"]] = relationship(back_populates="component", cascade=CASCADE)


class Damage(Base):
    """Bir hasarın kimliği. Şiddetin zamanla değişimi DamageObservation'da tutulur."""

    __tablename__ = "damages"

    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), index=True)
    type_code: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="aktif")  # aktif | onarildi
    repaired_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    description: Mapped[Optional[str]] = mapped_column(Text)
    seismic_event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("seismic_events.id", ondelete="SET NULL"))
    data_source: Mapped[str] = mapped_column(String(20), default="sentetik")

    component: Mapped[Component] = relationship(back_populates="damages")
    observations: Mapped[list["DamageObservation"]] = relationship(
        back_populates="damage", cascade=CASCADE, order_by="DamageObservation.observed_at"
    )


class DamageObservation(Base):
    __tablename__ = "damage_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    damage_id: Mapped[int] = mapped_column(ForeignKey("damages.id", ondelete="CASCADE"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    severity: Mapped[int] = mapped_column(Integer)  # 1–5
    note: Mapped[Optional[str]] = mapped_column(Text)
    photo_path: Mapped[Optional[str]] = mapped_column(String(500))
    phase: Mapped[str] = mapped_column(String(20), default="tani")

    damage: Mapped[Damage] = relationship(back_populates="observations")


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), index=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    temperature_c: Mapped[Optional[float]] = mapped_column(Float)
    humidity_pct: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[Optional[str]] = mapped_column(String(100))  # sensör kimliği, ölçüm yöntemi
    data_source: Mapped[str] = mapped_column(String(20), default="sentetik")

    component: Mapped[Component] = relationship(back_populates="measurements")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), index=True)
    performed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    kind: Mapped[str] = mapped_column(String(20), default="bakim")  # denetim | bakim | restorasyon
    description: Mapped[Optional[str]] = mapped_column(Text)
    materials_used: Mapped[Optional[str]] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(String(20), default="bakim")
    data_source: Mapped[str] = mapped_column(String(20), default="sentetik")

    component: Mapped[Component] = relationship(back_populates="maintenance_records")


class SeismicEvent(Base):
    __tablename__ = "seismic_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    structure_id: Mapped[int] = mapped_column(ForeignKey("structures.id", ondelete="CASCADE"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    intensity: Mapped[float] = mapped_column(Float)  # yapının bulunduğu yerdeki şiddet, EMS-98
    magnitude: Mapped[Optional[float]] = mapped_column(Float)  # bilgi amaçlı (Mw)
    description: Mapped[Optional[str]] = mapped_column(Text)
    data_source: Mapped[str] = mapped_column(String(20), default="sentetik")

    structure: Mapped[Structure] = relationship(back_populates="seismic_events")
    flags: Mapped[list["SeismicFlag"]] = relationship(back_populates="event", cascade=CASCADE)


class SeismicFlag(Base):
    """Deprem sonrası bir bileşen için beklenen hasar ve denetim durumu."""

    __tablename__ = "seismic_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("seismic_events.id", ondelete="CASCADE"), index=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), index=True)
    expected_mu_d: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="bekliyor")  # bekliyor | denetlendi | gerekmiyor
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    note: Mapped[Optional[str]] = mapped_column(Text)

    event: Mapped[SeismicEvent] = relationship(back_populates="flags")
    component: Mapped[Component] = relationship(back_populates="seismic_flags")


class RiskAssessment(Base):
    """Risk anlık görüntüsü: bileşen başına günde en fazla bir kayıt."""

    __tablename__ = "risk_assessments"
    __table_args__ = (UniqueConstraint("component_id", "assessed_on"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"), index=True)
    assessed_on: Mapped[date] = mapped_column(Date)
    as_of: Mapped[datetime] = mapped_column(DateTime)
    d: Mapped[float] = mapped_column(Float)
    e: Mapped[Optional[float]] = mapped_column(Float)
    t: Mapped[float] = mapped_column(Float)
    s: Mapped[float] = mapped_column(Float)
    r_chronic: Mapped[float] = mapped_column(Float)
    r_raw: Mapped[float] = mapped_column(Float)
    r: Mapped[float] = mapped_column(Float)
    risk_class: Mapped[str] = mapped_column(String(20))
    details: Mapped[dict] = mapped_column(JSON)  # katkılar, alt puanlar, işaretler
    explanation: Mapped[str] = mapped_column(Text)
    params_version: Mapped[str] = mapped_column(String(20))

    component: Mapped[Component] = relationship(back_populates="risk_assessments")
