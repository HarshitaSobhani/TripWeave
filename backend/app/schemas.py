from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .optimizer.hours import parse_hours

Currency = Field(pattern=r"^[A-Z]{3}$", description="ISO 4217 code, upper case")
MAX_TRIP_DAYS = 31


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth
class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORM):
    id: int
    email: str


# ---- catalog
class SourceOut(ORM):
    id: int
    name: str
    url: str | None = None
    license: str | None = None
    attribution: str | None = None


class DestinationOut(ORM):
    id: int
    name: str
    country: str | None = None
    lat: float
    lon: float


class HoursMixin(BaseModel):
    @staticmethod
    def check_hours(v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None:
            try:
                parse_hours(v)
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
        return v


class PlaceIn(HoursMixin):
    destination_id: int
    name: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=60)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    description: str | None = Field(default=None, max_length=4000)
    visit_minutes: int | None = Field(default=None, gt=0, le=1440)
    cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    cost_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    opening_hours: dict[str, Any] | None = None
    opening_hours_source: str | None = Field(default=None, max_length=300)

    @field_validator("opening_hours")
    @classmethod
    def _hours(cls, v):
        return cls.check_hours(v)

    @model_validator(mode="after")
    def _pairs(self):
        if (self.cost is None) != (self.cost_currency is None):
            raise ValueError("cost and cost_currency must be given together")
        if self.opening_hours is not None and not self.opening_hours_source:
            raise ValueError("opening_hours requires opening_hours_source (provenance)")
        return self


class PlaceOut(ORM):
    id: int
    destination_id: int
    owner_id: int | None
    name: str
    category: str
    lat: float
    lon: float
    description: str | None
    source: SourceOut | None
    opening_hours: dict[str, Any] | None
    opening_hours_source: str | None
    opening_hours_verified_at: datetime | None
    cost: Decimal | None
    cost_currency: str | None
    cost_recorded_at: datetime | None
    visit_minutes: int | None


# ---- trips
class PointIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str = Field(default="", max_length=200)


class Accessibility(BaseModel):
    step_free: bool = False
    notes: str | None = Field(default=None, max_length=1000)


class TripIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    destination_id: int
    start_date: date
    end_date: date
    travelers: int = Field(default=1, ge=1, le=50)
    day_start: time = time(9, 0)
    day_end: time = time(18, 0)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    budget: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    travel_mode: Literal["walking", "driving", "cycling"] = "walking"
    transit_buffer_minutes: int = Field(default=15, ge=0, le=240)
    max_daily_minutes: int | None = Field(default=None, gt=0, le=1440)
    max_travel_minutes: int | None = Field(default=None, gt=0, le=1440)
    max_walk_minutes: int | None = Field(default=None, gt=0, le=600)
    accessibility: Accessibility | None = None
    interests: list[str] | None = Field(default=None, max_length=30)
    start_point: PointIn | None = None
    end_point: PointIn | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if (self.end_date - self.start_date).days + 1 > MAX_TRIP_DAYS:
            raise ValueError(f"trips are limited to {MAX_TRIP_DAYS} days")
        if self.day_start >= self.day_end:
            raise ValueError("day_start must be before day_end")
        span = (self.day_end.hour * 60 + self.day_end.minute) - (self.day_start.hour * 60 + self.day_start.minute)
        if self.max_daily_minutes and self.max_daily_minutes > 1440:
            raise ValueError("max_daily_minutes is too large")
        if self.max_travel_minutes and self.max_daily_minutes and self.max_travel_minutes > self.max_daily_minutes:
            raise ValueError("max_travel_minutes cannot exceed max_daily_minutes")
        if self.max_travel_minutes and self.max_travel_minutes > span:
            raise ValueError("max_travel_minutes cannot exceed the daily time window")
        if self.max_walk_minutes and self.max_daily_minutes and self.max_walk_minutes > self.max_daily_minutes:
            raise ValueError("max_walk_minutes cannot exceed max_daily_minutes")
        return self


class CandidateIn(HoursMixin):
    place_id: int
    status: Literal["mandatory", "optional", "excluded"] = "optional"
    interest: int | None = Field(default=None, ge=1, le=5)
    visit_minutes: int | None = Field(default=None, gt=0, le=1440)
    hours_override: dict[str, Any] | None = None
    hours_override_source: str | None = Field(default=None, max_length=300)

    @field_validator("hours_override")
    @classmethod
    def _hours(cls, v):
        return cls.check_hours(v)

    @model_validator(mode="after")
    def _prov(self):
        if self.hours_override is not None and not self.hours_override_source:
            raise ValueError("hours_override requires hours_override_source (provenance)")
        return self


class CandidatePatch(HoursMixin):
    status: Literal["mandatory", "optional", "excluded"] | None = None
    interest: int | None = Field(default=None, ge=1, le=5)
    visit_minutes: int | None = Field(default=None, gt=0, le=1440)
    hours_override: dict[str, Any] | None = None
    hours_override_source: str | None = Field(default=None, max_length=300)

    @field_validator("hours_override")
    @classmethod
    def _hours(cls, v):
        return cls.check_hours(v)


class CandidateOut(ORM):
    id: int
    place_id: int
    status: str
    interest: int
    visit_minutes: int | None
    hours_override: dict[str, Any] | None
    hours_override_source: str | None
    place: PlaceOut


class PinIn(BaseModel):
    place_id: int
    day_index: int = Field(ge=0)


class StopOut(ORM):
    id: int
    place_id: int
    position: int
    visit_minutes: int
    notes: str | None
    origin: str
    locked: bool
    arrive_min: int | None
    start_min: int | None
    end_min: int | None
    wait_min: int | None
    leg_minutes: int | None
    leg_basis: str | None
    leg_distance_m: float | None
    leg_distance_kind: str | None
    warnings: list[str] | None
    place: PlaceOut


class DayOut(ORM):
    id: int
    day_index: int
    date: date
    stops: list[StopOut]


class TripOut(ORM):
    id: int
    name: str
    destination: DestinationOut
    start_date: date
    end_date: date
    travelers: int
    day_start: time
    day_end: time
    currency: str
    budget: Decimal | None
    travel_mode: str
    transit_buffer_minutes: int
    max_daily_minutes: int | None
    max_travel_minutes: int | None
    max_walk_minutes: int | None
    accessibility: dict[str, Any] | None
    interests: list[str] | None
    start_point: dict[str, Any] | None
    end_point: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    days: list[DayOut]
    candidates: list[CandidateOut]
    pins: list[PinIn] = []
    latest_run: dict[str, Any] | None = None


class TripSummary(ORM):
    id: int
    name: str
    start_date: date
    end_date: date
    destination: DestinationOut


class OptimizeIn(BaseModel):
    solver: Literal["auto", "ortools", "fallback"] = "auto"
    replace_manual: bool = False
    confirm_replace_manual: bool = False
    interest_weight: float | None = Field(default=None, ge=0, le=100_000)
    balance_weight: float | None = Field(default=None, ge=0, le=100_000)
    preview: bool = False


class StopCreate(BaseModel):
    place_id: int
    day_index: int = Field(ge=0)
    position: int | None = Field(default=None, ge=0)
    visit_minutes: int | None = Field(default=None, gt=0, le=1440)
    notes: str | None = Field(default=None, max_length=2000)


class StopPatch(BaseModel):
    day_index: int | None = Field(default=None, ge=0)
    position: int | None = Field(default=None, ge=0)
    visit_minutes: int | None = Field(default=None, gt=0, le=1440)
    notes: str | None = Field(default=None, max_length=2000)
    locked: bool | None = None


class ExpenseIn(BaseModel):
    category: Literal["food", "transport", "admission", "accommodation", "other"]
    description: str | None = Field(default=None, max_length=300)
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    day_index: int | None = Field(default=None, ge=0)


class ExpenseOut(ORM):
    id: int
    category: str
    description: str | None
    amount: Decimal
    currency: str
    day_index: int | None
