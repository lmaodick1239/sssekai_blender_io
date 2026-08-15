"""Task 5 guarded tests for standalone body motion append behavior."""

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SOURCE = (ROOT / "blender/operators/importer.py").read_text()
PANEL_SOURCE = (ROOT / "blender/panels/importer.py").read_text()


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


def test_standalone_body_append_places_full_action_without_clip_in():
    tree = ast.parse(IMPORTER_SOURCE)
    assert "sssekai_animation_append_exisiting" in IMPORTER_SOURCE
    assert "place_action_strip" in IMPORTER_SOURCE
    assert "append_start_frame" in IMPORTER_SOURCE
    assert "action_start, action_end = action.frame_range" in IMPORTER_SOURCE
    assert "action_start,\n                action_end," in IMPORTER_SOURCE
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "place_action_strip"
        for node in ast.walk(tree)
    )


def test_append_extends_scene_from_appended_strip_and_does_not_touch_face():
    assert "largest_end =" in IMPORTER_SOURCE
    assert "strip.frame_end" in IMPORTER_SOURCE
    assert "rigidbody_world.point_cache.frame_end" in IMPORTER_SOURCE
    assert "face.data.shape_keys" not in IMPORTER_SOURCE


def test_append_property_is_exposed_by_import_panel_with_legacy_spelling():
    assert "sssekai_animation_append_exisiting=BoolProperty" in PANEL_SOURCE
    assert 'row.prop(wm, "sssekai_animation_append_exisiting"' in PANEL_SOURCE


def test_non_append_legacy_apply_path_remains_present():
    assert "apply_action(" in IMPORTER_SOURCE
    assert "wm.sssekai_animation_import_use_nla" in IMPORTER_SOURCE
    assert "wm.sssekai_animation_import_nla_always_new_track" in IMPORTER_SOURCE
