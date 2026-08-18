"""Pure Unity Timeline track discovery and playable-asset resolution."""

from dataclasses import dataclass
from logging import getLogger
import math
from types import MappingProxyType
from typing import Any, Iterable, Literal, Mapping


logger = getLogger("sssekai")


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
class TimelineFrameRange:
    """Scene-frame and inner-action bounds for one Timeline clip."""

    timeline_start: float
    timeline_end: float
    action_start: float
    action_end: float


@dataclass(frozen=True)
class TimelineTrackRef:
    """A recognized direct child of a Timeline Motion or Face group."""

    source_id: Any
    parent_name: str
    name: str
    kind: TimelineTrackKind
    clips: tuple[TimelineClipSpec, ...]
    diagnostics: tuple[str, ...] = ()


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
    logger.debug(
        "Timeline clip resolve start: clip=%r source_order=%d asset_source_id=%r start=%r duration=%r clip_in=%r time_scale=%r",
        display_name,
        source_order,
        asset_source_id,
        getattr(clip, "m_Start", None),
        getattr(clip, "m_Duration", None),
        getattr(clip, "m_ClipIn", None),
        getattr(clip, "m_TimeScale", None),
    )
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
    spec = TimelineClipSpec(
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
    logger.debug(
        "Timeline clip resolve complete: clip=%r source_order=%d animation_source_id=%r start_seconds=%r duration_seconds=%r clip_in_seconds=%r time_scale=%r",
        spec.display_name,
        spec.source_order,
        spec.source_id,
        spec.start_seconds,
        spec.duration_seconds,
        spec.clip_in_seconds,
        spec.time_scale,
    )
    return spec


_FRAME_TOLERANCE = 1e-3


def _finite_number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be finite") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def timeline_scene_frame_end(frame_end: Any) -> int:
    """Convert a computed endpoint to an integer frame without float-noise overshoot."""

    endpoint = _finite_number(frame_end, "scene frame end")
    nearest = round(endpoint)
    if abs(endpoint - nearest) <= _FRAME_TOLERANCE:
        return int(nearest)
    return int(math.ceil(endpoint))


def timeline_clip_frames(spec: TimelineClipSpec, fps: float) -> TimelineFrameRange:
    """Convert authored Timeline seconds to scene frames using one FPS."""

    scene_fps = _finite_number(fps, "fps")
    if scene_fps <= 0:
        raise ValueError("fps must be positive")
    start_seconds = _finite_number(spec.start_seconds, "start_seconds")
    duration_seconds = _finite_number(spec.duration_seconds, "duration_seconds")
    clip_in_seconds = _finite_number(spec.clip_in_seconds, "clip_in_seconds")
    time_scale = _finite_number(spec.time_scale, "time_scale")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if time_scale <= 0:
        raise ValueError("time_scale must be positive")
    if clip_in_seconds < 0:
        raise ValueError("clip_in_seconds must be nonnegative")

    timeline_start = start_seconds * scene_fps
    timeline_end = timeline_start + duration_seconds * scene_fps
    action_start = clip_in_seconds * scene_fps
    action_end = action_start + duration_seconds * time_scale * scene_fps
    if action_end <= action_start:
        raise ValueError("action_end must be greater than action_start")
    frames = TimelineFrameRange(timeline_start, timeline_end, action_start, action_end)
    logger.debug(
        "Timeline clip frame conversion: clip=%r fps=%r timeline_start=%r timeline_end=%r action_start=%r action_end=%r",
        spec.display_name,
        scene_fps,
        frames.timeline_start,
        frames.timeline_end,
        frames.action_start,
        frames.action_end,
    )
    return frames


def _metadata_enabled(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)):
        return value != 0 and math.isfinite(float(value))
    if isinstance(value, (str, bytes)):
        return value not in ("", "0", "None", "NoneMode")
    return bool(value)


def _mix_curve_has_keys(value: Any) -> bool:
    """Return whether a serialized Unity mix curve contains curve keys."""

    if value is None:
        return False
    if isinstance(value, Mapping):
        for field in ("m_Curve", "curve", "keys", "keyframes"):
            if field in value:
                return bool(value[field])
        return bool(value)
    if hasattr(value, "m_Curve"):
        return bool(value.m_Curve)
    return bool(value)


def validate_timeline_clip(
    spec: TimelineClipSpec,
    action_frame_range: tuple[float, float],
    fps: float,
) -> list[str]:
    """Validate timing and report finite approximations for unsupported semantics."""

    frames = timeline_clip_frames(spec, fps)
    try:
        action_start = _finite_number(action_frame_range[0], "action frame start")
        action_end = _finite_number(action_frame_range[1], "action frame end")
    except (IndexError, TypeError) as error:
        raise ValueError("action_frame_range must contain two finite frames") from error
    if action_end <= action_start:
        raise ValueError("action frame range must be increasing")
    if frames.action_start < action_start - _FRAME_TOLERANCE:
        raise ValueError(
            "requested Timeline source window starts before generated Action frame range"
        )

    warnings: list[str] = []
    if frames.action_end > action_end + _FRAME_TOLERANCE:
        warnings.append(
            "generated Action is shorter than the authored Timeline source window; "
            "the final pose will be held for the remaining Timeline duration"
        )
    if any(
        _metadata_enabled(spec.transition_metadata.get(field))
        for field in _TRANSITION_FIELDS
        if field not in ("m_MixInCurve", "m_MixOutCurve")
    ) or any(
        _mix_curve_has_keys(spec.transition_metadata.get(field))
        for field in ("m_MixInCurve", "m_MixOutCurve")
    ):
        warnings.append("nonzero Timeline ease/blend/mix metadata is not applied")

    if any(
        _metadata_enabled(value)
        for field, value in spec.extrapolation_metadata.items()
        if field.endswith("Mode") and str(value) not in ("None", "NoneMode", "")
    ) or any(
        _metadata_enabled(value)
        for field, value in spec.extrapolation_metadata.items()
        if field.endswith("Time")
    ):
        warnings.append("non-default Timeline extrapolation is not applied")

    playable = spec.playable_metadata
    if _metadata_enabled(playable.get("m_Loop")):
        warnings.append("Timeline looping is not applied")
    if any(
        _metadata_enabled(playable.get(field))
        for field in ("m_MatchTargetFields", "m_MatchTargetPosition", "m_MatchTargetRotation")
    ):
        warnings.append("Timeline root matching is not applied")
    if any(
        _metadata_enabled(playable.get(field))
        for field in ("m_ApplyFootIK", "m_ApplyPlayableIK")
    ):
        warnings.append("Timeline foot IK is not applied")
    return warnings


def _track_kind(parent_name: str) -> TimelineTrackKind | None:
    if parent_name == _MOTION_GROUP_NAME:
        return "MOTION"
    if parent_name == _FACE_GROUP_NAME:
        return "FACE"
    return None


def discover_timeline_tracks(
    objects: Iterable[Any], *, tolerate_unresolved_clips: bool = False
) -> list[TimelineTrackRef]:
    """Discover direct Timeline children below the recognized Motion and Face groups."""

    objects = tuple(objects)
    logger.debug(
        "Timeline discovery start: objects=%d tolerate_unresolved_clips=%s",
        len(objects),
        tolerate_unresolved_clips,
    )
    tracks: list[TimelineTrackRef] = []
    for track_reader in objects:
        if not callable(getattr(track_reader, "read", None)):
            logger.debug(
                "Timeline discovery skipped unreadable object: source_id=%r type=%r",
                _source_id(track_reader),
                type(track_reader).__name__,
            )
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
            logger.debug(
                "Timeline discovery ignored track outside Motion/Face group: track=%r parent=%r source_id=%r",
                track_name,
                parent_name,
                track_source_id,
            )
            continue
        logger.debug(
            "Timeline track candidate: track=%r parent=%r kind=%s source_id=%r clip_count=%d",
            track_name,
            parent_name,
            kind,
            track_source_id,
            len(getattr(track, "m_Clips", ()) or ()),
        )
        resolved_clips = []
        diagnostics = []
        for source_order, clip in enumerate(getattr(track, "m_Clips", ()) or ()):
            try:
                resolved_clip = resolve_timeline_clip(clip, source_order)
                resolved_clips.append(resolved_clip)
                logger.debug(
                    "Timeline clip retained: track=%r clip=%r source_order=%d animation_source_id=%r",
                    track_name,
                    resolved_clip.display_name,
                    source_order,
                    resolved_clip.source_id,
                )
            except TimelineResolutionError as error:
                logger.debug(
                    "Timeline clip resolution failed: track=%r source_order=%d clip_source_id=%r error=%s",
                    track_name,
                    source_order,
                    _source_id(clip),
                    error,
                )
                if tolerate_unresolved_clips:
                    diagnostics.append(str(error))
                    continue
                raise TimelineResolutionError(
                    str(error),
                    track_source_id=track_source_id,
                    track_name=track_name,
                    clip_source_id=error.clip_source_id,
                    animation_source_id=error.animation_source_id,
                    clip_display_name=error.clip_display_name,
                    source_order=error.source_order,
                ) from error
        track_ref = TimelineTrackRef(
            source_id=track_source_id,
            parent_name=parent_name,
            name=track_name,
            kind=kind,
            clips=tuple(resolved_clips),
            diagnostics=tuple(diagnostics),
        )
        logger.debug(
            "Timeline track discovery complete: track=%r kind=%s source_id=%r clips=%d diagnostics=%d",
            track_ref.name,
            track_ref.kind,
            track_ref.source_id,
            len(track_ref.clips),
            len(track_ref.diagnostics),
        )
        tracks.append(track_ref)
    logger.debug("Timeline discovery complete: tracks=%d", len(tracks))
    return tracks


def catalog_timeline_tracks(objects: Iterable[Any]) -> list[TimelineTrackRef]:
    """Return catalog entries while retaining valid clips from partially unresolved tracks."""

    return discover_timeline_tracks(objects, tolerate_unresolved_clips=True)
