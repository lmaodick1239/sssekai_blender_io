# Blender 5 Face Motion Action Binding Design

## Problem

The Project SEKAI face-motion import operator completes on Blender 5.0.0 but produces no visible face movement during playback.

The inspected character controller is valid:

- `SekaiCharacterRoot` references the `face` armature.
- The armature contains 54 bones.
- The visible `Face` mesh is a descendant of that armature and has an Armature modifier targeting it.
- The mesh has 60 shape keys, including the expected `BS_` keys.

The imported action contains 26 valid `key_blocks[...].value` F-curves. Its Blender 5 Action slot is incompatible: it has target ID type `OBJECT`, even though its target is the mesh shape-key `Key` datablock. The NLA strip has no selected action slot. Additionally, the strip has an action-frame range of `0..1`, while the action curve range is `0..29992`; playback therefore never evaluates the animation frames.

## API Findings

Blender shape-key animation belongs to `bpy.types.Key`, which owns `animation_data`. In Blender 5, actions use slots; a slot identifies the action subset evaluated for an animated ID. The slot selected for `Key.animation_data` or an NLA strip must be compatible with ID type `KEY`.

The existing importer creates an action without declaring its target ID type. The first F-curve creation establishes the sole Blender 5 slot as `OBJECT`. The existing NLA code constructs a strip but only sets `action_frame_start`, leaving the default end of `1.0`, and does not select an action slot.

## Design

### Action Construction

Extend the shared action factory in `blender/core/helpers.py` to accept an optional Blender ID type.

- Retain legacy Action behavior for Blender 3.6 and 4.x.
- On Blender 5, create or retrieve the slot for the supplied ID type before any F-curves are created.
- Preserve `OBJECT` as the default for existing action callers.
- Make the keyshape loader request ID type `KEY` when creating an action.

The action factory owns this version-specific setup, so F-curve creation receives a correctly typed slot and does not infer an incompatible one.

### Action Application

Extend the shared action-application helper to select a slot compatible with the actual target datablock.

- For direct actions, assign the action to the target animation data, then assign the compatible slot when Blender 5 slots are available.
- For NLA actions, create the strip at the action start frame, set `action_frame_start` and `action_frame_end` from the complete action frame range, and assign the compatible slot when the NLA API exposes it.
- Use the target datablock ID type rather than the action's first slot as the compatibility criterion.
- Preserve existing caller-selected NLA behavior and track creation behavior.
- Raise or report a clear error when no compatible slot exists, rather than creating a silent non-playing action.

### Face Motion Import

Keep `SSSekaiBlenderImportSekaiCharacterFaceMotionOperator` responsible only for locating the face mesh, decoding its shape-key CRC table, loading the face action, and applying it to `mesh.data.shape_keys`.

Add post-load validation before applying the action:

- Count input blendshape curves.
- Count curves successfully bound to shape keys.
- Report missing CRC entries with their hash values and continue importing valid curves.
- Fail if no keyshape F-curves were created.

The importer will continue using the configured NLA option. It will not special-case Blender 5 or force direct action assignment.

### Diagnostic Procedure

Maintain a read-only Blender console diagnostic for a selected `SekaiCharacterRoot`. It reports:

- Blender version, controller, face armature, bone count, and world transform.
- Descendant mesh names, armature modifiers, shape-key counts, and shape-key names.
- `Key.animation_data`, active action, NLA tracks, strip ranges, action ranges, Action slot identifiers, target ID types, assigned strip slot identifiers, and F-curve data paths.
- Shape-key values sampled at each strip boundary.

The diagnostic must use Blender 5 `ActionSlot.identifier` and `ActionSlot.target_id_type`; it must not access a nonexistent `ActionSlot.name` property.

## Error Handling

- Face mesh discovery remains strict when multiple hash-table meshes are found, because selecting a mesh arbitrarily can animate invisible geometry.
- Missing shape-key CRC mappings are logged with enough context to identify the animation curve but do not block valid curves.
- Zero generated shape-key F-curves cause the operator to cancel with a user-visible error.
- No compatible Blender 5 Action slot causes application to fail visibly, avoiding a completed import with no playback effect.

## Test Coverage

Add focused tests for the shared helpers and face keyshape loader using Blender-compatible test infrastructure.

- Blender 5 `KEY` action construction creates a `KEY` slot and stores F-curves in that slot's channelbag.
- `OBJECT` action construction remains compatible with armature, camera, and light import callers.
- Direct action application assigns the target-compatible slot.
- NLA application assigns the target-compatible slot and copies the complete action frame range to the strip.
- A representative face action drives a non-Basis shape-key value at a sampled animation frame.
- A missing CRC mapping is reported and does not create an invalid data path.

## Verification

On Blender 5.x, import a face motion with NLA enabled and verify all of the following:

1. The target is the visible `Face` mesh's `shape_keys` datablock.
2. The action slot target ID type is `KEY`.
3. The NLA strip selects that `KEY` slot.
4. The strip action-frame start and end match the action curve range.
5. Sampling a frame containing a nonzero curve changes at least one non-Basis shape-key value.
6. The face visibly animates during timeline playback.

## Scope

This work changes only shared Action construction/application compatibility and face-motion binding validation. It does not modify face rig transforms, mesh import, shape-key geometry, animator retargeting, or non-face animation semantics beyond correctly selecting each target's existing compatible Blender 5 Action slot.
