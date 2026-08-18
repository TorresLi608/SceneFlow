"""Voice profile reads and writes, plus the binding characters hold onto them."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import update
from sqlmodel import Session, select

from app.models import Character, VoiceProfile
from app.utils.common import new_id, now


def voice_profiles_for(session: Session, project_id: str) -> list[VoiceProfile]:
    return list(
        session.exec(
            select(VoiceProfile)
            .where(VoiceProfile.project_id == project_id, VoiceProfile.deleted_at.is_(None))
            .order_by(VoiceProfile.order_num.asc(), VoiceProfile.name.asc())
        ).all()
    )


def owned_voice_profile(session: Session, project_id: str, profile_id: str) -> VoiceProfile:
    profile = session.exec(
        select(VoiceProfile).where(
            VoiceProfile.id == profile_id,
            VoiceProfile.project_id == project_id,
            VoiceProfile.deleted_at.is_(None),
        )
    ).first()
    if not profile:
        raise HTTPException(404, "voice profile not found")
    return profile


def create_voice_profile(session: Session, project_id: str, **values: object) -> VoiceProfile:
    stamp = now()
    profile = VoiceProfile(
        id=new_id("voice"),
        created_at=stamp,
        updated_at=stamp,
        project_id=project_id,
        **values,
    )
    session.add(profile)
    session.flush()
    return profile


def delete_voice_profile(session: Session, profile: VoiceProfile) -> None:
    """Soft-delete the profile and release every character bound to it.

    The binding is a plain column rather than a foreign key, so this stands in for
    ON DELETE SET NULL. Leaving it would point a card at a profile that no longer resolves.
    """
    stamp = now()
    session.execute(
        update(Character)
        .where(Character.voice_profile_id == profile.id)
        .values(voice_profile_id=None, updated_at=stamp),
        execution_options={"synchronize_session": False},
    )
    profile.deleted_at = stamp
    profile.updated_at = stamp
    session.add(profile)
    session.flush()
