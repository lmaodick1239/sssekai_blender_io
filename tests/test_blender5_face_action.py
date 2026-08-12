import logging

import pytest

bpy = pytest.importorskip("bpy")
bpy_version = getattr(getattr(bpy, "app", None), "version", None)
if bpy_version is None or bpy_version < (5, 0, 0):
    pytest.skip("requires Blender 5 Action slots", allow_module_level=True)

from sssekai.unity.AnimationClip import Animation, Curve, KeyFrame

from blender.core.animation import load_sekai_keyshape_animation
from blender.core.helpers import (
    action_curve_count,
    action_slot_for_target,
    apply_action,
    create_action,
    create_action_fcurve,
)


def _shape_key_target(name):
    mesh = bpy.data.meshes.new(f"{name}-mesh")
    obj = bpy.data.objects.new(f"{name}-object", mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.shape_key_add(name="Basis")
    key = mesh.shape_key_add(name="BS_test")
    return mesh, obj, key


def _key_action(name="face-key-action", end_frame=120.0):
    action = create_action(name, "KEY")
    fcurve = create_action_fcurve(action, "KEY", 'key_blocks["BS_test"].value')
    fcurve.keyframe_points.insert(0.0, 0.0)
    fcurve.keyframe_points.insert(end_frame, 1.0)
    return action


def _remove_shape_key_target(mesh, obj, key):
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)


def _cleanup_action(action):
    if action and action.name in bpy.data.actions:
        bpy.data.actions.remove(action)


def _curve_paths(action):
    if getattr(action, "fcurves", None) is not None:
        return [curve.data_path for curve in action.fcurves]
    channelbag = action.layers[0].strips[0].channelbag(action.slots[0])
    return [curve.data_path for curve in channelbag.fcurves]


def test_create_key_action_uses_key_slot():
    action = create_action("face-slot-test", "KEY")
    try:
        assert len(action.slots) == 1
        assert action.slots[0].target_id_type == "KEY"
    finally:
        _cleanup_action(action)


def test_action_slot_for_target_returns_shape_key_slot():
    mesh, obj, key = _shape_key_target("face-slot-lookup-test")
    action = create_action("face-slot-lookup-test", "KEY")
    try:
        assert action_slot_for_target(action, key.id_data) is action.slots[0]
    finally:
        _cleanup_action(action)
        _remove_shape_key_target(mesh, obj, key)


def test_action_slot_for_target_rejects_incompatible_slot():
    action = create_action("face-slot-mismatch-test", "OBJECT")
    mesh = bpy.data.meshes.new("face-slot-mismatch-mesh")
    try:
        with pytest.raises(ValueError, match="face-slot-mismatch-mesh"):
            action_slot_for_target(action, mesh)
    finally:
        _cleanup_action(action)
        bpy.data.meshes.remove(mesh)


def test_apply_key_action_directly_binds_compatible_slot():
    mesh, obj, key = _shape_key_target("face-direct-test")
    action = _key_action()
    try:
        apply_action(key.id_data, action)
        assert key.id_data.animation_data.action == action
        assert key.id_data.animation_data.action_slot.target_id_type == "KEY"
    finally:
        _cleanup_action(action)
        _remove_shape_key_target(mesh, obj, key)


def test_apply_key_action_nla_uses_full_range_and_compatible_slot():
    mesh, obj, key = _shape_key_target("face-nla-test")
    action = _key_action("face-nla-action", 120.0)
    try:
        apply_action(key.id_data, action, use_nla=True)
        strip = key.id_data.animation_data.nla_tracks[-1].strips[-1]
        assert strip.action_slot.target_id_type == "KEY"
        assert strip.action_frame_start == 0.0
        assert strip.action_frame_end == 120.0
        assert strip.frame_end - strip.frame_start == 120.0
        assert strip.influence > 0.0
    finally:
        _cleanup_action(action)
        _remove_shape_key_target(mesh, obj, key)


def test_keyshape_loader_uses_key_slot_and_skips_unknown_crc(caplog):
    mapped_key = KeyFrame(0.0, 0, 25.0)
    mapped_key.next = KeyFrame(1.0, 0, 50.0)
    unmapped_key = KeyFrame(0.0, 0, 75.0)
    unmapped_key.next = KeyFrame(1.0, 0, 100.0)
    animation = Animation(
        "face-loader-test",
        1.0,
        30.0,
        CurvesT={
            2770785369: {
                100: Curve(None, [mapped_key]),
                200: Curve(None, [unmapped_key]),
            }
        },
    )
    with caplog.at_level(logging.WARNING):
        action = load_sekai_keyshape_animation(
            "face-loader-test", animation, {"100": "BS_test"}
        )
    try:
        assert action.slots[0].target_id_type == "KEY"
        assert _curve_paths(action) == ['key_blocks["BS_test"].value']
        assert "200" in caplog.text
    finally:
        _cleanup_action(action)


def test_action_curve_count_handles_empty_key_action():
    action = create_action("face-empty-action", "KEY")
    try:
        assert action_curve_count(action) == 0
        fcurve = create_action_fcurve(action, "KEY", 'key_blocks["BS_test"].value')
        fcurve.keyframe_points.insert(0.0, 0.0)
        assert action_curve_count(action) == 1
    finally:
        _cleanup_action(action)
