"""Pure Unity Timeline track discovery and playable-asset resolution."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Literal, Mapping


TimelineTrackKind = Literal["MOTION", "FACE"]

_MOTION_GROUP_NAME = "Motion Group"
_FACE_GROUP_NAME = "Face  Group"
_TRANSITION_FIELDS = (
    "m_EaseInDuration",
    "m_EaseOutDuration",
    "m_BlendInDuration",
    "m_BlendOutDuration",
    "m_MixInCurve",
    "m_MixOutCurve",
)
_EXTRAPOLATION_FIELDS = (
    "m_PreExtrapolationMode",
    "m_PostExtrapolationMode",
    "m_PreExtrapolationTime",
    "m_PostExtrapolationTime",
)
_PLAYABLE_FIELDS = (
    "m_Loop",
    "m_ApplyFootIK",
    "m_ApplyPlayableIK",
    "m_MatchTargetFields",
    "m_MatchTargetPosition",
    "m_MatchTargetRotation",
    "m_RemoveStartOffset",
)


@dataclass(frozen=True)
class TimelineClipSpec:
    """A resolved Timeline clip and its raw Timeline/PlayableAsset metadata."""

    source_id: Any
    display_name: str
    animation_reader: Any
    start_seconds: Any
    duration_seconds: Any
    clip_in_seconds: Any
    time_scale: Any
    transition_metadata: Mapping[str, Any]
    extrapolation_metadata: Mapping[str, Any]
    playable_metadata: Mapping[str, Any]
    source_order: int


@dataclass(frozen=True)
class TimelineTrackRef:
    """A recognized direct child of a Timeline Motion or Face group."""

    source_id: Any
    parent_name: str
    name: str
    kind: TimelineTrackKind
    clips: tuple[TimelineClipSpec, ...]


class TimelineResolutionError(ValueError):
    """A Timeline pointer could not be resolved, with source diagnostic context."""

    def __init__(
        self,
        message: str,
        *,
        track_source_id: Any = None,
        track_name: str | None = None,
        clip_source_id: Any = None,
        animation_source_id: Any = None,
        clip_display_name: str | None = None,
        source_order: int | None = None,
    ) -> None:
        self.track_source_id = track_source_id
        self.track_name = track_name
        self.clip_source_id = clip_source_id
        self.animation_source_id = animation_source_id
        self.clip_display_name = clip_display_name
        self.source_order = source_order
        context = []
        if track_name is not None:
            context.append(f"track={track_name!r}")
        if track_source_id is not None:
            context.append(f"track_source_id={track_source_id!r}")
        if clip_display_name is not None:
            context.append(f"clip={clip_display_name!r}")
        if clip_source_id is not None:
            context.append(f"clip_source_id={clip_source_id!r}")
        if animation_source_id is not None:
            context.append(f"animation_source_id={animation_source_id!r}")
        if source_order is not None:
            context.append(f"source_order={source_order}")
        detail = f" ({', '.join(context)})" if context else ""
        super().__init__(f"{message}{detail}")


def _source_id(reader: Any) -> Any:
    return getattr(reader, "path_id", None)


def _clip_display_name(clip: Any) -> str:
    return getattr(clip, "m_DisplayName", getattr(clip, "m_Name", ""))


def _read_reference(
    reference: Any,
    *,
    label: str,
    clip_display_name: str,
    source_order: int,
    clip_source_id: Any = None,
    animation_source_id: Any = None,
) -> Any:
    reference_id = _source_id(reference)
    diagnostic_clip_source_id = (
        reference_id if clip_source_id is None else clip_source_id
    )
    diagnostic_animation_source_id = (
        reference_id
        if animation_source_id is None and label == "animation clip"
        else animation_source_id
    )
    if reference is None or not callable(getattr(reference, "read", None)):
        raise TimelineResolutionError(
            f"unresolved {label} reference",
            clip_source_id=diagnostic_clip_source_id,
            animation_source_id=diagnostic_animation_source_id,
            clip_display_name=clip_display_name,
            source_order=source_order,
        )
    try:
        value = reference.read()
    except Exception as error:
        raise TimelineResolutionError(
            f"unresolved {label} reference: {error}",
            clip_source_id=diagnostic_clip_source_id,
            animation_source_id=diagnostic_animation_source_id,
            clip_display_name=clip_display_name,
            source_order=source_order,
        ) from error
    if value is None:
        raise TimelineResolutionError(
            f"unresolved {label} reference",
            clip_source_id=diagnostic_clip_source_id,
            animation_source_id=diagnostic_animation_source_id,
            clip_display_name=clip_display_name,
            source_order=source_order,
        )
    return value


def _deep_freeze(value: Any) -> Any:
    """Copy nested containers into immutable equivalents."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {_deep_freeze(key): _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    if isinstance(value, bytearray):
        return bytes(value)
    return value


def _metadata(value: Any, fields: tuple[str, ...]) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            field: _deep_freeze(getattr(value, field))
            for field in fields
            if hasattr(value, field)
        }
    )


def resolve_timeline_clip(clip: Any, source_order: int) -> TimelineClipSpec:
    """Resolve one Timeline clip through its playable asset to an AnimationClip reader."""

    display_name = _clip_display_name(clip)
    asset_reader = getattr(clip, "m_Asset", None)
    asset_source_id = _source_id(asset_reader)
    playable = _read_reference(
        asset_reader,
        label="playable asset",
        clip_display_name=display_name,
        source_order=source_order,
        clip_source_id=asset_source_id,
    )
    animation_reader = getattr(playable, "m_Clip", None)
    _read_reference(
        animation_reader,
        label="animation clip",
        clip_display_name=display_name,
        source_order=source_order,
        clip_source_id=asset_source_id,
        animation_source_id=_source_id(animation_reader),
    )
    return TimelineClipSpec(
        source_id=_source_id(animation_reader),
        display_name=display_name,
        animation_reader=animation_reader,
        start_seconds=getattr(clip, "m_Start", None),
        duration_seconds=getattr(clip, "m_Duration", None),
        clip_in_seconds=getattr(clip, "m_ClipIn", None),
        time_scale=getattr(clip, "m_TimeScale", None),
        transition_metadata=_metadata(clip, _TRANSITION_FIELDS),
        extrapolation_metadata=_metadata(clip, _EXTRAPOLATION_FIELDS),
        playable_metadata=_metadata(playable, _PLAYABLE_FIELDS),
        source_order=source_order,
    )


def _track_kind(parent_name: str) -> TimelineTrackKind | None:
    if parent_name == _MOTION_GROUP_NAME:
        return "MOTION"
    if parent_name == _FACE_GROUP_NAME:
        return "FACE"
    return None


def discover_timeline_tracks(objects: Iterable[Any]) -> list[TimelineTrackRef]:
    """Discover direct Timeline children below the recognized Motion and Face groups."""

    tracks: list[TimelineTrackRef] = []
    for track_reader in objects:
        if not callable(getattr(track_reader, "read", None)):
            continue
        track_source_id = _source_id(track_reader)
        try:
            track = track_reader.read()
        except Exception as error:
            raise TimelineResolutionError(
                f"unresolved track reference: {error}",
                track_source_id=track_source_id,
            ) from error
        if track is None:
            raise TimelineResolutionError(
                "unresolved track reference",
                track_source_id=track_source_id,
            )
        track_name = getattr(track, "m_Name", "")
        parent_reader = getattr(track, "m_Parent", None)
        if not callable(getattr(parent_reader, "read", None)):
            raise TimelineResolutionError(
                "unresolved parent reference",
                track_source_id=track_source_id,
                track_name=track_name,
            )
        try:
            parent = parent_reader.read()
        except Exception as error:
            raise TimelineResolutionError(
                f"unresolved parent reference: {error}",
                track_source_id=track_source_id,
                track_name=track_name,
            ) from error
        if parent is None:
            raise TimelineResolutionError(
                "unresolved parent reference",
                track_source_id=track_source_id,
                track_name=track_name,
            )
        parent_name = getattr(parent, "m_Name", "")
        kind = _track_kind(parent_name)
        if kind is None:
            continue
        resolved_clips = []
        for source_order, clip in enumerate(getattr(track, "m_Clips", ()) or ()):
            try:
                resolved_clips.append(resolve_timeline_clip(clip, source_order))
            except TimelineResolutionError as error:
                raise TimelineResolutionError(
                    str(error),
                    track_source_id=track_source_id,
                    track_name=track_name,
                    clip_source_id=error.clip_source_id,
                    animation_source_id=error.animation_source_id,
                    clip_display_name=error.clip_display_name,
                    source_order=error.source_order,
                ) from error
        tracks.append(
            TimelineTrackRef(
                source_id=track_source_id,
                parent_name=parent_name,
                name=track_name,
                kind=kind,
                clips=tuple(resolved_clips),
            )
        )
    return tracks


def catalog_timeline_tracks(objects: Iterable[Any]) -> list[TimelineTrackRef]:
    """Return the Timeline track catalog in the source object order."""

    return discover_timeline_tracks(objects)
