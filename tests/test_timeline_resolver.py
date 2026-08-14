from dataclasses import FrozenInstanceError
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sssekai_blender_io.blender.core.timeline import (
    TimelineClipSpec,
    TimelineResolutionError,
    TimelineTrackRef,
    catalog_timeline_tracks,
    discover_timeline_tracks,
    resolve_timeline_clip,
)


class Reader:
    def __init__(self, value, path_id):
        self.value = value
        self.path_id = path_id
        self.read_count = 0

    def read(self):
        self.read_count += 1
        return self.value


class FailingReader:
    def __init__(self, path_id, error="read failed"):
        self.path_id = path_id
        self.error = error

    def read(self):
        raise RuntimeError(self.error)


class Group:
    def __init__(self, name):
        self.m_Name = name


class AnimationClip:
    def __init__(self, name):
        self.m_Name = name


class PlayableAsset:
    def __init__(self, animation_reader, **metadata):
        self.m_Clip = animation_reader
        for name, value in metadata.items():
            setattr(self, name, value)


class TimelineClip:
    def __init__(self, display_name, asset_reader, **metadata):
        self.m_DisplayName = display_name
        self.m_Asset = asset_reader
        for name, value in metadata.items():
            setattr(self, name, value)


class Track:
    def __init__(self, name, parent_reader, clips):
        self.m_Name = name
        self.m_Parent = parent_reader
        self.m_Clips = clips


def make_clip(
    display_name,
    source_id,
    animation_name=None,
    *,
    start=0.0,
    duration=1.0,
    clip_in=0.0,
    time_scale=1.0,
    **metadata,
):
    animation = AnimationClip(animation_name or display_name)
    animation_reader = Reader(animation, source_id + 100)
    playable = PlayableAsset(animation_reader, **metadata.pop("playable", {}))
    asset_reader = Reader(playable, source_id + 10)
    return TimelineClip(
        display_name,
        asset_reader,
        m_Start=start,
        m_Duration=duration,
        m_ClipIn=clip_in,
        m_TimeScale=time_scale,
        **metadata,
    ), animation_reader, playable


def make_track(name, group_name, source_id, clips):
    return Reader(
        Track(name, Reader(Group(group_name), source_id + 1), clips),
        source_id,
    )


def test_resolver_follows_asset_to_playable_to_animation_clip():
    clip, animation_reader, _ = make_clip(
        "motion-a",
        200,
        start=12.5,
        duration=3.0,
        clip_in=0.25,
        time_scale=1.0,
    )
    tracks = discover_timeline_tracks([make_track("Character0", "Motion Group", 100, [clip])])

    assert tracks[0].name == "Character0"
    assert tracks[0].parent_name == "Motion Group"
    assert tracks[0].kind == "MOTION"
    assert tracks[0].source_id == 100
    assert tracks[0].clips[0].display_name == "motion-a"
    assert tracks[0].clips[0].animation_reader is animation_reader
    assert tracks[0].clips[0].start_seconds == 12.5
    assert tracks[0].clips[0].duration_seconds == 3.0
    assert tracks[0].clips[0].clip_in_seconds == 0.25
    assert tracks[0].clips[0].time_scale == 1.0
    assert animation_reader.read_count == 1


def test_discovery_classifies_only_direct_motion_and_face_groups():
    motion_clip, _, _ = make_clip("motion", 10)
    face_clip, _, _ = make_clip("face", 20)
    ignored_clip, _, _ = make_clip("ignored", 30)
    tracks = discover_timeline_tracks(
        [
            make_track("raw-motion", "Motion Group", 1, [motion_clip]),
            make_track("raw-face", "Face  Group", 2, [face_clip]),
            make_track("raw-other", "Other Group", 3, [ignored_clip]),
        ]
    )

    assert [(track.parent_name, track.name, track.kind) for track in tracks] == [
        ("Motion Group", "raw-motion", "MOTION"),
        ("Face  Group", "raw-face", "FACE"),
    ]


def test_discovery_preserves_track_and_clip_source_order_and_raw_labels():
    first, _, _ = make_clip("raw clip / one", 10)
    second, _, _ = make_clip("raw clip / two", 20)
    third, _, _ = make_clip("raw clip / three", 30)
    readers = [
        make_track("second raw track", "Motion Group", 2, [second]),
        make_track("first raw track", "Motion Group", 1, [first, third]),
    ]

    tracks = discover_timeline_tracks(readers)

    assert [track.name for track in tracks] == ["second raw track", "first raw track"]
    assert [clip.display_name for clip in tracks[1].clips] == [
        "raw clip / one",
        "raw clip / three",
    ]
    assert [clip.source_order for clip in tracks[1].clips] == [0, 1]


def test_empty_recognized_tracks_are_retained_and_catalog_matches_discovery():
    empty = make_track("empty raw track", "Face  Group", 50, [])

    discovered = discover_timeline_tracks([empty])
    catalog = catalog_timeline_tracks([empty])

    assert discovered == catalog
    assert discovered[0].name == "empty raw track"
    assert discovered[0].kind == "FACE"
    assert discovered[0].clips == ()


def test_resolver_captures_raw_transition_extrapolation_and_playable_metadata():
    clip, _, playable = make_clip(
        "metadata clip",
        40,
        m_EaseInDuration=0.5,
        m_EaseOutDuration=0.25,
        m_PreExtrapolationMode="Hold",
        m_PostExtrapolationMode="Loop",
        playable={
            "m_Loop": True,
            "m_ApplyFootIK": True,
            "m_ApplyPlayableIK": False,
        },
    )

    spec = resolve_timeline_clip(clip, source_order=7)

    assert spec.source_id == 140
    assert spec.source_order == 7
    assert spec.transition_metadata == {
        "m_EaseInDuration": 0.5,
        "m_EaseOutDuration": 0.25,
    }
    assert spec.extrapolation_metadata == {
        "m_PreExtrapolationMode": "Hold",
        "m_PostExtrapolationMode": "Loop",
    }
    assert spec.playable_metadata == {
        "m_Loop": True,
        "m_ApplyFootIK": True,
        "m_ApplyPlayableIK": False,
    }
    assert playable.m_Clip.read_count == 1


def test_timeline_models_are_immutable():
    clip, _, _ = make_clip("immutable", 70)
    spec = resolve_timeline_clip(clip, source_order=0)
    track = discover_timeline_tracks([make_track("track", "Motion Group", 60, [clip])])[0]

    assert isinstance(spec, TimelineClipSpec)
    assert isinstance(track, TimelineTrackRef)
    with pytest.raises(FrozenInstanceError):
        spec.display_name = "changed"
    with pytest.raises(FrozenInstanceError):
        track.name = "changed"


def test_captured_metadata_is_deeply_immutable_and_detached_from_sources():
    transition_curve = {"keys": [{"time": 0.0, "value": 1.0}]}
    target_position = [1.0, {"axis": "y", "value": 2.0}]
    clip, _, _ = make_clip(
        "nested metadata",
        80,
        m_MixInCurve=transition_curve,
        playable={"m_MatchTargetPosition": target_position},
    )

    spec = resolve_timeline_clip(clip, source_order=0)
    transition_curve["keys"][0]["value"] = 99.0
    target_position[1]["value"] = 99.0

    assert spec.transition_metadata["m_MixInCurve"]["keys"][0]["value"] == 1.0
    assert spec.playable_metadata["m_MatchTargetPosition"][1]["value"] == 2.0
    with pytest.raises(TypeError):
        spec.transition_metadata["m_MixInCurve"]["keys"][0]["value"] = 3.0
    with pytest.raises(TypeError):
        spec.playable_metadata["m_MatchTargetPosition"][1]["value"] = 3.0


def test_unresolved_asset_reference_has_typed_track_and_clip_context():
    clip = TimelineClip("broken clip", Reader(None, 222))
    track_reader = make_track("Character broken", "Motion Group", 111, [clip])

    with pytest.raises(TimelineResolutionError) as raised:
        discover_timeline_tracks([track_reader])

    error = raised.value
    assert error.track_source_id == 111
    assert error.track_name == "Character broken"
    assert error.clip_source_id == 222
    assert error.clip_display_name == "broken clip"
    assert "Character broken" in str(error)
    assert "broken clip" in str(error)


def test_unreadable_track_reference_has_typed_track_context():
    with pytest.raises(TimelineResolutionError) as raised:
        discover_timeline_tracks([FailingReader(444)])

    error = raised.value
    assert error.track_source_id == 444
    assert error.track_name is None
    assert "unresolved track reference" in str(error)


def test_unreadable_parent_reference_has_typed_track_context():
    track_reader = Reader(
        Track("broken parent", FailingReader(555), []),
        111,
    )

    with pytest.raises(TimelineResolutionError) as raised:
        discover_timeline_tracks([track_reader])

    error = raised.value
    assert error.track_source_id == 111
    assert error.track_name == "broken parent"
    assert "unresolved parent reference" in str(error)


def test_unresolved_animation_reference_preserves_asset_and_animation_ids():
    clip = TimelineClip(
        "missing animation",
        Reader(PlayableAsset(Reader(None, 333)), 222),
    )

    with pytest.raises(TimelineResolutionError) as raised:
        resolve_timeline_clip(clip, source_order=4)

    error = raised.value
    assert error.clip_source_id == 222
    assert error.animation_source_id == 333
    assert error.clip_display_name == "missing animation"
    assert error.source_order == 4
    assert "missing animation" in str(error)


def test_unrecognized_groups_remain_ignored_even_with_broken_clips():
    broken_clip = TimelineClip("ignored broken clip", Reader(None, 666))

    assert discover_timeline_tracks(
        [make_track("ignored track", "Other Group", 667, [broken_clip])]
    ) == []


def test_resolver_source_has_no_mvdata_dependency_or_file_access():
    import sssekai_blender_io.blender.core.timeline as timeline

    source = Path(timeline.__file__).read_text(encoding="utf-8").lower()
    assert "mvdata" not in source
    assert "xtract" not in source
    assert "open(" not in source
    assert "path(" not in source
