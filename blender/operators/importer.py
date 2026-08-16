from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews, bpy_extras
import math, json, traceback

from typing import List, Tuple
from UnityPy.classes import PPtr

from UnityPy.classes import (
    Mesh,
    Material,
    SkinnedMeshRenderer,
    MeshFilter,
    MeshRenderer,
)
from sssekai.unity.AnimationClip import read_animation

from ..core.consts import *
from ..core.helpers import create_empty
from ..core.helpers import (
    ensure_sssekai_shader_blend,
    create_action,
    apply_action,
    action_curve_count,
    editbone_children_recursive,
    armature_editbone_children_recursive,
    set_obj_bone_parent,
    place_action_strip,
    append_start_frame,
)

from ..core.asset import (
    import_all_material_inputs,
    make_material_value_node,
    import_sekai_eye_material,
    import_sekai_eyelight_material,
    import_sekai_character_material,
    import_sekai_character_face_sdf_material,
    import_sekai_stage_lightmap_material,
    import_sekai_stage_color_add_material,
    import_scene_hierarchy,
    import_mesh_data,
)
from ..core.animation import (
    load_armature_animation,
    load_sekai_camera_animation,
    load_sekai_keyshape_animation,
    load_sekai_ambient_light_animation,
    load_sekai_directional_light_animation,
    load_sekai_character_ambient_light_animation,
    load_sekai_character_rim_light_animation,
)
from ..core.types import Hierarchy
from ..core.math import blVector, blEuler, blMatrix, xform_to_matrix
from ..core.helpers import apply_pose_matrix
from ..core.timeline import timeline_clip_frames, validate_timeline_clip
from .. import register_class, register_wm_props, logger
from .. import sssekai_global
from ..operators.material import (
    SSSekaiGenericMaterialSetModeOperator,
    set_generic_material_nodegroup,
)
from .utils import crc32
from tqdm import tqdm


@register_class
class SSSekaiBlenderUpdateCharacterControllerBodyPositionDriverOperator(
    bpy.types.Operator
):
    bl_idname = "sssekai.update_character_controller_body_position_driver_op"
    bl_label = T("Update Character Controller Driver")
    bl_description = T(
        "Update the driver for the Body object of the Character Controller"
    )

    def execute(self, context):
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert active_obj and KEY_SEKAI_CHARACTER_ROOT in active_obj
        body = active_obj[KEY_SEKAI_CHARACTER_BODY_OBJ]
        assert body, "Body not found"
        body: bpy.types.Object
        bpy.context.view_layer.objects.active = body
        bpy.ops.object.mode_set(mode="POSE")
        bone = body.pose.bones.get("Position", None)
        if bone:
            bone.driver_remove("scale")
            for ch in bone.driver_add("scale"):
                ch.driver.type = "SCRIPTED"
                var = ch.driver.variables.new()
                var.name = "height"
                var.type = "SINGLE_PROP"
                var.targets[0].id = active_obj
                var.targets[0].data_path = f'["{KEY_SEKAI_CHARACTER_HEIGHT}"]'
                ch.driver.expression = "height"
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderCreateCharacterControllerOperator(bpy.types.Operator):
    bl_idname = "sssekai.create_character_controller_op"
    bl_label = T("Create Character Controller")
    bl_description = T(
        "Create an Empty object with a Rim Light Controller that one can import Sekai Character armatures to"
    )

    def execute(self, context):
        wm = context.window_manager
        ensure_sssekai_shader_blend()

        root = create_empty("SekaiCharacterRoot")
        root[KEY_SEKAI_CHARACTER_ROOT] = True
        root[KEY_SEKAI_CHARACTER_HEIGHT] = wm.sssekai_character_height
        root[KEY_SEKAI_CHARACTER_BODY_OBJ] = None
        root[KEY_SEKAI_CHARACTER_FACE_OBJ] = None
        rim_controller = bpy.data.objects["SekaiCharaRimLight"].copy()
        rim_controller.parent = root
        root[KEY_SEKAI_CHARACTER_LIGHT_OBJ] = rim_controller
        bpy.context.collection.objects.link(rim_controller)

        bpy.context.view_layer.objects.active = root
        return {"FINISHED"}


@register_class
class SSSekaiBlenderCreateCameraRigControllerOperator(bpy.types.Operator):
    bl_idname = "sssekai.create_camera_rig_controller_op"
    bl_label = T("Create Camera Rig Controller")
    bl_description = T(
        "Create an Empty object with a Camera Rig Controller that one can import Sekai Camera animations to"
    )

    def execute(self, context):
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        camera = context.active_object
        assert camera.type == "CAMERA", "Active object must be a Camera"

        rig = create_empty("SekaiCameraRig")
        rig[KEY_SEKAI_CAMERA_RIG] = "<marker>"
        rig.rotation_mode = "XZY"
        # NOTE: Not YXZ since there's a 90 degree Y offset at the root of the in game camera
        # Can be done in anim import stage but that messes up the slopes. Eulers are weird...
        rig.scale.y = 60  # Arbitrary default - FOV
        rig[KEY_SEKAI_CAMERA_RIG_SENSOR_HEIGHT] = (
            24  # Arbitrary default - Sensor Height (mm)
        )
        camera.parent = rig
        camera.data.lens_unit = "MILLIMETERS"
        camera.location = blVector((0, 0, 0))
        camera.rotation_euler = blEuler((math.radians(90), 0, math.radians(180)))
        camera.rotation_mode = "YXZ"
        camera.scale = blVector((1, 1, 1))
        camera.data.sensor_fit = "VERTICAL"
        camera.data.dof.aperture_fstop = 6.5

        height = camera.data.driver_add("sensor_height")
        height.driver.type = "SCRIPTED"
        var = height.driver.variables.new()
        var.name = "height"
        var.type = "SINGLE_PROP"
        var.targets[0].id = rig
        var.targets[0].data_path = f'["{KEY_SEKAI_CAMERA_RIG_SENSOR_HEIGHT}"]'
        height.driver.expression = "height"

        # Driver for FOV
        driver = camera.data.driver_add("lens")
        driver.driver.type = "SCRIPTED"

        var_sensor = driver.driver.variables.new()
        var_sensor.name = "sensor_height"
        var_sensor.type = "SINGLE_PROP"
        var_sensor.targets[0].id = rig
        var_sensor.targets[0].data_path = f'["{KEY_SEKAI_CAMERA_RIG_SENSOR_HEIGHT}"]'

        var_scale = driver.driver.variables.new()
        var_scale.name = "fov"
        var_scale.type = "TRANSFORMS"
        var_scale.targets[0].id = rig
        var_scale.targets[0].transform_space = "WORLD_SPACE"
        var_scale.targets[0].transform_type = "SCALE_Z"

        driver.driver.expression = "sensor_height / (2 * tan(radians(fov * 100) / 2))"

        # Driver for Focal Distance
        camera.data.dof.use_dof = True
        driver = camera.data.driver_add("dof.focus_distance")
        driver.driver.type = "SCRIPTED"

        var_distance = driver.driver.variables.new()
        var_distance.name = "distance"
        var_distance.type = "SINGLE_PROP"
        var_distance.targets[0].id = rig
        var_distance.targets[0].data_path = "delta_scale.x"

        driver.driver.expression = "distance"

        bpy.context.view_layer.objects.active = rig
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportHierarchyOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_op"
    bl_label = T("Import Hierarchy")
    bl_description = T("Import the selected Hierarchy from the selected asset bundle")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object

        container = wm.sssekai_selected_hierarchy_container
        selected = wm.sssekai_selected_hierarchy
        selected: bpy.types.EnumProperty
        hierarchy = sssekai_global.containers[container].hierarchies[int(selected)]
        logger.debug("Loading selected hierarchy: %s" % hierarchy.name)
        # Import the scene as an Armature
        scene = import_scene_hierarchy(
            hierarchy,
            wm.sssekai_hierarchy_import_bindpose,
            wm.sssekai_hierarchy_import_seperate_armatures,
        )
        if wm.sssekai_hierarchy_import_mode == "SEKAI_CHARACTER":
            assert (
                KEY_SEKAI_CHARACTER_ROOT in active_obj
            ), "Active object is not a Character Controller"
            match wm.sssekai_character_type:
                case "HEAD":
                    assert not active_obj[
                        KEY_SEKAI_CHARACTER_FACE_OBJ
                    ], "Face already imported"
                    active_obj[KEY_SEKAI_CHARACTER_FACE_OBJ] = scene[0][0]
                case "BODY":
                    assert not active_obj[
                        KEY_SEKAI_CHARACTER_BODY_OBJ
                    ], "Body already imported"
                    active_obj[KEY_SEKAI_CHARACTER_BODY_OBJ] = scene[0][0]
                    bpy.context.view_layer.objects.active = active_obj
                    bpy.ops.sssekai.update_character_controller_body_position_driver_op()
        # Import Skinned Meshes and Static Meshes
        # - Just like with Unity scene graph, everything is going to have a parent
        # - Once expressed as a Blender Armature, the direct translation of that is a Bone Parent
        #   Hence we'd always need an Armature to parent the meshes to
        # - Skinning works in Blender by matching bone names with vertex groups
        #   In that sense we only need to import the mesh and assign the modifier since parenting is already done
        imported_objects: List[Tuple[bpy.types.Object, List[PPtr[Material]], Mesh]] = []
        # Skinned Meshes
        sm_mapping = {
            sm_pathid: (armature_obj, bone_names)
            for armature_obj, bone_names, sm_pathid in scene
        }
        for node in tqdm(hierarchy.nodes.values(), desc="Importing Skinned Meshes"):
            game_object = node.game_object
            if game_object.m_SkinnedMeshRenderer:
                # bool ModelImporter::ImportSkinnedMesh
                try:
                    sm = game_object.m_SkinnedMeshRenderer.read()
                    sm: SkinnedMeshRenderer
                    if not sm.m_Mesh:
                        continue
                    mesh = sm.m_Mesh.read()
                    bone_names = [
                        hierarchy.nodes[pptr.m_PathID].name
                        if pptr.m_PathID in hierarchy.nodes
                        else f"__MISSING_BONE_{pptr.m_PathID}"
                        for pptr in sm.m_Bones
                    ]
                    mesh_data, mesh_obj = import_mesh_data(
                        game_object.m_Name, mesh, bone_names
                    )
                    armature_obj, _mapping = sm_mapping.get(
                        sm.object_reader.path_id, (None, None)
                    )
                    if not armature_obj:
                        armature_obj, _mapping = sm_mapping.get(0, (None, None))
                        assert armature_obj, "no armature found"
                    # Already in parent space
                    mesh_obj.parent = armature_obj
                    # Add an armature modifier
                    mesh_obj.modifiers.new("Armature", "ARMATURE").object = armature_obj
                    imported_objects.append((mesh_obj, sm.m_Materials, mesh))
                except Exception as e:
                    traceback.print_exc()
                    logger.error(
                        "Failed to import Skinned Mesh at %s: %s. Skipping."
                        % (game_object.m_Name, str(e))
                    )
        # Static Meshes
        if wm.sssekai_hierarchy_import_seperate_armatures:
            # Only bones that can have effect on mesh skinning are kept in `scene` with this mode
            # Create a complete Armature for the static ones
            scene = import_scene_hierarchy(
                hierarchy, wm.sssekai_hierarchy_import_bindpose, False
            )
        for armature_obj, nodes, sm_id in scene:
            assert sm_id == 0, "bad importer state"
            if wm.sssekai_hierarchy_import_mode == "SEKAI_CHARACTER":
                armature_obj.parent = active_obj
            for path_id, bone_name in tqdm(
                nodes.items(), desc="Importing Static Meshes"
            ):
                node = hierarchy.nodes[path_id]
                game_object = node.game_object
                if game_object.m_MeshFilter:
                    try:
                        m = game_object.m_MeshRenderer.read()
                        m: MeshRenderer
                        mf = game_object.m_MeshFilter.read()
                        mf: MeshFilter
                        if not mf.m_Mesh:
                            continue
                        mesh = mf.m_Mesh.read()
                        mesh_data, mesh_obj = import_mesh_data(game_object.m_Name, mesh)
                        set_obj_bone_parent(mesh_obj, bone_name, armature_obj)
                        imported_objects.append((mesh_obj, m.m_Materials, mesh))
                    except Exception as e:
                        traceback.print_exc()
                        logger.error(
                            "Failed to import Static Mesh at %s: %s. Skipping."
                            % (bone_name, str(e))
                        )
        # Import Materials
        # - This is done in a seperate procedure since there'd be some permuations depending on
        #   the user's preference (i.e. sssekai_hierarchy_import_mode)
        # - Caching persists across imports, and is only reset when the source folder is reloaded
        texture_cache = sssekai_global.texture_cache
        material_cache = sssekai_global.material_cache

        # By principle this should be matched by their respective Shaders
        # But since there's no guarantee that the PathID would always match across versions therefore we'd pattern-match
        # the name and the properties to determine the correct importer
        def import_material_sekai_character(material: Material):
            rim_light_controller = next(
                filter(
                    lambda o: o.name.startswith("SekaiCharaRimLight"),
                    active_obj.children_recursive,
                ),
                None,
            )
            envs = dict(material.m_SavedProperties.m_TexEnvs)
            floats = dict(material.m_SavedProperties.m_Floats)
            name = material.m_Name
            if "_eye" in name:  # CharacterEyeBase
                return import_sekai_eye_material(name, material, texture_cache)
            if "_ehl_" in name:  # CharacterEyeLight
                return import_sekai_eyelight_material(name, material, texture_cache)
            if "_FaceShadowTex" in envs and floats.get(
                "_UseFaceSDF", 0
            ):  # CharacterToonV3
                return import_sekai_character_face_sdf_material(
                    name,
                    material,
                    texture_cache,
                    armature_obj=armature_obj,
                    rim_light_controller=rim_light_controller,
                    head_bone_target="Head",
                )
            return import_sekai_character_material(
                name, material, texture_cache, rim_light_controller=rim_light_controller
            )

        def import_material_fallback(material: Material, mode_override: str = ""):
            name = material.m_Name
            mat = import_all_material_inputs(name, material, texture_cache)
            set_generic_material_nodegroup(
                mat, mode_override or wm.sssekai_generic_material_import_mode
            )
            return mat

        def import_material_sekai_stage(material: Material):
            envs = dict(material.m_SavedProperties.m_TexEnvs)
            floats = dict(material.m_SavedProperties.m_Floats)
            name = material.m_Name
            # TODO: Better way to detect these
            # Naming schemes are not consistent in some of the newer assets
            if "_LightMapTex" in envs:
                if "Reflection_" in name:
                    return import_sekai_stage_lightmap_material(
                        name, material, texture_cache, has_reflection=True
                    )
                else:
                    return import_sekai_stage_lightmap_material(
                        name, material, texture_cache, has_reflection=False
                    )
            elif "_Color_Add" in name:
                return import_sekai_stage_color_add_material(
                    name, material, texture_cache
                )
            else:
                # XXX: Some other permutations still exist
                return import_material_fallback(material)

        def import_material(material: Material):
            imported = None
            name = material.m_Name
            envs = dict(material.m_SavedProperties.m_TexEnvs)
            floats = dict(material.m_SavedProperties.m_Floats)
            match wm.sssekai_hierarchy_import_mode:
                case "SEKAI_CHARACTER":
                    if wm.sssekai_sekai_material_mode == "GENERIC":
                        # Some hardcoded modes for this kind of blending
                        if "_ehl_" in name:
                            imported = import_material_fallback(
                                material, mode_override="COLORADD"
                            )
                        elif "_FaceShadowTex" in envs and floats.get("_UseFaceSDF", 0):
                            imported = import_material_fallback(
                                material, mode_override="EMISSIVE"
                            )
                        else:
                            imported = import_material_fallback(material)
                    else:
                        imported = import_material_sekai_character(material)
                case "SEKAI_STAGE":
                    if wm.sssekai_sekai_material_mode == "GENERIC":
                        if "_Color_Add" in name:
                            imported = import_material_fallback(
                                material, mode_override="COLORADD"
                            )
                        else:
                            imported = import_material_fallback(material)
                    else:
                        imported = import_material_sekai_stage(material)
                case "GENERIC":
                    if wm.sssekai_generic_material_import_mode == "SKIP":
                        return None
                    imported = import_material_fallback(material)
            return imported

        for obj, materials, mesh in tqdm(imported_objects, desc="Importing Materials"):
            if wm.sssekai_generic_material_import_mode == "SKIP":
                break
            for ppmat in materials:
                if ppmat.path_id:
                    try:
                        material: Material = ppmat.read()
                        imported = None
                        if material.object_reader.path_id in material_cache:
                            imported = material_cache[material.object_reader.path_id]
                            obj.data.materials.append(imported)
                            continue
                        imported = import_material(material)
                        if imported:
                            obj.data.materials.append(imported)
                            material_cache[material.object_reader.path_id] = imported
                    except Exception as e:
                        traceback.print_exc()
                        logger.error(
                            "Failed to import Material %s: %s. Skipping."
                            % (ppmat.path_id, str(e))
                        )
            # Set material indices afterwards
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode="OBJECT")
            for index, sub in enumerate(mesh.m_SubMeshes):
                start, count = sub.firstVertex, sub.vertexCount
                for i in range(start, start + count):
                    obj.data.vertices[i].select = True
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.context.object.active_material_index = index
                bpy.ops.object.material_slot_assign()
                bpy.ops.mesh.select_all(action="DESELECT")
                bpy.ops.object.mode_set(mode="OBJECT")  # Deselects all vertices

        # Restore
        if active_obj:
            bpy.context.view_layer.objects.active = active_obj
            bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportHierarchyAnimationOperaotr(bpy.types.Operator):
    bl_idname = "sssekai.import_hierarchy_animation_op"
    bl_label = T("Import Hierarchy Animation")
    bl_description = T(
        "Import the selected Animation into the selected Armature (Hierarchy). ATTENTION: Split armatures won't work yet!"
    )

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert active_obj.type == "ARMATURE", "Active object must be an Armature"
        assert (
            KEY_HIERARCHY_BONE_PATHID in active_obj
        ), "Active object must be a Hierarchy imported by the addon itself"
        # Build TOS
        # XXX: Does TOS mean To String? Unity uses this nomenclature internally
        tos_leaf = dict()
        bind_xform = dict()
        bpy.ops.object.mode_set(mode="EDIT")
        if wm.sssekai_animation_use_animator:
            animator = sssekai_global.containers[
                wm.sssekai_selected_animator_container
            ].animators[int(wm.sssekai_selected_animator)]
            animator = animator.read()
            avatar = animator.m_Avatar
            if not avatar.path_id:
                self.report(
                    {"ERROR"},
                    T("Animator Avatar not found, cannot recover hierarchy"),
                )
                return {"CANCELLED"}
            avatar.read()
            # Only take the leaf bone names
            tos_leaf = {k: v.split("/")[-1] for k, v in avatar.m_TOS}
            if len(set(tos_leaf.values())) != len(tos_leaf):
                logger.warning(
                    "Animator has multiple bones with the same name. Expect issues"
                )
            # Mecanim stores the bindpose when importing the model here
            bind = avatar.m_Avatar.m_DefaultPose.data.m_X  # local space
            bind_xform = {
                tos_leaf[k]: xform_to_matrix(v.t, v.q, v.s)
                for k, v in zip(avatar.m_Avatar.m_AvatarSkeleton.data.m_ID, bind)
            }
            dfngen = armature_editbone_children_recursive(active_obj.data)
            global_xform = dict()
            for parent, child, depth in dfngen:  # to world space
                u = parent.name if parent else ""
                v = child.name
                if v not in bind_xform:
                    continue
                mat = bind_xform[v]
                if u in global_xform:
                    mat = global_xform[u] @ mat
                global_xform[v] = mat
            # Update our bind transform with it
            # XXX: Mesh MUST match the skeleton before this op (i.e. w/ Bake Identity Pose)
            if global_xform:
                apply_pose_matrix(active_obj, global_xform, True, True)
        else:
            dfngen = None
            if wm.sssekai_animation_root_bone:
                ebone = active_obj.data.edit_bones.get(
                    wm.sssekai_animation_root_bone, None
                )
                assert ebone, "Selected root bone not found in the Armature"
                dfngen = editbone_children_recursive(ebone)
            else:
                dfngen = armature_editbone_children_recursive(active_obj.data)
            for parent, child, depth in dfngen:
                if (
                    not wm.sssekai_animation_root_bone
                    and KEY_HIERARCHY_BONE_ROOT in child
                ):
                    # Stub. Ignore this when a root bone is selected
                    continue
                pa_path = (
                    tos_leaf.get(parent[KEY_HIERARCHY_BONE_NAME], "") if parent else ""
                )
                if pa_path:
                    pa_path += "/"
                # Blender bone names are guaranteed to be unique within their hierarchy
                tos_leaf[child.name] = pa_path + child[KEY_HIERARCHY_BONE_NAME]
            tos_leaf = {crc32(v): k for k, v in tos_leaf.items()}
        tos_leaf[0] = active_obj.data.edit_bones[0].name  # Root bone is always 0
        bpy.ops.object.mode_set(mode="OBJECT")
        # Load Animation
        anim = sssekai_global.containers[
            wm.sssekai_selected_animation_container
        ].animations[int(wm.sssekai_selected_animation)]
        logger.info("Loading Animation %s" % anim.m_Name)
        anim = anim.read()
        anim = read_animation(anim)
        # Check for Mecanim IK hashes
        mecanim_ik = set(UNITY_MECANIM_RESERVED_TOS.keys()) & set(tos_leaf.keys())
        if len(mecanim_ik) > 0:
            self.report(
                {"WARNING"},
                "Mecanim IK bones found in the animation: %s. "
                "This is not supported yet. Expect issues."
                % ", ".join([UNITY_MECANIM_RESERVED_TOS[k] for k in mecanim_ik]),
            )
        logger.info("Loading Animation %s" % anim.Name)
        if not wm.sssekai_animation_import_use_scene_fps:
            bpy.context.scene.render.fps = int(anim.SampleRate)
            logger.info("Using animation Sample Rate: %d FPS" % anim.SampleRate)
        action = load_armature_animation(
            anim.Name,
            anim,
            active_obj,
            tos_leaf,
        )
        append_body = (
            getattr(wm, "sssekai_animation_append_exisiting", False)
            and active_obj.parent
            and active_obj.parent.get(KEY_SEKAI_CHARACTER_BODY_OBJ) is active_obj
        )
        if append_body:
            append_start = append_start_frame(active_obj)
            action_start, action_end = action.frame_range
            strip = place_action_strip(
                active_obj,
                action,
                append_start,
                action_end - action_start,
                action_start,
                action_end,
                "Motion Group",
                name=action.name,
            )
            imported_end = strip.frame_end
        else:
            imported_end = action.curve_frame_range[1]
            apply_action(
                active_obj,
                action,
                wm.sssekai_animation_import_use_nla,
                wm.sssekai_animation_import_nla_always_new_track,
            )
        # Set frame range, including the actual endpoint of an appended strip.
        bpy.context.scene.frame_end = max(
            bpy.context.scene.frame_end, int(imported_end)
        )
        if bpy.context.scene.rigidbody_world:
            bpy.context.scene.rigidbody_world.point_cache.frame_end = max(
                bpy.context.scene.rigidbody_world.point_cache.frame_end,
                bpy.context.scene.frame_end,
            )
        self.report({"INFO"}, T("Hierarchy Animation %s Imported") % anim.Name)
        # Restore
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportSekaiCharacterMotionOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_sekai_character_motion_op"
    bl_label = T("Import Sekai Character Motion")
    bl_description = T("Import the selected Sekai Character Motion")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert (
            active_obj and KEY_SEKAI_CHARACTER_ROOT in active_obj
        ), "Active object must be a Character Controller"
        body = active_obj[KEY_SEKAI_CHARACTER_BODY_OBJ]
        assert body, "Body not found"
        # Set active object to the body
        bpy.context.view_layer.objects.active = body
        bpy.ops.sssekai.import_hierarchy_animation_op()
        # Restore
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="OBJECT")
        # Drivers get removed post animation import so fix it here too
        bpy.ops.sssekai.update_character_controller_body_position_driver_op()
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportSekaiCharacterFaceMotionOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_sekai_character_face_motion_op"
    bl_label = T("Import Sekai Character Face Motion")
    bl_description = T("Import the selected Sekai Character Face Motion")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert (
            active_obj and KEY_SEKAI_CHARACTER_ROOT in active_obj
        ), "Active object must be a Character Controller"
        face = active_obj[KEY_SEKAI_CHARACTER_FACE_OBJ]
        face: bpy.types.Object
        assert face, "Face not found"
        # Find the shapekey name hashtable
        # hash is simply crc32("blendShape." + Shape key name). This is baked in.
        morphs = list(
            filter(
                lambda obj: obj.type == "MESH" and KEY_SHAPEKEY_HASH_TABEL in obj.data,
                face.children_recursive,
            )
        )
        assert morphs, "No meshes with shapekey found"
        assert (
            len(morphs) == 1
        ), "Multiple meshes with shapekeys found. Please keep only one"
        # XXX: Generalize this for generic Unity stuff
        morph = morphs[0]
        crc_table = json.loads(morph.data[KEY_SHAPEKEY_HASH_TABEL])
        # Set active object to the face
        bpy.context.view_layer.objects.active = face
        # Load Animation
        anim = sssekai_global.containers[
            wm.sssekai_selected_animation_container
        ].animations[int(wm.sssekai_selected_animation)]
        logger.info("Loading Animation %s" % anim.m_Name)
        anim = anim.read()
        anim = read_animation(anim)
        action = load_sekai_keyshape_animation(anim.Name, anim, crc_table)
        if action_curve_count(action) == 0:
            self.report(
                {"ERROR"},
                T("Face Shapekey Animation %s generated no curves") % anim.Name,
            )
            bpy.context.view_layer.objects.active = active_obj
            bpy.ops.object.mode_set(mode="OBJECT")
            return {"CANCELLED"}
        apply_action(
            morph.data.shape_keys,
            action,
            wm.sssekai_animation_import_use_nla,
            wm.sssekai_animation_import_nla_always_new_track,
        )
        self.report({"INFO"}, T("Sekai Shapekey Animation %s Imported") % anim.Name)
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportSekaiTimelineOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_sekai_timeline_op"
    bl_label = T("Import Sekai Timeline")
    bl_description = T("Import selected Timeline motion or explicitly selected face tracks")

    @staticmethod
    def _body_tos_leaf(body):
        def visit(bone, parent_path=""):
            unity_name = bone.get(KEY_HIERARCHY_BONE_NAME, bone.name)
            path = f"{parent_path}/{unity_name}" if parent_path else unity_name
            yield crc32(path), bone.name
            for child in bone.children:
                yield from visit(child, path)

        result = dict(
            item
            for root in body.data.bones
            if root.parent is None
            for item in visit(root)
        )
        result[0] = next(
            (bone.name for bone in body.data.bones if bone.parent is None),
            "",
        )
        return result

    @staticmethod
    def _face_target(face):
        morphs = [
            obj
            for obj in face.children_recursive
            if obj.type == "MESH" and KEY_SHAPEKEY_HASH_TABEL in obj.data
        ]
        if len(morphs) != 1:
            raise ValueError("expected exactly one face mesh with a shapekey hash table")
        morph = morphs[0]
        return morph.data.shape_keys, json.loads(morph.data[KEY_SHAPEKEY_HASH_TABEL])

    @staticmethod
    def _track(track_id, expected_kind):
        from ..panels.importer import timeline_track_by_id

        if not track_id or track_id == "<no assest selected!>":
            return None
        track = timeline_track_by_id(track_id)
        if track is None or track.kind != expected_kind:
            raise ValueError(f"selected {expected_kind.lower()} Timeline track is unavailable")
        return track

    def _report_track(self, track, imported, skipped, warnings):
        detail = f"{track.name}: imported={imported}, skipped={skipped}"
        if warnings:
            detail += "; warnings=" + " | ".join(warnings)
        self.report({"WARNING" if skipped or warnings else "INFO"}, detail)

    @staticmethod
    def _discard_generated_action(action):
        """Remove an unreferenced Action created for an invalid Timeline clip."""

        if action is not None and getattr(action, "users", 0) == 0:
            bpy.data.actions.remove(action)

    def execute(self, context):
        wm = context.window_manager
        controller = context.active_object
        if not controller or KEY_SEKAI_CHARACTER_ROOT not in controller:
            self.report({"ERROR"}, T("Active object must be a Sekai character controller"))
            return {"CANCELLED"}

        motion_id = wm.sssekai_selected_motion_track
        face_id = wm.sssekai_selected_face_track
        if motion_id == "<no assest selected!>":
            motion_id = ""
        if face_id == "<no assest selected!>":
            face_id = ""
        paired = wm.sssekai_import_matching_face_track
        if not motion_id and not face_id:
            self.report({"ERROR"}, T("Select a Timeline motion or face track"))
            return {"CANCELLED"}
        if paired and not face_id:
            self.report({"ERROR"}, T("Select an explicit face track for pairing"))
            return {"CANCELLED"}
        if paired and not motion_id:
            self.report({"ERROR"}, T("Select a motion track for paired Timeline import"))
            return {"CANCELLED"}

        # A face selection is meaningful without motion only as an explicit face-only import.
        # With motion selected, face data is opt-in through the pairing flag.
        face_requested = bool(face_id) and (paired or not motion_id)
        try:
            motion = self._track(motion_id, "MOTION")
            face_track = self._track(face_id if face_requested else "", "FACE")
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        body = controller.get(KEY_SEKAI_CHARACTER_BODY_OBJ)
        face = controller.get(KEY_SEKAI_CHARACTER_FACE_OBJ)
        if motion and not body:
            self.report({"ERROR"}, T("The active controller has no body target"))
            return {"CANCELLED"}
        if face_track and not face:
            self.report({"ERROR"}, T("The active controller has no face target"))
            return {"CANCELLED"}

        fps = context.scene.render.fps
        try:
            face_target, face_crc_table = self._face_target(face) if face_track else (None, None)
            body_tos_leaf = self._body_tos_leaf(body) if motion else None
        except Exception as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        prepared = []
        motion_imported = motion_skipped = 0
        track_reports = []

        for track, kind in ((motion, "MOTION"), (face_track, "FACE")):
            if not track:
                continue
            imported = skipped = 0
            warnings = []
            target = body if kind == "MOTION" else face_target
            for spec in sorted(track.clips, key=lambda item: item.source_order):
                clip_label = f"{track.name} / {spec.display_name}"
                action = None
                try:
                    frames = timeline_clip_frames(spec, fps)
                    animation = read_animation(spec.animation_reader.read())
                    if kind == "MOTION":
                        action = load_armature_animation(
                            spec.display_name, animation, target, body_tos_leaf
                        )
                        if action_curve_count(action) == 0:
                            raise ValueError("generated body Action has no curves")
                    else:
                        action = load_sekai_keyshape_animation(
                            spec.display_name, animation, face_crc_table
                        )
                        if action_curve_count(action) == 0:
                            raise ValueError("generated face Action has no curves")
                    warnings.extend(
                        f"{clip_label}: {warning}"
                        for warning in validate_timeline_clip(spec, action.frame_range, fps)
                    )
                    prepared.append((track, spec, frames, action, target))
                    imported += 1
                except Exception as error:
                    self._discard_generated_action(action)
                    skipped += 1
                    warnings.append(f"{clip_label}: {error}")
            track_reports.append((track, imported, skipped, warnings))
            if kind == "MOTION":
                motion_imported, motion_skipped = imported, skipped

        for track, imported, skipped, warnings in track_reports:
            self._report_track(track, imported, skipped, warnings)
        if motion and motion_imported == 0:
            logger.error(
                "No valid motion clips remain: selected_id=%r track=%r clips=%d "
                "catalog_motion_tracks=%s source=%r aux=%r failures=%s",
                motion_id,
                motion.name,
                len(motion.clips),
                [
                    (track.source_id, track.name, len(track.clips), len(track.diagnostics))
                    for track in sssekai_global.timeline_tracks
                    if track.kind == "MOTION"
                ],
                sssekai_global.env_path,
                sssekai_global.env_aux_path,
                warnings,
            )
            for _, _, _, action, _ in prepared:
                self._discard_generated_action(action)
            self.report({"ERROR"}, T("No valid motion clips remain"))
            return {"CANCELLED"}
        if not prepared:
            self.report({"ERROR"}, T("No valid Timeline clips remain"))
            return {"CANCELLED"}

        largest_end = context.scene.frame_end
        for track, spec, frames, action, target in sorted(
            prepared, key=lambda item: (item[2].timeline_start, item[1].source_order)
        ):
            strip = place_action_strip(
                target,
                action,
                frames.timeline_start,
                frames.timeline_end - frames.timeline_start,
                frames.action_start,
                frames.action_end,
                track.name,
                name=spec.display_name,
            )
            largest_end = max(largest_end, strip.frame_end)
        context.scene.frame_end = int(math.ceil(largest_end))
        if context.scene.rigidbody_world:
            context.scene.rigidbody_world.point_cache.frame_end = max(
                context.scene.rigidbody_world.point_cache.frame_end,
                context.scene.frame_end,
            )
        self.report({"INFO"}, T("Sekai Timeline imported"))
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportSekaiCameraAnimationOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_sekai_camera_animation_op"
    bl_label = T("Import Sekai Camera Animation")
    bl_description = T("Import the selected Sekai Camera Animation")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert KEY_SEKAI_CAMERA_RIG in active_obj, "Active object must be a Camera Rig"
        # Load Animation
        anim = sssekai_global.containers[
            wm.sssekai_selected_animation_container
        ].animations[int(wm.sssekai_selected_animation)]
        logger.info("Loading Animation %s" % anim.m_Name)
        anim = anim.read()
        anim = read_animation(anim)
        if not wm.sssekai_animation_import_use_scene_fps:
            bpy.context.scene.render.fps = int(anim.SampleRate)
            logger.info("Using animation Sample Rate: %d FPS" % anim.SampleRate)
        action = load_sekai_camera_animation(
            anim.Name,
            anim,
            wm.sssekai_camera_import_is_sub_camera,
        )
        # Set frame range
        bpy.context.scene.frame_end = max(
            bpy.context.scene.frame_end, int(action.curve_frame_range[1])
        )
        apply_action(
            active_obj,
            action,
            wm.sssekai_animation_import_use_nla,
            wm.sssekai_animation_import_nla_always_new_track,
        )
        self.report({"INFO"}, T("Sekai Camera Animation %s Imported") % anim.Name)
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportGlobalLightAnimationOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_global_light_animation_op"
    bl_label = T("Import Global Light Animation")
    bl_description = T("Import the selected Light Animation to the Global Light")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        # Load Animation
        anim = sssekai_global.containers[
            wm.sssekai_selected_animation_container
        ].animations[int(wm.sssekai_selected_animation)]
        logger.info("Loading Animation %s" % anim.m_Name)
        anim = anim.read()
        anim = read_animation(anim)
        if not wm.sssekai_animation_import_use_scene_fps:
            bpy.context.scene.render.fps = int(anim.SampleRate)
            logger.info("Using animation Sample Rate: %d FPS" % anim.SampleRate)
        global_obj = bpy.data.objects["SekaiShaderGlobals"]
        dir_light_obj = bpy.data.objects["SekaiDirectionalLight"]
        match wm.sssekai_animation_light_type:
            case "AMBIENT":
                action = load_sekai_ambient_light_animation(anim.Name, anim)
                apply_action(
                    global_obj,
                    action,
                    wm.sssekai_animation_import_use_nla,
                    wm.sssekai_animation_import_nla_always_new_track,
                )
            case "DIRECTIONAL":
                global_action, directional_light_action = (
                    load_sekai_directional_light_animation(anim.Name, anim)
                )
                apply_action(
                    global_obj,
                    global_action,
                    wm.sssekai_animation_import_use_nla,
                    wm.sssekai_animation_import_nla_always_new_track,
                )
                apply_action(
                    dir_light_obj,
                    directional_light_action,
                    wm.sssekai_animation_import_use_nla,
                    wm.sssekai_animation_import_nla_always_new_track,
                )

        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportCharacterLightAnimationOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_character_light_animation_op"
    bl_label = T("Import Character Light Animation")
    bl_description = T("Import the selected Light Animation to the Character Light")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert (
            active_obj and KEY_SEKAI_CHARACTER_ROOT in active_obj
        ), "Active object must be a Character Controller"
        controler = active_obj[KEY_SEKAI_CHARACTER_LIGHT_OBJ]
        # Load Animation
        anim = sssekai_global.containers[
            wm.sssekai_selected_animation_container
        ].animations[int(wm.sssekai_selected_animation)]
        logger.info("Loading Animation %s" % anim.m_Name)
        anim = anim.read()
        anim = read_animation(anim)
        if not wm.sssekai_animation_import_use_scene_fps:
            bpy.context.scene.render.fps = int(anim.SampleRate)
            logger.info("Using animation Sample Rate: %d FPS" % anim.SampleRate)
        match wm.sssekai_animation_light_type:
            case "CHARACTER_RIM":
                action = load_sekai_character_rim_light_animation(anim.Name, anim)
                apply_action(
                    controler,
                    action,
                    wm.sssekai_animation_import_use_nla,
                    wm.sssekai_animation_import_nla_always_new_track,
                )
            case "CHARACTER_AMBIENT":
                action = load_sekai_character_ambient_light_animation(anim.Name, anim)
                apply_action(
                    controler,
                    action,
                    wm.sssekai_animation_import_use_nla,
                    wm.sssekai_animation_import_nla_always_new_track,
                )
        return {"FINISHED"}
