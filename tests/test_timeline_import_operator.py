"""Task 4 operator-flow tests.

The executable doubles run the real Timeline operator control flow without Blender.
Blender-only tests remain guarded for registration, NLA, and Action-slot behavior.
"""

from pathlib import Path
import ast
import importlib.util
import sys
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
OPERATOR_SOURCE = ROOT / "blender/operators/importer.py"
PANEL_SOURCE = ROOT / "blender/panels/importer.py"


def _source_tree(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class(tree, name):
    return next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)


def _method(class_node, name):
    return next(node for node in class_node.body if isinstance(node, ast.FunctionDef) and node.name == name)


def test_timeline_operator_and_explicit_pairing_contract_exists():
    tree = _source_tree(OPERATOR_SOURCE)
    operator = _class(tree, "SSSekaiBlenderImportSekaiTimelineOperator")
    assignments = {
        node.targets[0].id: node.value.value
        for node in operator.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
    }
    assert assignments["bl_idname"] == "sssekai.import_sekai_timeline_op"
    assert {"sssekai_selected_motion_track", "sssekai_selected_face_track"} <= {
        node.attr for node in ast.walk(_method(operator, "execute")) if isinstance(node, ast.Attribute)
    }
    source = ast.unparse(operator)
    assert "timeline_track_by_id" in source
    assert "place_action_strip" in source
    assert "append_start_frame" not in source
    assert "action_curve_count" in source


def test_timeline_properties_and_panel_keep_standalone_animation_controls():
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    assert "sssekai_selected_motion_track" in source
    assert "sssekai_import_matching_face_track" in source
    assert "sssekai_selected_face_track" in source
    assert "SSSekaiBlenderImportSekaiTimelineOperator" in source
    assert '"IMPORT_TIMELINE"' in source
    assert '"IMPORT_ANIMATION"' in source
    assert "SSSekaiBlenderImportSekaiCharacterMotionOperator" in source
    assert "SSSekaiBlenderImportSekaiCharacterFaceMotionOperator" in source
    timeline_block = source.split('case "IMPORT_TIMELINE":', 1)[1].split('case "IMPORT_ANIMATION":', 1)[0]
    assert "row.enabled" not in timeline_block


class FakeAction:
    def __init__(self, name, curves=1):
        self.name = name
        self.frame_range = (0.0, 30.0)
        self.curves = [object()] * curves
        self.users = 0


class FakeReader:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error

    def read(self):
        if self.error:
            raise self.error
        return self.value


class FakeSpec:
    def __init__(self, name, order=0, reader=None, warning=None, validation_error=None):
        self.display_name = name
        self.source_order = order
        self.animation_reader = reader or FakeReader(name)
        self.warning = warning
        self.validation_error = validation_error


class FakeTrack:
    def __init__(self, name, kind, *clips):
        self.name = name
        self.kind = kind
        self.clips = list(clips)
        self.source_id = name
        self.diagnostics = ()


class FakeObject:
    def __init__(self, name, object_type):
        self.name = name
        self.type = object_type
        self.mode = "OBJECT"
        self.active_when_loaded = None


class FakeController(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "SekaiCharacterRoot"
        self.type = "EMPTY"
        self.mode = "OBJECT"
        self.view_layer_objects = None


def _load_operator_class():
    """Compile only the production operator class with dependency doubles."""
    tree = _source_tree(OPERATOR_SOURCE)
    class_node = _class(tree, "SSSekaiBlenderImportSekaiTimelineOperator")
    module = ast.Module(body=[class_node], type_ignores=[])
    view_layer_objects = SimpleNamespace(active=None)
    bpy = SimpleNamespace(
        types=SimpleNamespace(Operator=object),
        data=SimpleNamespace(actions=[]),
        context=SimpleNamespace(
            view_layer=SimpleNamespace(objects=view_layer_objects),
        ),
    )
    bpy.ops = SimpleNamespace(
        object=SimpleNamespace(
            mode_set=lambda mode: setattr(
                bpy.context.view_layer.objects.active, "mode", mode
            ),
        ),
    )
    namespace = {
        "bpy": bpy,
        "T": lambda text: text,
        "register_class": lambda value: value,
        "logger": SimpleNamespace(error=lambda *_args, **_kwargs: None),
        "sssekai_global": SimpleNamespace(
            timeline_tracks=[], env_path="", env_aux_path=""
        ),
        "KEY_SEKAI_CHARACTER_ROOT": "root",
        "KEY_SEKAI_CHARACTER_BODY_OBJ": "body",
        "KEY_SEKAI_CHARACTER_FACE_OBJ": "face",
        "KEY_HIERARCHY_BONE_NAME": "unity_name",
        "KEY_SHAPEKEY_HASH_TABEL": "hash_table",
        "crc32": lambda value: hash(value),
        "json": __import__("json"),
        "timeline_clip_frames": lambda spec, fps: SimpleNamespace(
            timeline_start=float(spec.source_order * 60),
            timeline_end=float(spec.source_order * 60 + 30),
            action_start=0.0,
            action_end=30.0,
        ),
    }
    exec(compile(module, str(OPERATOR_SOURCE), "exec"), namespace)
    return namespace["SSSekaiBlenderImportSekaiTimelineOperator"]


def _operator_harness(
    motion=None,
    face=None,
    paired=False,
    body=True,
    face_target=True,
    body_loader=None,
    face_loader=None,
    body_endpoint=0.0,
    face_endpoint=0.0,
):
    Operator = _load_operator_class()
    tracks = {track.source_id: track for track in (motion, face) if track}
    Operator.execute.__globals__["sssekai_global"].timeline_tracks = list(tracks.values())
    placements = []
    reports = []
    loads = []

    def track_lookup(track_id, expected_kind):
        if not track_id:
            return None
        track = tracks.get(track_id)
        if track is None or track.kind != expected_kind:
            raise ValueError("unavailable track")
        return track

    action_store = Operator.execute.__globals__["bpy"].data.actions

    def load_body(name, animation, target, mapping):
        target.active_when_loaded = context.view_layer.objects.active is target
        action = body_loader(name, animation, target, mapping) if body_loader else FakeAction(name)
        action_store.append(action)
        loads.append(("body", name, target))
        return action

    def load_face(name, animation, mapping):
        action = face_loader(name, animation, mapping) if face_loader else FakeAction(name)
        action_store.append(action)
        loads.append(("face", name, mapping))
        return action

    def place(target, action, start, duration, action_start, action_end, group, name=None):
        strip = SimpleNamespace(
            frame_start=start,
            frame_end=start + duration,
            target=target,
            action=action,
            group=group,
            name=name,
        )
        placements.append(strip)
        return strip

    Operator._track = staticmethod(track_lookup)
    Operator._body_tos_leaf = staticmethod(lambda target: {"root": "root"})
    Operator._face_target = staticmethod(lambda target: (target, {"1": "Smile"}))
    globals_for_execute = Operator.execute.__globals__
    globals_for_execute.update({
        "read_animation": lambda value: value,
        "load_armature_animation": load_body,
        "load_sekai_keyshape_animation": load_face,
        "action_curve_count": lambda action: len(action.curves),
        "timeline_clip_frames": globals_for_execute["timeline_clip_frames"],
        "validate_timeline_clip": lambda spec, frame_range, fps: (
            (_ for _ in ()).throw(ValueError(spec.validation_error))
            if spec.validation_error
            else [spec.warning] if spec.warning else []
        ),
        "append_start_frame": lambda target: (
            body_endpoint if target is controller["body"] else face_endpoint
        ),
        "place_action_strip": place,
        "math": __import__("math"),
    })
    controller = FakeController(root=True)
    controller["body"] = FakeObject("body", "ARMATURE") if body else None
    controller["face"] = FakeObject("face", "ARMATURE") if face_target else None
    wm = SimpleNamespace(
        sssekai_selected_motion_track=motion.source_id if motion else "",
        sssekai_selected_face_track=face.source_id if face else "",
        sssekai_import_matching_face_track=paired,
    )
    scene = SimpleNamespace(render=SimpleNamespace(fps=30), frame_end=1, rigidbody_world=None)
    view_layer_objects = SimpleNamespace(active=controller)
    controller.view_layer_objects = view_layer_objects
    context = SimpleNamespace(
        window_manager=wm,
        active_object=controller,
        scene=scene,
        mode="OBJECT",
        view_layer=SimpleNamespace(objects=view_layer_objects),
    )
    Operator.execute.__globals__["bpy"].context.view_layer = context.view_layer
    operator = Operator()
    operator.reports = reports
    operator.report = lambda level, message: reports.append((level, message))
    result = operator.execute(context)
    return result, placements, reports, loads, controller, action_store


def test_body_only_ignores_stale_face_selection_and_face_target():
    body = FakeTrack("motion", "MOTION", FakeSpec("body-clip"))
    stale_face = FakeTrack("stale-face", "FACE", FakeSpec("face-clip"))
    result, placements, reports, loads, controller, actions = _operator_harness(body, stale_face)
    assert result == {"FINISHED"}
    assert [kind for kind, _, _ in loads] == ["body"]
    assert all(strip.target is controller["body"] for strip in placements)
    assert controller["face"] not in [strip.target for strip in placements]


def test_body_armature_is_active_during_motion_load_and_controller_is_restored():
    body = FakeTrack("motion", "MOTION", FakeSpec("body-clip"))

    result, placements, reports, loads, controller, actions = _operator_harness(body)

    assert result == {"FINISHED"}
    assert controller["body"].active_when_loaded is True
    assert controller.view_layer_objects.active is controller
    assert controller.mode == "OBJECT"


def test_face_only_is_reachable_without_motion_or_pairing():
    face = FakeTrack("face", "FACE", FakeSpec("face-clip"))
    result, placements, reports, loads, controller, actions = _operator_harness(None, face)
    assert result == {"FINISHED"}
    assert [kind for kind, _, _ in loads] == ["face"]
    assert placements[0].target is controller["face"]


def test_paired_import_uses_independent_targets_and_synchronized_starts():
    body = FakeTrack("motion", "MOTION", FakeSpec("body-clip", order=0))
    face = FakeTrack("face", "FACE", FakeSpec("face-clip", order=0))
    result, placements, reports, loads, controller, actions = _operator_harness(body, face, paired=True)
    assert result == {"FINISHED"}
    assert {strip.target for strip in placements} == {controller["body"], controller["face"]}
    assert {strip.frame_start for strip in placements} == {0.0}


def test_timeline_import_preserves_authored_starts_despite_existing_body_and_face_strips():
    body = FakeTrack(
        "motion",
        "MOTION",
        FakeSpec("body-clip", order=0),
        FakeSpec("body-only", order=1),
    )
    face = FakeTrack("face", "FACE", FakeSpec("face-clip", order=0))

    result, placements, reports, loads, controller, actions = _operator_harness(
        body,
        face,
        paired=True,
        body_endpoint=240.0,
        face_endpoint=480.0,
    )

    assert result == {"FINISHED"}
    assert [(strip.name, strip.frame_start) for strip in placements] == [
        ("body-clip", 0.0),
        ("face-clip", 0.0),
        ("body-only", 60.0),
    ]


def test_invalid_clip_is_skipped_and_summary_identifies_track_and_clip():
    body = FakeTrack("motion", "MOTION", FakeSpec("broken", reader=FakeReader(error=ValueError("bad clip"))))
    result, placements, reports, loads, controller, actions = _operator_harness(body)
    assert result == {"CANCELLED"}
    assert not placements
    assert any("motion / broken" in message and "skipped=1" in message for _, message in reports)


def test_empty_body_action_is_removed_without_empty_strip():
    body = FakeTrack("motion", "MOTION", FakeSpec("empty"))
    result, placements, reports, loads, controller, actions = _operator_harness(
        body, body_loader=lambda *args: FakeAction("empty", curves=0)
    )
    assert result == {"CANCELLED"}
    assert not placements
    assert not actions
    assert any("generated body Action has no curves" in message for _, message in reports)


def test_invalid_face_action_is_removed_when_face_only_import_is_cancelled():
    face = FakeTrack("face", "FACE", FakeSpec("invalid", validation_error="source window outside Action"))

    result, placements, reports, loads, controller, actions = _operator_harness(None, face)

    assert result == {"CANCELLED"}
    assert not placements
    assert not actions


def test_empty_face_action_is_removed_without_empty_strip():
    face = FakeTrack("face", "FACE", FakeSpec("empty-face"))

    result, placements, reports, loads, controller, actions = _operator_harness(
        None,
        face,
        face_loader=lambda *args: FakeAction("empty-face", curves=0),
    )

    assert result == {"CANCELLED"}
    assert not placements
    assert not actions


def test_invalid_referenced_action_is_not_removed():
    body = FakeTrack("motion", "MOTION", FakeSpec("referenced", validation_error="bad body window"))
    referenced = FakeAction("referenced")
    referenced.users = 1

    result, placements, reports, loads, controller, actions = _operator_harness(
        body,
        body_loader=lambda *args: referenced,
    )

    assert result == {"CANCELLED"}
    assert not placements
    assert actions == [referenced]


def test_cancelled_paired_import_removes_prepared_face_action_after_invalid_body():
    body = FakeTrack("motion", "MOTION", FakeSpec("invalid-body", validation_error="bad body window"))
    face = FakeTrack("face", "FACE", FakeSpec("valid-face"))

    result, placements, reports, loads, controller, actions = _operator_harness(body, face, paired=True)

    assert result == {"CANCELLED"}
    assert not placements
    assert not actions


@pytest.mark.parametrize("paired", [False, True])
def test_face_selection_requires_motion_only_when_pairing_is_explicit(paired):
    face = FakeTrack("face", "FACE", FakeSpec("face-clip"))
    result, placements, reports, loads, controller, actions = _operator_harness(None, face, paired=paired)
    if paired:
        assert result == {"CANCELLED"}
        assert not placements
    else:
        assert result == {"FINISHED"}


def test_guarded_bpy_properties_and_operator_registration():
    bpy = pytest.importorskip("bpy")
    import sssekai_blender_io.blender.panels.importer as importer_panel
    import sssekai_blender_io.blender.operators.importer as importer_operator
    del importer_panel, importer_operator
    assert bpy.types.WindowManager.bl_rna.properties.get("sssekai_selected_motion_track") is not None
    assert bpy.types.WindowManager.bl_rna.properties.get("sssekai_selected_face_track") is not None
    assert hasattr(bpy.ops.sssekai, "import_sekai_timeline_op")


def test_guarded_blender_face_action_tests_are_available():
    pytest.importorskip("bpy")
    face_tests = ROOT / "tests/test_blender5_face_action.py"
    assert face_tests.exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
