"""Episode-level reads and writes: the layer a project's content actually hangs off.

A project is a series and owns no shots directly. Every scene belongs to an episode, so
anything that used to operate on "the project's scenes" now needs a target episode. A
caller that does not name one gets the current episode, which keeps the single-episode
flow working for projects that only ever have one.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Episode, Scene
from app.utils.common import new_id, now


# Where an episode sits in its own lifecycle. The busy lock stays on the project
# (`claim_project_status`): one run owns the series at a time, so a second episode
# cannot start rendering while the first is still going.
EPISODE_STATUSES = {"draft", "storyboard", "generating", "done", "partial", "failed"}


def episodes_for(session: Session, project_id: str) -> list[Episode]:
    return list(
        session.exec(
            select(Episode)
            .where(Episode.project_id == project_id, Episode.deleted_at.is_(None))
            .order_by(Episode.episode_number.asc())
        ).all()
    )


def current_episode(session: Session, project_id: str) -> Episode | None:
    """The episode new work lands on by default: the highest-numbered one."""
    return session.exec(
        select(Episode)
        .where(Episode.project_id == project_id, Episode.deleted_at.is_(None))
        .order_by(Episode.episode_number.desc())
    ).first()


def create_episode(
    session: Session,
    project_id: str,
    *,
    title: str = "",
    synopsis: str = "",
    source_text: str = "",
) -> Episode:
    """Append the next episode.

    The number comes from the highest live episode, so reusing a soft-deleted number is
    fine — the uniqueness index only covers rows that are still there.
    """
    highest = session.exec(
        select(func.max(Episode.episode_number)).where(
            Episode.project_id == project_id,
            Episode.deleted_at.is_(None),
        )
    ).first()
    number = int(highest or 0) + 1
    stamp = now()
    episode = Episode(
        id=new_id("ep"),
        created_at=stamp,
        updated_at=stamp,
        project_id=project_id,
        episode_number=number,
        title=title.strip()[:80] or f"第 {number} 集",
        synopsis=synopsis,
        source_text=source_text,
        status="draft",
    )
    session.add(episode)
    session.flush()
    return episode


def ensure_episode(session: Session, project_id: str) -> Episode:
    """The current episode, creating episode 1 when the project has none.

    A project with no episode can hold no scenes at all, so every path that writes content
    goes through here rather than failing on a series nobody has opened yet.
    """
    return current_episode(session, project_id) or create_episode(session, project_id)


def resolve_episode(session: Session, project_id: str, episode_id: str | None) -> Episode:
    """The episode a request targets. An unnamed one means the current episode."""
    if not episode_id:
        return ensure_episode(session, project_id)
    episode = session.exec(
        select(Episode).where(
            Episode.id == episode_id,
            Episode.project_id == project_id,
            Episode.deleted_at.is_(None),
        )
    ).first()
    if not episode:
        raise HTTPException(404, "episode not found")
    return episode


def episode_scenes(session: Session, episode_id: str) -> list[Scene]:
    return list(
        session.exec(
            select(Scene)
            .where(Scene.episode_id == episode_id, Scene.deleted_at.is_(None))
            .order_by(Scene.order_num.asc())
        ).all()
    )


def scene_counts(session: Session, project_ids: list[str]) -> dict[str, int]:
    """Shot count per episode, for every listed project in one query."""
    if not project_ids:
        return {}
    rows = session.exec(
        select(Scene.episode_id, func.count(Scene.id))
        .where(
            Scene.project_id.in_(project_ids),
            Scene.deleted_at.is_(None),
            Scene.episode_id.is_not(None),
        )
        .group_by(Scene.episode_id)
    ).all()
    return {episode_id: int(count) for episode_id, count in rows}


def episodes_by_project(session: Session, project_ids: list[str]) -> dict[str, list[Episode]]:
    """Episodes grouped by project, so a list endpoint stays at one query instead of N."""
    if not project_ids:
        return {}
    rows = session.exec(
        select(Episode)
        .where(Episode.project_id.in_(project_ids), Episode.deleted_at.is_(None))
        .order_by(Episode.episode_number.asc())
    ).all()
    grouped: dict[str, list[Episode]] = {project_id: [] for project_id in project_ids}
    for episode in rows:
        grouped.setdefault(episode.project_id, []).append(episode)
    return grouped


def touch_episode(session: Session, episode: Episode, **values: object) -> Episode:
    for key, value in values.items():
        setattr(episode, key, value)
    episode.updated_at = now()
    session.add(episode)
    session.flush()
    return episode


def delete_episode(session: Session, episode: Episode) -> None:
    """Soft-delete an episode and the shots it owns.

    The scenes go with it: they are the episode's content, and leaving them behind would
    strand rows that no longer belong to anything reachable.
    """
    stamp = now()
    for scene in episode_scenes(session, episode.id):
        scene.deleted_at = stamp
        scene.updated_at = stamp
        session.add(scene)
    episode.deleted_at = stamp
    episode.updated_at = stamp
    session.add(episode)
    session.flush()
