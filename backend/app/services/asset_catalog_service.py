"""Project-wide reference catalogue; generated media keeps its original identity."""

from sqlmodel import Session, select

from app.models import Asset, Character, CharacterState, Episode, Prop, Scene, VoiceProfile
from app.schemas.serializers import scene_asset_url
from app.services.reference_service import episode_reference_labels


def project_asset_catalog(session: Session, project_id: str) -> list[dict]:
    items: list[dict] = []

    def add(kind, row, path, label, media="image", *, episode=None, order=None, aliases=None, description=""):
        if not path:
            return
        url = path if path.startswith(("http://", "https://")) else scene_asset_url(path, f"{kind}-{row.id}")
        if url:
            items.append({
                "kind": kind, "id": row.id, "label": label, "media": media, "url": url,
                "description": description or "", "aliases": aliases or [],
                "episodeId": episode.id if episode else None,
                "episodeNumber": episode.episode_number if episode else None,
                "episodeTitle": episode.title if episode else "", "sceneOrder": order,
                "updatedAt": row.updated_at,
            })

    characters = session.exec(select(Character).where(Character.project_id == project_id, Character.deleted_at.is_(None)).order_by(Character.order_num)).all()
    for row in characters:
        add("character", row, row.sheet_image_path or row.reference_image_path, row.name, description=row.description)
    states = session.exec(select(CharacterState, Character).join(Character, Character.id == CharacterState.character_id).where(Character.project_id == project_id, Character.deleted_at.is_(None), CharacterState.deleted_at.is_(None)).order_by(Character.order_num, CharacterState.order_num)).all()
    for row, character in states:
        add("characterState", row, row.reference_image_path, f"{character.name} · {row.name}", description=row.description)
    for row in session.exec(select(Prop).where(Prop.project_id == project_id, Prop.deleted_at.is_(None)).order_by(Prop.order_num)).all():
        add("prop", row, row.image_path, row.name, description=row.description)
    episodes = session.exec(select(Episode).where(Episode.project_id == project_id, Episode.deleted_at.is_(None)).order_by(Episode.episode_number)).all()
    by_id = {row.id: row for row in episodes}
    for row in episodes:
        labels = episode_reference_labels("tone", row)
        add("tone", row, row.tone_image_path, labels[0], episode=row, aliases=labels)
    for row in session.exec(select(Scene).where(Scene.project_id == project_id, Scene.deleted_at.is_(None)).order_by(Scene.order_num)).all():
        episode = by_id.get(row.episode_id)
        if row.episode_id and not episode:
            continue
        for kind, path, media in (("sceneImage", row.image_path, "image"), ("sceneVideo", row.video_path, "video")):
            labels = episode_reference_labels(kind, episode, row.order_num)
            add(kind, row, path, labels[0], media, episode=episode, order=row.order_num, aliases=labels)
    for row in session.exec(select(VoiceProfile).where(VoiceProfile.project_id == project_id, VoiceProfile.deleted_at.is_(None)).order_by(VoiceProfile.order_num)).all():
        add("voice", row, row.audio_path, row.name, "audio", description=row.note)
    for row in session.exec(select(Asset).where(Asset.project_id == project_id, Asset.deleted_at.is_(None)).order_by(Asset.created_at)).all():
        add("asset", row, row.path, row.name, row.kind, description=row.description)
    return items
