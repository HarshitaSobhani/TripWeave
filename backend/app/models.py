"""Normalized relational model. Ownership: trips (and children) belong to a user."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

PKType = BigInteger().with_variant(Integer, "sqlite")


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceMeta(Base):
    """Provenance for catalog data."""

    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    url: Mapped[str | None] = mapped_column(String(500))
    license: Mapped[str | None] = mapped_column(String(200))
    attribution: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Destination(Base):
    __tablename__ = "destinations"
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    country: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    timezone: Mapped[str | None] = mapped_column(String(64))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"))


class Place(Base):
    __tablename__ = "places"
    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180", name="ck_place_coords"),
        CheckConstraint("visit_minutes IS NULL OR visit_minutes > 0", name="ck_place_minutes"),
        CheckConstraint("cost IS NULL OR cost >= 0", name="ck_place_cost"),
        Index("ix_places_dest_cat", "destination_id", "category"),
        Index("ix_places_coords", "lat", "lon"),
    )
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    destination_id: Mapped[int] = mapped_column(ForeignKey("destinations.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(60))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"))
    opening_hours: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    opening_hours_source: Mapped[str | None] = mapped_column(String(300))
    opening_hours_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    cost_currency: Mapped[str | None] = mapped_column(String(3))
    cost_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    visit_minutes: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[SourceMeta | None] = relationship()


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_trip_dates"),
        CheckConstraint("travelers >= 1", name="ck_trip_travelers"),
        CheckConstraint("day_start < day_end", name="ck_trip_window"),
    )
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    destination_id: Mapped[int] = mapped_column(ForeignKey("destinations.id"))
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    travelers: Mapped[int] = mapped_column(Integer, default=1)
    day_start: Mapped[time] = mapped_column(Time, default=time(9, 0))
    day_end: Mapped[time] = mapped_column(Time, default=time(18, 0))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    travel_mode: Mapped[str] = mapped_column(String(20), default="walking")
    transit_buffer_minutes: Mapped[int] = mapped_column(Integer, default=15)
    max_daily_minutes: Mapped[int | None] = mapped_column(Integer)
    max_travel_minutes: Mapped[int | None] = mapped_column(Integer)
    max_walk_minutes: Mapped[int | None] = mapped_column(Integer)
    accessibility: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    interests: Mapped[list[str] | None] = mapped_column(JSON)
    start_point: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    end_point: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    destination: Mapped[Destination] = relationship()
    days: Mapped[list[TripDay]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="TripDay.day_index"
    )
    candidates: Mapped[list[TripPlace]] = relationship(cascade="all, delete-orphan")
    constraints: Mapped[list[TripConstraint]] = relationship(cascade="all, delete-orphan")
    expenses: Mapped[list[Expense]] = relationship(cascade="all, delete-orphan")
    runs: Mapped[list[OptimizationRun]] = relationship(cascade="all, delete-orphan", order_by="OptimizationRun.id")


class TripPlace(Base):
    """A place in the trip's candidate pool with per-trip choices."""

    __tablename__ = "trip_places"
    __table_args__ = (
        UniqueConstraint("trip_id", "place_id", name="uq_trip_place"),
        CheckConstraint("interest BETWEEN 1 AND 5", name="ck_tp_interest"),
        CheckConstraint("status IN ('mandatory','optional','excluded')", name="ck_tp_status"),
    )
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(12), default="optional")
    interest: Mapped[int] = mapped_column(Integer, default=3)
    visit_minutes: Mapped[int | None] = mapped_column(Integer)
    hours_override: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    hours_override_source: Mapped[str | None] = mapped_column(String(300))
    place: Mapped[Place] = relationship()


class TripConstraint(Base):
    """Extra user constraints. kind='pin_day' -> {place_id, day_index}."""

    __tablename__ = "trip_constraints"
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    value: Mapped[dict[str, Any]] = mapped_column(JSON)


class TripDay(Base):
    __tablename__ = "trip_days"
    __table_args__ = (UniqueConstraint("trip_id", "day_index", name="uq_trip_day"),)
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    day_index: Mapped[int] = mapped_column(Integer)
    date: Mapped[date] = mapped_column(Date)
    trip: Mapped[Trip] = relationship(back_populates="days")
    stops: Mapped[list[Stop]] = relationship(
        back_populates="day", cascade="all, delete-orphan", order_by="Stop.position"
    )


class Stop(Base):
    __tablename__ = "stops"
    __table_args__ = (
        UniqueConstraint("trip_id", "place_id", name="uq_stop_trip_place"),
        CheckConstraint("visit_minutes > 0", name="ck_stop_minutes"),
        CheckConstraint("origin IN ('optimized','manual')", name="ck_stop_origin"),
        Index("ix_stops_day_pos", "trip_day_id", "position"),
    )
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    trip_day_id: Mapped[int] = mapped_column(ForeignKey("trip_days.id", ondelete="CASCADE"))
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    visit_minutes: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(12), default="optimized")
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    arrive_min: Mapped[int | None] = mapped_column(Integer)
    start_min: Mapped[int | None] = mapped_column(Integer)
    end_min: Mapped[int | None] = mapped_column(Integer)
    wait_min: Mapped[int | None] = mapped_column(Integer)
    leg_minutes: Mapped[int | None] = mapped_column(Integer)
    leg_basis: Mapped[str | None] = mapped_column(String(16))
    leg_distance_m: Mapped[float | None] = mapped_column(Float)
    leg_distance_kind: Mapped[str | None] = mapped_column(String(32))
    warnings: Mapped[list[str] | None] = mapped_column(JSON)
    day: Mapped[TripDay] = relationship(back_populates="stops")
    place: Mapped[Place] = relationship()


class OptimizationRun(Base):
    __tablename__ = "optimization_runs"
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(16), default="optimize")  # optimize | reschedule
    status: Mapped[str] = mapped_column(String(16))
    solver: Mapped[str] = mapped_column(String(16))
    matrix_kind: Mapped[str] = mapped_column(String(32))
    matrix_provider: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    legs: Mapped[list[RouteLeg]] = relationship(cascade="all, delete-orphan")


class RouteLeg(Base):
    """Saved travel data between consecutive stops of a run (provenance included)."""

    __tablename__ = "route_legs"
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("optimization_runs.id", ondelete="CASCADE"), index=True)
    day_index: Mapped[int] = mapped_column(Integer)
    from_place_id: Mapped[int | None] = mapped_column(ForeignKey("places.id", ondelete="SET NULL"))
    to_place_id: Mapped[int | None] = mapped_column(ForeignKey("places.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(20))
    duration_s: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_expense_amount"),
        CheckConstraint("category IN ('food','transport','admission','accommodation','other')", name="ck_expense_cat"),
    )
    id: Mapped[int] = mapped_column(PKType, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(String(300))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    day_index: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
