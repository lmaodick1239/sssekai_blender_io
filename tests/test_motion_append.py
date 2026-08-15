"""Task 5 guarded tests for standalone body motion append behavior."""

import ast
import importlib
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_PATH = ROOT / "blender/operators/importer.py"
PANEL_PATH = ROOT / "blender/panels/importer.py"
IMPORTER_SOURCE = IMPORTER_PATH.read_text(encoding="utf-8")
PANEL_SOURCE = PANEL_PATH.read_text(encoding="utf-8")


def _load_helpers():
    """Load the pure NLA helpers without requiring Blender."""
    import importlib.util
    import sys
    from types import ModuleType

    package = ModuleType("task5_helpers_package")
    package.__path__ = []
    package.logger = SimpleNamespace()
    package.register_wm_props = lambda **kwargs: None
    package.register_class = lambda value: value
    package.sssekai_global = SimpleNamespace()
    core = ModuleType("task5_helpers_package.core")
    core.__path__ = []
    math_module = ModuleType("task5_helpers_package.core.math")
    math_module.blMatrix = object
    math_module.blVector = object
    utils = ModuleType("task5_helpers_package.core.utils")
    utils.get_addon_relative_path = lambda *parts: Path(*parts)
    consts = ModuleType("task5_helpers_package.core.consts")
    consts.DEFAULT_BONE_SIZE = 0.1
    bpy = ModuleType("bpy")
    bpy.types = SimpleNamespace(
        Action=object, FCurve=object, ID=object, Object=object,
        NlaStrip=object, EditBone=object, Armature=object,
        Keyframe=object, Operator=object,
    )
    app = ModuleType("bpy.app")
    translations = ModuleType("bpy.app.translations")
    translations.pgettext = lambda value: value
    app.translations = translations
    sys.modules.update({
        package.__name__: package,
        core.__name__: core,
        math_module.__name__: math_module,
        utils.__name__: utils,
        consts.__name__: consts,
        "bpy": bpy,
        "bpy.app": app,
        "bpy.app.translations": translations,
    })
    name = "task5_helpers_package.core.helpers"
    spec = importlib.util.spec_from_file_location(name, ROOT / "blender/core/helpers.py")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "task5_helpers_package.core"
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _Strip:
    def __init__(self, end):
        self.frame_end = end


class _Target:
    def __init__(self, ends=()):
        self.animation_data = SimpleNamespace(
            nla_tracks=[SimpleNamespace(strips=[_Strip(end) for end in ends])]
        ) if ends else None


def test_append_uses_body_end_and_ignores_face_end():
    helpers = _load_helpers()
    body_target = _Target((120.0, 240.0))
    face_target = _Target((480.0,))

    assert helpers.append_start_frame(body_target) == 240.0
    assert helpers.append_start_frame(face_target) == 480.0


def test_append_empty_body_starts_at_zero():
    helpers = _load_helpers()
    assert helpers.append_start_frame(_Target()) == 0.0


class _Animation:
    Name = "body-animation"
    m_Name = "body-animation"
    SampleRate = 30

    def read(self):
        return self


class _Action:
    name = "body-action"
    frame_range = (10.0, 70.0)
    curve_frame_range = (10.0, 70.0)


class _Object(dict):
    type = "ARMATURE"

    def __init__(self, parent=None, ends=()):
        super().__init__()
        self["hierarchy_pathid"] = True
        self.parent = parent
        self.data = SimpleNamespace(edit_bones=[SimpleNamespace(name="root")])
        self.animation_data = SimpleNamespace(
            nla_tracks=[SimpleNamespace(strips=[SimpleNamespace(frame_end=end) for end in ends])]
        ) if ends else None


class _Controller(_Object):
    def __init__(self):
        super().__init__()
        self.lookups = []

    def get(self, key, default=None):
        self.lookups.append(key)
        return super().get(key, default)


class _FaceTarget(_Object):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.observations = []
        self.shape_keys = {"smile": 0.25}

    def __getattribute__(self, name):
        if name in {"animation_data", "shape_keys", "parent"}:
            observations = object.__getattribute__(self, "__dict__").get("observations")
            if observations is not None:
                observations.append(("read", name))
        return super().__getattribute__(name)

    def __setattr__(self, name, value):
        if name in {"animation_data", "shape_keys", "parent"}:
            observations = self.__dict__.get("observations")
            if observations is not None:
                observations.append(("write", name, value))
        super().__setattr__(name, value)


class _Container:
    animations = [_Animation()]


def _load_operator_class():
    """Load only the Task 5 operator class, avoiding Blender and UnityPy imports."""
    tree = ast.parse(IMPORTER_SOURCE)
    class_node = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "SSSekaiBlenderImportHierarchyAnimationOperaotr"
    )
    module = ModuleType("task5_operator_under_test")
    bpy = SimpleNamespace(
        types=SimpleNamespace(Operator=object),
        context=None,
        ops=SimpleNamespace(object=SimpleNamespace(mode_set=lambda **kwargs: None)),
    )
    constants = {
        "KEY_HIERARCHY_BONE_PATHID": "hierarchy_pathid",
        "KEY_HIERARCHY_BONE_ROOT": "hierarchy_root",
        "KEY_HIERARCHY_BONE_NAME": "unity_name",
        "KEY_SEKAI_CHARACTER_BODY_OBJ": "body",
        "UNITY_MECANIM_RESERVED_TOS": {},
    }
    globals_for_class = {
        "bpy": bpy,
        "T": lambda value: value,
        "register_class": lambda value: value,
        "ensure_sssekai_shader_blend": lambda: None,
        "armature_editbone_children_recursive": lambda data: [],
        "editbone_children_recursive": lambda bone: [],
        "apply_pose_matrix": lambda *args: None,
        "read_animation": lambda animation: animation,
        "load_armature_animation": lambda *args: _Action(),
        "append_start_frame": lambda target: max(
            (strip.frame_end for track in (target.animation_data.nla_tracks if target.animation_data else [])
             for strip in track.strips), default=0.0
        ),
        "place_action_strip": None,
        "apply_action": None,
        "crc32": lambda value: value,
        "logger": SimpleNamespace(info=lambda *args: None),
        "sssekai_global": SimpleNamespace(containers={"0": _Container()}),
        **constants,
    }
    exec(compile(ast.Module(body=[class_node], type_ignores=[]), str(IMPORTER_PATH), "exec"), globals_for_class, module.__dict__)
    module.__dict__.update(globals_for_class)
    return module.SSSekaiBlenderImportHierarchyAnimationOperaotr, globals_for_class


def _operator_flow(append=True, body_ends=(120.0, 240.0), face_end=480.0):
    operator, scope = _load_operator_class()
    body = _Object(ends=body_ends)
    face = _FaceTarget(ends=(face_end,))
    controller = _Controller()
    controller["body"] = body
    controller["face"] = face
    body.parent = controller
    face_state = {"shape_keys": dict(face.shape_keys), "nla": tuple(face.animation_data.nla_tracks[0].strips)}
    face.observations.clear()
    placements = []
    applied = []

    def place(target, action, start, duration, action_start, action_end, group, name=None):
        strip = SimpleNamespace(
            target=target, frame_start=start, frame_end=start + duration,
            action_frame_start=action_start, action_frame_end=action_end,
            group=group, name=name,
        )
        placements.append(strip)
        return strip

    def apply(target, action, use_nla, always_new):
        applied.append((target, action, use_nla, always_new))

    scope["place_action_strip"] = place
    scope["apply_action"] = apply
    scene = SimpleNamespace(
        render=SimpleNamespace(fps=24), frame_end=100,
        rigidbody_world=SimpleNamespace(point_cache=SimpleNamespace(frame_end=110)),
    )
    scope["bpy"].context = SimpleNamespace(
        scene=scene, view_layer=SimpleNamespace(objects=SimpleNamespace(active=None))
    )
    wm = SimpleNamespace(
        sssekai_animation_use_animator=False,
        sssekai_animation_root_bone="",
        sssekai_selected_animator_container="0",
        sssekai_selected_animator="0",
        sssekai_selected_animation_container="0",
        sssekai_selected_animation="0",
        sssekai_animation_import_use_scene_fps=True,
        sssekai_animation_import_use_nla=True,
        sssekai_animation_import_nla_always_new_track=True,
        sssekai_animation_append_exisiting=append,
    )
    context = SimpleNamespace(window_manager=wm, active_object=body, scene=scene)
    op = operator()
    reports = []
    op.report = lambda level, message: reports.append((level, message))
    result = op.execute(context)
    assert controller.lookups == (["body"] if append else [])
    assert face.observations == []
    assert face_state == {"shape_keys": dict(face.shape_keys), "nla": tuple(face.animation_data.nla_tracks[0].strips)}
    return result, body, face, scene, placements, applied, reports


def test_standalone_body_append_executes_full_action_at_body_endpoint():
    result, body, face, scene, placements, applied, reports = _operator_flow()
    assert result == {"FINISHED"}
    assert len(placements) == 1
    strip = placements[0]
    assert strip.target is body
    assert strip.frame_start == 240.0
    assert strip.frame_end == 300.0
    assert strip.action_frame_start == 10.0
    assert strip.action_frame_end == 70.0
    assert not applied
    assert scene.frame_end == 300
    assert scene.rigidbody_world.point_cache.frame_end == 300


def test_standalone_body_append_uses_zero_for_empty_body_and_ignores_face_endpoint():
    result, body, face, scene, placements, applied, reports = _operator_flow(
        body_ends=(), face_end=999.0
    )
    assert result == {"FINISHED"}
    assert placements[0].frame_start == 0.0
    assert placements[0].frame_end == 60.0
    assert placements[0].target is not face


def test_standalone_body_import_keeps_non_append_apply_path():
    result, body, face, scene, placements, applied, reports = _operator_flow(append=False)
    assert result == {"FINISHED"}
    assert not placements
    assert len(applied) == 1
    assert applied[0][0] is body
    assert applied[0][2:] == (True, True)
    assert scene.frame_end == 100
    assert scene.rigidbody_world.point_cache.frame_end == 110


def test_append_branch_is_task5_specific_and_has_no_task6_collision_assertion():
    tree = ast.parse(IMPORTER_SOURCE)
    operator = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SSSekaiBlenderImportHierarchyAnimationOperaotr")
    source = ast.unparse(operator)
    assert "append_start_frame(active_obj)" in source
    assert "imported_end = strip.frame_end" in source
    frame_range_assignments = [
        node
        for node in ast.walk(operator)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "frame_range"
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Tuple)
        and [elt.id for elt in node.targets[0].elts if isinstance(elt, ast.Name)] == [
            "action_start", "action_end"
        ]
    ]
    assert frame_range_assignments
    assert "largest_end" not in source


def test_append_branch_never_reads_or_mutates_face_target():
    _operator_flow(body_ends=(240.0,), face_end=999.0)


def test_append_property_is_exposed_by_import_panel_with_legacy_spelling():
    assert "sssekai_animation_append_exisiting=BoolProperty" in PANEL_SOURCE
    assert 'row.prop(wm, "sssekai_animation_append_exisiting"' in PANEL_SOURCE


def test_blender_registration_and_panel_draw_when_available():
    bpy = pytest.importorskip("bpy")
    panel = importlib.import_module("sssekai_blender_io.blender.panels.importer")
    operators = importlib.import_module("sssekai_blender_io.blender.operators.importer")
    panel_class = panel.SSSekaiBlenderImportPanel
    operator_class = operators.SSSekaiBlenderImportHierarchyAnimationOperaotr

    bpy.utils.register_class(panel_class)
    bpy.utils.register_class(operator_class)
    try:
        class _Layout:
            def row(self):
                return self

            def label(self, **kwargs):
                return None

            def prop(self, **kwargs):
                return None

            def operator(self, **kwargs):
                return None

        wm = SimpleNamespace(
            sssekai_import_type="IMPORT_ANIMATION",
            sssekai_unity_version_override="",
            sssekai_selected_assetbundle_file="",
            sssekai_selected_assetbundle_file_aux="",
            sssekai_selected_animation_container="0",
            sssekai_selected_animation="0",
            sssekai_selected_animator_container="0",
            sssekai_selected_animator="0",
            sssekai_animation_append_exisiting=False,
            sssekai_animation_import_use_nla=True,
            sssekai_animation_import_nla_always_new_track=True,
        )
        instance = panel_class()
        instance.layout = _Layout()
        instance.draw(SimpleNamespace(window_manager=wm, active_object=None))
    finally:
        bpy.utils.unregister_class(operator_class)
        bpy.utils.unregister_class(panel_class)


def test_non_append_legacy_apply_path_remains_present():
    assert "apply_action(" in IMPORTER_SOURCE
    assert "wm.sssekai_animation_import_use_nla" in IMPORTER_SOURCE
    assert "wm.sssekai_animation_import_nla_always_new_track" in IMPORTER_SOURCE
