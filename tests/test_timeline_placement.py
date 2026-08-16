"""Task 2 tests that run without a Blender or pytest runtime."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _load_timeline():
    module_name = "task2_timeline_under_test"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "blender/core/timeline.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_helpers():
    """Load helpers with only its Blender-facing imports replaced by doubles."""
    package = ModuleType("task2_helpers_package")
    package.__path__ = []
    package.logger = SimpleNamespace()
    package.register_wm_props = lambda **kwargs: None
    package.register_class = lambda value: value
    package.sssekai_global = SimpleNamespace()
    core_package = ModuleType("task2_helpers_package.core")
    core_package.__path__ = []
    math_module = ModuleType("task2_helpers_package.core.math")
    math_module.blMatrix = object
    math_module.blVector = object
    utils_module = ModuleType("task2_helpers_package.core.utils")
    utils_module.get_addon_relative_path = lambda *parts: Path(*parts)
    consts_module = ModuleType("task2_helpers_package.core.consts")
    consts_module.DEFAULT_BONE_SIZE = 0.1
    sys.modules.update(
        {
            package.__name__: package,
            core_package.__name__: core_package,
            math_module.__name__: math_module,
            utils_module.__name__: utils_module,
            consts_module.__name__: consts_module,
        }
    )

    bpy_module = ModuleType("bpy")
    bpy_module.types = SimpleNamespace(
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
    bpy_module.app = SimpleNamespace()
    translations_module = ModuleType("bpy.app.translations")
    translations_module.pgettext = lambda value: value
    app_module = ModuleType("bpy.app")
    app_module.translations = translations_module
    prior_modules = {
        name: sys.modules.get(name)
        for name in ("bpy", "bpy.app", "bpy.app.translations")
    }
    sys.modules.update(
        {"bpy": bpy_module, "bpy.app": app_module, "bpy.app.translations": translations_module}
    )

    module_name = "task2_helpers_package.core.helpers"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "blender/core/helpers.py", submodule_search_locations=[]
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "task2_helpers_package.core"
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    for name, prior in prior_modules.items():
        if prior is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prior
    return module


TIMELINE = _load_timeline()
HELPERS = _load_helpers()


class FakeStrip:
    def __init__(self, name, frame_start, action):
        self.name = name
        self.frame_start = frame_start
        self.frame_end = frame_start
        self.action = action
        self.action_frame_start = None
        self.action_frame_end = None
        self.influence = 0.0
        self.action_slot = None


class FakeStrips(list):
    def new(self, name, frame_start, action):
        strip = FakeStrip(name, frame_start, action)
        self.append(strip)
        return strip


class FakeTrack:
    def __init__(self):
        self.name = ""
        self.strips = FakeStrips()


class FakeTracks(list):
    def new(self):
        track = FakeTrack()
        self.append(track)
        return track


class FakeTarget:
    id_type = "OBJECT"

    def __init__(self):
        self.name = "target"
        self.animation_data = None

    def animation_data_create(self):
        self.animation_data = SimpleNamespace(nla_tracks=FakeTracks())
        return self.animation_data


class FakeAction:
    def __init__(self, name="action", frame_range=(10.25, 90.75), slot_type="OBJECT"):
        self.name = name
        self.frame_range = frame_range
        self.slots = [SimpleNamespace(target_id_type=slot_type)]


def _spec(**changes):
    values = dict(
        source_id=1,
        display_name="clip",
        animation_reader=None,
        start_seconds=2.5,
        duration_seconds=3.0,
        clip_in_seconds=0.5,
        time_scale=2.0,
        transition_metadata={},
        extrapolation_metadata={},
        playable_metadata={},
        source_order=0,
    )
    values.update(changes)
    return TIMELINE.TimelineClipSpec(**values)


def _raises(error_type, callback):
    try:
        callback()
    except error_type:
        return
    raise AssertionError(f"expected {error_type.__name__}")


def test_timeline_frames_use_scene_fps_for_all_times():
    frames = TIMELINE.timeline_clip_frames(_spec(), fps=30.0)

    assert frames.timeline_start == 75.0
    assert frames.timeline_end == 165.0
    assert frames.action_start == 15.0
    assert frames.action_end == 195.0


def test_timeline_frames_reject_invalid_duration_scale_and_clip_in():
    _raises(ValueError, lambda: TIMELINE.timeline_clip_frames(_spec(duration_seconds=0), 30.0))
    _raises(ValueError, lambda: TIMELINE.timeline_clip_frames(_spec(time_scale=-1), 30.0))
    _raises(ValueError, lambda: TIMELINE.timeline_clip_frames(_spec(clip_in_seconds=-0.1), 30.0))
    for field in ("start_seconds", "duration_seconds", "clip_in_seconds", "time_scale"):
        for invalid in (float("nan"), float("inf"), float("-inf")):
            _raises(
                ValueError,
                lambda field=field, invalid=invalid: TIMELINE.timeline_clip_frames(
                    _spec(**{field: invalid}), 30.0
                ),
            )
    for fps in (float("nan"), float("inf"), float("-inf")):
        _raises(ValueError, lambda fps=fps: TIMELINE.timeline_clip_frames(_spec(), fps))


def test_validation_accepts_positive_clip_in_with_full_source_action_range():
    spec = _spec(clip_in_seconds=0.5, duration_seconds=1.0, time_scale=1.0)

    assert TIMELINE.validate_timeline_clip(spec, (0.0, 90.0), 30.0) == []


def test_validation_rejects_requested_window_outside_action_and_returns_semantic_warnings():
    spec = _spec(
        transition_metadata={"m_EaseInDuration": 0.25, "m_MixInCurve": {"key": 1}},
        extrapolation_metadata={"m_PostExtrapolationMode": "Loop"},
        playable_metadata={
            "m_Loop": True,
            "m_MatchTargetFields": 1,
            "m_ApplyFootIK": True,
        },
    )
    warnings = TIMELINE.validate_timeline_clip(spec, (0.0, 195.0), 30.0)

    assert warnings
    warning_text = " ".join(warnings).lower()
    assert "blend" in warning_text or "ease" in warning_text
    assert "loop" in warning_text
    assert "extrapolation" in warning_text
    assert "root" in warning_text or "match" in warning_text
    assert "foot" in warning_text
    _raises(
        ValueError,
        lambda: TIMELINE.validate_timeline_clip(spec, (0.0, 194.0), 30.0),
    )


def test_validation_ignores_empty_serialized_mix_curves_but_warns_for_curve_keys():
    empty_curve = _spec(
        transition_metadata={
            "m_MixInCurve": {"m_Curve": []},
            "m_MixOutCurve": {"m_Curve": ()},
        }
    )
    keyed_curve = _spec(transition_metadata={"m_MixInCurve": {"m_Curve": [{"time": 0.0}]}})

    assert TIMELINE.validate_timeline_clip(empty_curve, (0.0, 195.0), 30.0) == []
    assert any(
        "mix" in warning.lower()
        for warning in TIMELINE.validate_timeline_clip(keyed_curve, (0.0, 195.0), 30.0)
    )


def test_validation_warns_for_nondefault_hold_extrapolation():
    spec = _spec(extrapolation_metadata={"m_PostExtrapolationMode": "Hold"})

    warnings = TIMELINE.validate_timeline_clip(spec, (15.0, 195.0), 30.0)

    assert any("extrapolation" in warning.lower() for warning in warnings)


def test_validation_accepts_documented_default_extrapolation_sentinel():
    spec = _spec(extrapolation_metadata={"m_PostExtrapolationMode": "None"})

    assert TIMELINE.validate_timeline_clip(spec, (15.0, 195.0), 30.0) == []


def test_validation_accepts_action_range_with_small_float_tolerance():
    warnings = TIMELINE.validate_timeline_clip(_spec(), (15.0005, 194.9995), 30.0)

    assert warnings == []


def test_place_action_strip_reuses_gap_and_separates_overlap_without_truncation():
    target = FakeTarget()
    action = FakeAction()
    first = HELPERS.place_action_strip(
        target, action, 0.25, 100.5, 10.25, 90.75, "Motion Group", name="first"
    )
    overlap = HELPERS.place_action_strip(
        target, action, 50.5, 5.25, 10.25, 90.75, "Motion Group", name="overlap"
    )
    gap = HELPERS.place_action_strip(
        target, action, 200.5, 5.25, 10.25, 90.75, "Motion Group", name="gap"
    )

    tracks = target.animation_data.nla_tracks
    assert len(tracks) == 2
    assert first.frame_start == 0.25
    assert first.frame_end == 100.75
    assert first.action_frame_start == 10.25
    assert first.action_frame_end == 90.75
    assert gap in tracks[0].strips
    assert overlap in tracks[1].strips
    assert gap.frame_start == 200.5
    assert gap.frame_end == 205.75
    assert first.influence > 0.0


def test_append_start_frame_isolated_to_target_nla_tracks():
    body = FakeTarget()
    face = FakeTarget()
    action = FakeAction()
    HELPERS.place_action_strip(body, action, 0.0, 240.0, 0.0, 240.0, "body")
    HELPERS.place_action_strip(face, action, 0.0, 480.0, 0.0, 480.0, "face")

    assert HELPERS.append_start_frame(body) == 240.0
    assert HELPERS.append_start_frame(face) == 480.0
    assert HELPERS.append_start_frame(FakeTarget()) == 0.0


def test_place_action_strip_rejects_nonfinite_frame_values():
    for field in ("timeline_start", "timeline_duration", "action_start", "action_end"):
        for invalid in (float("nan"), float("inf"), float("-inf")):
            values = dict(
                timeline_start=1.5,
                timeline_duration=2.25,
                action_start=10.25,
                action_end=12.5,
                track_group="Motion Group",
            )
            values[field] = invalid
            _raises(
                ValueError,
                lambda values=values: HELPERS.place_action_strip(
                    FakeTarget(), FakeAction(), **values
                ),
            )


def test_place_action_strip_binds_compatible_action_slot():
    target = FakeTarget()
    action = FakeAction(slot_type="OBJECT")

    strip = HELPERS.place_action_strip(
        target, action, 1.5, 2.25, 10.25, 12.5, "Motion Group"
    )

    assert strip.action_slot is action.slots[0]


def test_place_action_strip_binds_key_slot_for_ordered_face_placements():
    target = FakeTarget()
    action = FakeAction(name="face-action", slot_type="KEY")
    target.id_type = "KEY"

    strip = HELPERS.place_action_strip(
        target, action, 0.25, 2.25, 10.25, 12.5, "Face Group"
    )

    assert strip.action_slot is action.slots[0]


if __name__ == "__main__":
    for name, test in sorted(globals().items()):
        if name.startswith("test_"):
            test()
    print("task-2 placement harness: PASS")
