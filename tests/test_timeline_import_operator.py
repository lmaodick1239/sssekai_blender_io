"""Task 4 operator contract tests.

These tests are intentionally guarded because the repository has no local Blender
runtime. The source-contract tests run everywhere; bpy integration tests run only
inside Blender with pytest available.
"""

from pathlib import Path
import ast

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


def _names(node):
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


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
        node.attr
        for node in ast.walk(_method(operator, "execute"))
        if isinstance(node, ast.Attribute)
    }
    operator_source = ast.unparse(operator)
    assert "timeline_track_by_id" in operator_source
    assert "place_action_strip" in operator_source
    assert "append_start_frame" in operator_source
    assert "mvdata" not in OPERATOR_SOURCE.read_text(encoding="utf-8").lower()


def test_timeline_operator_uses_independent_body_and_face_targets():
    tree = _source_tree(OPERATOR_SOURCE)
    operator = _class(tree, "SSSekaiBlenderImportSekaiTimelineOperator")
    source = ast.unparse(operator)
    assert "KEY_SEKAI_CHARACTER_BODY_OBJ" in source
    assert "KEY_SEKAI_CHARACTER_FACE_OBJ" in source
    assert "shape_keys" in source
    assert "load_armature_animation" in source
    assert "load_sekai_keyshape_animation" in source
    assert "action_curve_count" in source
    assert "read_animation" in source


def test_timeline_properties_and_panel_keep_standalone_animation_controls():
    panel_source = PANEL_SOURCE.read_text(encoding="utf-8")
    assert "sssekai_selected_motion_track" in panel_source
    assert "sssekai_import_matching_face_track" in panel_source
    assert "sssekai_selected_face_track" in panel_source
    assert "SSSekaiBlenderImportSekaiTimelineOperator" in panel_source
    assert '"IMPORT_TIMELINE"' in panel_source
    assert '"IMPORT_ANIMATION"' in panel_source
    assert "SSSekaiBlenderImportSekaiCharacterMotionOperator" in panel_source
    assert "SSSekaiBlenderImportSekaiCharacterFaceMotionOperator" in panel_source


def test_guarded_bpy_properties_are_registered_with_expected_defaults():
    bpy = pytest.importorskip("bpy")
    import sssekai_blender_io.blender.panels.importer as importer_panel

    del importer_panel
    properties = bpy.types.WindowManager.bl_rna.properties
    assert properties.get("sssekai_selected_motion_track") is not None
    assert properties.get("sssekai_import_matching_face_track") is not None
    assert properties.get("sssekai_selected_face_track") is not None

    wm = bpy.context.window_manager
    assert wm.sssekai_import_matching_face_track is False


def test_guarded_bpy_operator_is_registered():
    bpy = pytest.importorskip("bpy")
    import sssekai_blender_io.blender.operators.importer as importer_operator

    del importer_operator
    assert hasattr(bpy.ops.sssekai, "import_sekai_timeline_op")


def test_guarded_bpy_operator_requires_explicit_face_selection():
    bpy = pytest.importorskip("bpy")
    import sssekai_blender_io.blender.operators.importer as importer_operator

    del importer_operator
    wm = bpy.context.window_manager
    wm.sssekai_import_matching_face_track = True
    wm.sssekai_selected_face_track = ""
    assert bpy.ops.sssekai.import_sekai_timeline_op() == {"CANCELLED"}
    wm.sssekai_import_matching_face_track = False


def test_guarded_bpy_operator_uses_active_controller_targets():
    bpy = pytest.importorskip("bpy")
    import sssekai_blender_io.blender.operators.importer as importer_operator

    del importer_operator
    source = OPERATOR_SOURCE.read_text(encoding="utf-8")
    assert 'controller.get(KEY_SEKAI_CHARACTER_BODY_OBJ)' in source
    assert 'controller.get(KEY_SEKAI_CHARACTER_FACE_OBJ)' in source
    assert "source character" not in source.lower()
    del bpy


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
