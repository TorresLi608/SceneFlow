"""Prop reads and writes. Deliberately the same shape as `character_service`."""

from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import Prop
from app.utils.common import new_id, now


def props_for(session: Session, project_id: str) -> list[Prop]:
    return list(
        session.exec(
            select(Prop)
            .where(Prop.project_id == project_id, Prop.deleted_at.is_(None))
            .order_by(Prop.order_num.asc(), Prop.name.asc())
        ).all()
    )


def owned_prop(session: Session, project_id: str, prop_id: str) -> Prop:
    prop = session.exec(
        select(Prop).where(
            Prop.id == prop_id,
            Prop.project_id == project_id,
            Prop.deleted_at.is_(None),
        )
    ).first()
    if not prop:
        raise HTTPException(404, "prop not found")
    return prop


def create_prop(session: Session, project_id: str, **values: object) -> Prop:
    stamp = now()
    prop = Prop(
        id=new_id("prop"),
        created_at=stamp,
        updated_at=stamp,
        project_id=project_id,
        **values,
    )
    session.add(prop)
    session.flush()
    return prop


def delete_prop(session: Session, prop: Prop) -> None:
    stamp = now()
    prop.deleted_at = stamp
    prop.updated_at = stamp
    session.add(prop)
    session.flush()


def owner_names(session: Session, project_id: str) -> dict[str, str]:
    """Character id to name, so a prop card can show whose it is without a second request."""
    from app.services.character_service import characters_for

    return {character.id: character.name for character in characters_for(session, project_id)}


def prop_payload(session: Session, project_id: str, prop: Prop) -> dict[str, object]:
    """One prop as the wire sees it.

    Lives here rather than in the endpoint because the generation-job handler has to produce
    the identical shape when it finishes a draw — `api/v1` may not be imported by a service.
    """
    from app.schemas.serializers import prop_json

    return prop_json(prop, owner_names(session, project_id).get(prop.owner_character_id or "", ""))
