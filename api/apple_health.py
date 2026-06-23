"""Apple Health sync API for the iOS companion app."""

import datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from database.database import get_session
from database.repositories import HealthRepository


router = APIRouter(prefix="/api/apple-health", tags=["apple-health"])


class ClaimRequest(BaseModel):
    link_code: str = Field(min_length=8)
    device_name: str | None = None
    permissions: list[str] = Field(default_factory=list)


class ClaimResponse(BaseModel):
    sync_token: str
    token_type: str = "bearer"
    provider: str = "apple_health"


class DailySummaryIn(BaseModel):
    summary_date: datetime.date
    steps: int | None = None
    active_energy_kcal: float | None = None
    resting_heart_rate_bpm: float | None = None
    hrv_ms: float | None = None
    sleep_minutes: int | None = None
    workout_minutes: int | None = None
    walking_running_distance_km: float | None = None
    vo2_max: float | None = None
    body_mass_kg: float | None = None


class HealthWorkoutIn(BaseModel):
    external_uuid: str = Field(min_length=1)
    workout_type: str | None = None
    started_at: datetime.datetime
    ended_at: datetime.datetime | None = None
    duration_minutes: float | None = None
    active_energy_kcal: float | None = None
    distance_km: float | None = None


class SyncRequest(BaseModel):
    sync_token: str | None = None
    permissions: list[str] = Field(default_factory=list)
    daily_summaries: list[DailySummaryIn] = Field(default_factory=list)
    workouts: list[HealthWorkoutIn] = Field(default_factory=list)


class SyncResponse(BaseModel):
    synced: bool
    daily_summaries: int
    workouts: int


def _extract_sync_token(authorization: str | None, body_token: str | None) -> str:
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    if body_token:
        return body_token.strip()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing bearer sync token",
    )


@router.post("/claim", response_model=ClaimResponse)
async def claim_apple_health_link(payload: ClaimRequest) -> ClaimResponse:
    """Exchange a short-lived pairing code for a long-lived sync token."""
    session = await get_session()
    try:
        health_repo = HealthRepository(session)
        connection, sync_token = await health_repo.claim_link_code(
            payload.link_code,
            device_name=payload.device_name,
            permissions=payload.permissions,
        )
        if not connection or not sync_token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid or expired Apple Health link code",
            )
        await session.commit()
        return ClaimResponse(sync_token=sync_token)
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@router.post("/sync", response_model=SyncResponse)
async def sync_apple_health(
    payload: SyncRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> SyncResponse:
    """Persist Apple Health summaries and workouts sent by the iOS app."""
    sync_token = _extract_sync_token(authorization, payload.sync_token)
    session = await get_session()
    try:
        health_repo = HealthRepository(session)
        connection = await health_repo.get_connection_for_sync_token(sync_token)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Apple Health sync token",
            )

        for summary in payload.daily_summaries:
            values = summary.model_dump()
            summary_date = values.pop("summary_date")
            await health_repo.upsert_daily_summary(
                user_id=connection.user_id,
                summary_date=summary_date,
                raw_payload=summary.model_dump(mode="json"),
                **values,
            )

        for workout in payload.workouts:
            values = workout.model_dump()
            external_uuid = values.pop("external_uuid")
            started_at = values.pop("started_at")
            await health_repo.upsert_workout(
                user_id=connection.user_id,
                external_uuid=external_uuid,
                started_at=started_at,
                raw_payload=workout.model_dump(mode="json"),
                **values,
            )

        await health_repo.mark_synced(
            connection,
            permissions=payload.permissions or None,
        )
        await session.commit()
        return SyncResponse(
            synced=True,
            daily_summaries=len(payload.daily_summaries),
            workouts=len(payload.workouts),
        )
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
