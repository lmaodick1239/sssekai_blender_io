"""Task 6 dependency-free end-to-end Timeline regression coverage."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _load_timeline():
    name = "task6_timeline_under_test"
    spec = importlib.util.spec_from_file_location(name, ROOT / "blender/core/timeline.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_helpers():
    package = ModuleType("task6_helpers_package")
    package.__path__ = []
    package.logger = SimpleNamespace()
    package.register_wm_props = lambda **kwargs: None
    package.register_class = lambda value: value
    package.sssekai_global = SimpleNamespace()
    core = ModuleType("task6_helpers_package.core")
    core.__path__ = []
    math_module = ModuleType("task6_helpers_package.core.math")
    math_module.blMatrix = object
    math_module.blVector = object
    utils = ModuleType("task6_helpers_package.core.utils")
    utils.get_addon_relative_path = lambda *parts: Path(*parts)
    consts = ModuleType("task6_helpers_package.core.consts")
    consts.DEFAULT_BONE_SIZE = 0.1
    bpy = ModuleType("bpy")
    bpy.types = SimpleNamespace(
        Action=object,
        FCurve=object,
        ID=object,
        Object=object,
        NlaStrip=object,
        EditBone=object,
        Armature=object,
        Keyframe=object,
        Operator=object,
    )
    app = ModuleType("bpy.app")
    translations = ModuleType("bpy.app.translations")
    translations.pgettext = lambda value: value
    app.translations = translations
    sys.modules.update(
        {
            package.__name__: package,
            core.__name__: core,
            math_module.__name__: math_module,
            utils.__name__: utils,
            consts.__name__: consts,
            "bpy": bpy,
            "bpy.app": app,
            "bpy.app.translations": translations,
        }
    )
    name = "task6_helpers_package.core.helpers"
    spec = importlib.util.spec_from_file_location(name, ROOT / "blender/core/helpers.py")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "task6_helpers_package.core"
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TIMELINE = _load_timeline()
HELPERS = _load_helpers()


class Reader:
    def __init__(self, value, path_id):
        self.value = value
        self.path_id = path_id

    def read(self):
        return self.value


class Animation:
    def __init__(self, name):
        self.m_Name = name


class Playable:
    def __init__(self, animation):
        self.m_Clip = Reader(animation, f"animation-{animation.m_Name}")


class Clip:
    def __init__(self, name, start, duration):
        self.m_DisplayName = name
        self.m_Start = start
        self.m_Duration = duration
        self.m_ClipIn = 0.25
        self.m_TimeScale = 1.0
        animation = Animation(name)
        self.m_Asset = Reader(Playable(animation), f"asset-{name}")


class Group:
    def __init__(self, name):
        self.m_Name = name


class Track:
    def __init__(self, name, group, clips):
        self.m_Name = name
        self.m_Parent = Reader(Group(group), f"group-{group}")
        self.m_Clips = clips


class Strip:
    def __init__(self, name, start, action):
        self.name = name
        self.frame_start = start
        self.frame_end = start
        self.action = action
        self.action_frame_start = None
        self.action_frame_end = None
        self.influence = 0.0
        self.action_slot = None


class Strips(list):
    def new(self, name, frame_start, action):
        strip = Strip(name, frame_start, action)
        self.append(strip)
        return strip


class Target:
    id_type = "OBJECT"

    def __init__(self, name):
        self.name = name
        self.animation_data = None

    def animation_data_create(self):
        self.animation_data = SimpleNamespace(nla_tracks=Tracks())
        return self.animation_data


class TrackNla:
    def __init__(self):
        self.name = ""
        self.strips = Strips()


class Tracks(list):
    def new(self):
        track = TrackNla()
        self.append(track)
        return track


class Action:
    def __init__(self, name, frame_range=(0.0, 60.0)):
        self.name = name
        self.frame_range = frame_range
        self.slots = [SimpleNamespace(target_id_type="OBJECT")]


def _graph():
    body_starts = (0.0, 5.0, 6.0)
    body_durations = (2.0, 2.0, 2.0)
    face_starts = (0.0, 5.0)
    face_durations = (2.0, 2.0)
    body = Track(
        "Character0",
        "Motion Group",
        [
            Clip(f"body-{index}", start, duration)
            for index, (start, duration) in enumerate(zip(body_starts, body_durations))
        ],
    )
    face = Track(
        "Character0_face",
        "Face  Group",
        [
            Clip(f"face-{index}", start, duration)
            for index, (start, duration) in enumerate(zip(face_starts, face_durations))
        ],
    )
    return [Reader(body, 100), Reader(face, 200)]


def _place_track(track, target, fps=10.0):
    placements = []
    for spec in track.clips:
        frames = TIMELINE.timeline_clip_frames(spec, fps)
        action = Action(spec.display_name, (frames.action_start, frames.action_end))
        strip = HELPERS.place_action_strip(
            target,
            action,
            frames.timeline_start,
            frames.timeline_end - frames.timeline_start,
            frames.action_start,
            frames.action_end,
            track.name,
            name=spec.display_name,
        )
        placements.append((spec, frames, strip))
    return placements


def test_synthetic_timeline_preserves_authored_starts_and_gaps():
    tracks = TIMELINE.catalog_timeline_tracks(_graph())
    body_track, face_track = tracks
    body = Target("body")
    face = Target("face")

    body_placements = _place_track(body_track, body)
    face_placements = _place_track(face_track, face)

    assert [spec.start_seconds for spec in body_track.clips] == [0.0, 5.0, 6.0]
    assert [spec.start_seconds for spec in face_track.clips] == [0.0, 5.0]
    assert [strip.frame_start for _, _, strip in body_placements] == [0.0, 50.0, 60.0]
    assert [strip.frame_start for _, _, strip in face_placements] == [0.0, 50.0]
    assert body_placements[0][2].frame_end == 20.0
    assert body_placements[1][2].frame_start == 50.0
    assert body_placements[1][2].frame_start > body_placements[0][2].frame_end


def test_synthetic_timeline_overlap_allocates_separate_track():
    tracks = TIMELINE.catalog_timeline_tracks(_graph())
    body = Target("body")
    placements = _place_track(tracks[0], body)
    first = placements[1][2]
    overlap = placements[2][2]

    tracks_for_body = body.animation_data.nla_tracks
    assert first in tracks_for_body[0].strips
    assert overlap in tracks_for_body[1].strips
    assert overlap.frame_start < first.frame_end


def test_standalone_body_append_starts_after_body_endpoint_and_preserves_face():
    tracks = TIMELINE.catalog_timeline_tracks(_graph())
    body = Target("body")
    face = Target("face")
    _place_track(tracks[0], body)
    _place_track(tracks[1], face)
    face_snapshot = tuple(
        (strip.name, strip.frame_start, strip.frame_end)
        for track in face.animation_data.nla_tracks
        for strip in track.strips
    )

    append_start = HELPERS.append_start_frame(body)
    action = Action("standalone-body", (0.0, 30.0))
    appended = HELPERS.place_action_strip(
        body,
        action,
        append_start,
        action.frame_range[1] - action.frame_range[0],
        *action.frame_range,
        "Standalone Body",
        name=action.name,
    )

    assert appended.frame_start == 80.0
    assert appended.frame_start >= 80.0
    assert tuple(
        (strip.name, strip.frame_start, strip.frame_end)
        for track in face.animation_data.nla_tracks
        for strip in track.strips
    ) == face_snapshot


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_"):
            value()
    print("task 6 end-to-end tests passed")
