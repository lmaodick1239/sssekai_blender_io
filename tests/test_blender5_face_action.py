import pytest

bpy = pytest.importorskip("bpy")
if bpy.app.version < (5, 0, 0):
    pytest.skip("requires Blender 5 Action slots", allow_module_level=True)

from blender.core.helpers import action_slot_for_target, create_action


def test_create_key_action_uses_key_slot():
    action = create_action("face-slot-test", "KEY")
    try:
        assert len(action.slots) == 1
        assert action.slots[0].target_id_type == "KEY"
    finally:
        bpy.data.actions.remove(action)


def test_action_slot_for_target_returns_shape_key_slot():
    mesh = bpy.data.meshes.new("face-slot-test-mesh")
    obj = bpy.data.objects.new("face-slot-test-object", mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.shape_key_add(name="Basis")
    key = mesh.shape_key_add(name="BS_test")
    action = create_action("face-slot-lookup-test", "KEY")
    try:
        assert action_slot_for_target(action, key.id_data) is action.slots[0]
    finally:
        bpy.data.actions.remove(action)
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def test_action_slot_for_target_rejects_incompatible_slot():
    action = create_action("face-slot-mismatch-test", "OBJECT")
    mesh = bpy.data.meshes.new("face-slot-mismatch-mesh")
    try:
        target = mesh
        with pytest.raises(ValueError, match="face-slot-mismatch-mesh"):
            action_slot_for_target(action, target)
    finally:
        bpy.data.actions.remove(action)
        bpy.data.meshes.remove(mesh)
