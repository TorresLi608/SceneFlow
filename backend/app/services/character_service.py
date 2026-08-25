"""The series bible in use: who is in a shot, and what they look and sound like there.

Characters are the answer to a specific failure of long-running series: the same person
drifts between episodes because every render starts from scratch. A character card pins the
look, the image model, and the voice; a `CharacterState` is an alternate form of that same
person — an age, an outfit — and when a state carries an episode range it is also how a
series says "this one changed in episode 5" without that drift being accidental.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import Character, CharacterState, Scene, SceneCharacter
from app.utils.common import new_id, now


@dataclass(frozen=True)
class ResolvedCharacter:
    """A character as it stands in one episode, after states are applied."""

    id: str
    name: str
    appearance_prompt: str
    reference_image_path: str | None
    voice_provider: str
    voice_model: str

    def as_payload(self) -> dict[str, str | None]:
        """Plain data, because generation runs off scene dicts rather than ORM rows."""
        return {
            "id": self.id,
            "name": self.name,
            "appearance_prompt": self.appearance_prompt,
            "reference_image_path": self.reference_image_path,
            "voice_provider": self.voice_provider,
            "voice_model": self.voice_model,
        }


def characters_for(session: Session, project_id: str) -> list[Character]:
    return list(
        session.exec(
            select(Character)
            .where(Character.project_id == project_id, Character.deleted_at.is_(None))
            .order_by(Character.order_num.asc(), Character.name.asc())
        ).all()
    )


def owned_character(session: Session, project_id: str, character_id: str) -> Character:
    character = session.exec(
        select(Character).where(
            Character.id == character_id,
            Character.project_id == project_id,
            Character.deleted_at.is_(None),
        )
    ).first()
    if not character:
        raise HTTPException(404, "character not found")
    return character


def create_character(session: Session, project_id: str, **values: object) -> Character:
    stamp = now()
    character = Character(
        id=new_id("char"),
        created_at=stamp,
        updated_at=stamp,
        project_id=project_id,
        **values,
    )
    session.add(character)
    session.flush()
    return character


def delete_character(session: Session, character: Character) -> None:
    """Soft-delete the card and its states, and drop it from every shot's cast.

    The cast links are a join table with no soft-delete column, so they are removed
    outright; leaving them would keep a deleted character in prompts.
    """
    stamp = now()
    for state in states_for(session, [character.id]).get(character.id, []):
        state.deleted_at = stamp
        state.updated_at = stamp
        session.add(state)
    for link in session.exec(
        select(SceneCharacter).where(SceneCharacter.character_id == character.id)
    ).all():
        session.delete(link)
    character.deleted_at = stamp
    character.updated_at = stamp
    session.add(character)
    session.flush()


def states_for(session: Session, character_ids: list[str]) -> dict[str, list[CharacterState]]:
    if not character_ids:
        return {}
    rows = session.exec(
        select(CharacterState)
        .where(
            CharacterState.character_id.in_(character_ids),
            CharacterState.deleted_at.is_(None),
        )
        .order_by(CharacterState.order_num.asc(), CharacterState.id.asc())
    ).all()
    grouped: dict[str, list[CharacterState]] = {character_id: [] for character_id in character_ids}
    for state in rows:
        grouped.setdefault(state.character_id, []).append(state)
    return grouped


def owned_state(session: Session, character_id: str, state_id: str) -> CharacterState:
    state = session.exec(
        select(CharacterState).where(
            CharacterState.id == state_id,
            CharacterState.character_id == character_id,
            CharacterState.deleted_at.is_(None),
        )
    ).first()
    if not state:
        raise HTTPException(404, "character state not found")
    return state


def create_state(session: Session, character_id: str, **values: object) -> CharacterState:
    stamp = now()
    state = CharacterState(
        id=new_id("cstate"),
        created_at=stamp,
        updated_at=stamp,
        character_id=character_id,
        **values,
    )
    session.add(state)
    session.flush()
    return state


def resolve_state(states: list[CharacterState], episode_number: int) -> CharacterState | None:
    """The state in effect for an episode: the latest one whose range covers it.

    A state with no `from_episode` is not pinned to the timeline at all — it is one of
    several parallel looks the user picks between, so it never wins this resolution and
    the card's own look stands. Ranges may overlap when a look is revised twice, so the
    most recent change wins rather than whichever row happens to be read first.
    """
    covering = [
        state
        for state in states
        if state.from_episode is not None
        and state.from_episode <= episode_number
        and (state.to_episode is None or episode_number <= state.to_episode)
    ]
    if not covering:
        return None
    return max(covering, key=lambda state: (state.from_episode or 0, state.id))


def resolve_character(
    character: Character,
    states: list[CharacterState],
    episode_number: int,
) -> ResolvedCharacter:
    """Fold the episode-scoped state over the character card.

    A state only overrides the fields it actually sets: an empty appearance prompt means
    "the look did not change", not "this character has no look".
    """
    state = resolve_state(states, episode_number)
    return ResolvedCharacter(
        id=character.id,
        name=character.name,
        appearance_prompt=(
            state.appearance_prompt if state and state.appearance_prompt else character.appearance_prompt
        ),
        reference_image_path=(
            state.reference_image_path
            if state and state.reference_image_path
            # The card portrait is legacy and only older series still have one, so a
            # character built entirely out of states falls through to its merged sheet.
            else character.reference_image_path or character.sheet_image_path
        ),
        # States carry no provider of their own: a voice change stays on the account that
        # holds the credentials, otherwise the override would be unusable at synthesis time.
        voice_provider=character.voice_provider,
        voice_model=(state.voice_model if state and state.voice_model else character.voice_model),
    )


def cast_for_episode(session: Session, project_id: str, episode_number: int) -> dict[str, ResolvedCharacter]:
    """Every character in the series as it stands in one episode, keyed by id."""
    characters = characters_for(session, project_id)
    states = states_for(session, [character.id for character in characters]) or {}
    return {
        character.id: resolve_character(character, states.get(character.id, []), episode_number)
        for character in characters
    }


def scene_cast(session: Session, scene_ids: list[str]) -> dict[str, list[str]]:
    """Character ids per shot, for a whole episode in one query."""
    if not scene_ids:
        return {}
    rows = session.exec(
        select(SceneCharacter).where(SceneCharacter.scene_id.in_(scene_ids))
    ).all()
    grouped: dict[str, list[str]] = {scene_id: [] for scene_id in scene_ids}
    for link in rows:
        grouped.setdefault(link.scene_id, []).append(link.character_id)
    return grouped


def set_scene_cast(session: Session, scene: Scene, character_ids: list[str]) -> list[str]:
    """Replace a shot's cast, rejecting anyone who is not in this project's bible."""
    wanted = list(dict.fromkeys(character_ids))
    if wanted:
        known = {
            character.id
            for character in session.exec(
                select(Character).where(
                    Character.id.in_(wanted),
                    Character.project_id == scene.project_id,
                    Character.deleted_at.is_(None),
                )
            ).all()
        }
        missing = [character_id for character_id in wanted if character_id not in known]
        if missing:
            raise HTTPException(400, f"unknown character for this project: {', '.join(missing)}")

    for link in session.exec(select(SceneCharacter).where(SceneCharacter.scene_id == scene.id)).all():
        session.delete(link)
    session.flush()
    stamp = now()
    for character_id in wanted:
        session.add(SceneCharacter(scene_id=scene.id, character_id=character_id, created_at=stamp))
    scene.updated_at = stamp
    session.add(scene)
    session.flush()
    return wanted
