# Blender 5 Face Motion Action Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` recommended or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make Project SEKAI face-motion imports evaluate correctly on Blender 5 by authoring shape-key actions in `KEY` slots and assigning those slots with complete frame ranges to direct actions and NLA strips.

**Architecture:** Centralize Blender 5 Action-slot creation and target-compatible slot selection in the shared animation helpers. The face keyshape loader declares its target as `KEY`; the existing face-motion importer remains focused on mesh discovery, CRC-to-shape-key binding, and action application. The shared application helper sets Action/NLA binding state from the actual target datablock, preserving existing non-face import flows.

**Tech Stack:** Python 3.10+, Blender Python API 3.6/4.x/5.x, `bpy`, `sssekai`, UnityPy, pytest.

## Global Constraints

- Preserve support for Blender 3.6+, 4.x, and 5.x.
- Do not add runtime dependencies.
- Preserve the configured direct-action versus NLA import mode.
- In Blender 5, shape-key actions must use an Action slot with target ID type `KEY`.
- In Blender 5, direct and NLA assignment must select an Action slot compatible with the target datablock's ID type.
- NLA strips must use the complete action frame range, not Blender's default one-frame range.
- Do not alter face rig transforms, mesh geometry, or unrelated animation semantics.

---

## File Structure

- Modify [`blender/core/helpers.py`](blender/core/helpers.py): define Blender-version-compatible Action construction, compatible slot lookup, and direct/NLA application behavior.
- Modify [`blender/core/animation.py`](blender/core/animation.py): create face keyshape actions with the `KEY` target type and safely account for missing CRC mappings.
- Modify [`blender/operators/importer.py`](blender/operators/importer.py): make face-motion import reject zero generated curves and report skipped mappings.
- Create [`tests/test_blender5_face_action.py`](tests/test_blender5_face_action.py): Blender 5 integration regression test, skipped outside a real Blender 5 Python runtime.
- Modify [`README.md`](README.md): document the Blender 5 face-motion requirement and diagnostic/verification route only if project documentation conventions warrant user-facing release notes.

### Task 1: Define the Shared Blender 5 Action Contract

**Files:**
- Modify: [`blender/core/helpers.py`](blender/core/helpers.py)
- Test: [`tests/test_blender5_face_action.py`](tests/test_blender5_face_action.py)

**Interfaces:**
- Consumes: Action name string and Blender ID-type string such as `OBJECT` or `KEY`.
- Produces: `create_action(name: str, id_type: str = 'OBJECT') -> bpy.types.Action`, with a single compatible Blender 5 slot before F-curve creation.
- Produces: `action_slot_for_target(action: bpy.types.Action, target: bpy.types.ID) -> bpy.types.ActionSlot | None`, returning the unique compatible Action slot when Blender 5 exposes slots and otherwise `None`.

- [ ] **Step 1: Create the Blender 5 test module with a real-runtime guard**

Write [`tests/test_blender5_face_action.py`](tests/test_blender5_face_action.py) so pytest skips the module if importing `bpy` fails or its version is below 5.0. The guard must keep the existing fake-BPY unit test environment usable.

```python
import pytest

bpy = pytest.importorskip('bpy')
if bpy.app.version < (5, 0, 0):
    pytest.skip('requires Blender 5 Action slots', allow_module_level=True)
```

- [ ] **Step 2: Write the failing KEY-slot construction test**

Add a test that calls `create_action('face-slot-test', 'KEY')`, asserts exactly one Action slot, asserts its target ID type is `KEY`, and removes the generated action in a `finally` block.

```python
action = create_action('face-slot-test', 'KEY')
assert len(action.slots) == 1
assert action.slots[0].target_id_type == 'KEY'
```

- [ ] **Step 3: Run the test under Blender 5 and confirm the current behavior fails**

Run Blender's bundled Python against pytest from the repository root, using the local add-on source on `PYTHONPATH`.

```bash
/path/to/blender/5.x/python/bin/python3.11 -m pytest tests/test_blender5_face_action.py::test_create_key_action_uses_key_slot -v
```

Expected: failure because [`create_action()`](blender/core/helpers.py:209) accepts no ID-type argument and the initial slot is inferred as `OBJECT`.

- [ ] **Step 4: Implement explicit slot construction**

Update [`create_action()`](blender/core/helpers.py:209) to accept `id_type: str = 'OBJECT'`. On Blender 5, create the base layer and keyframe strip as needed, then create the requested slot before callers can create F-curves. On Blender 3.6 and 4.x, only create the legacy Action and ignore this argument.

```python
def create_action(name: str, id_type: str = 'OBJECT'):
    action = bpy.data.actions.new(name)
    if getattr(action, 'slots', None) is not None:
        action.slots.new(id_type=id_type, name='Base Slot')
    return action
```

Keep the existing layer/strip initialization in the F-curve helper, or move it into a small private helper shared by Action construction and F-curve creation. Do not create a second slot when the F-curve helper runs.

- [ ] **Step 5: Add compatible-slot lookup and its test**

Implement `action_slot_for_target()` beside [`create_action()`](blender/core/helpers.py:209). Derive the target ID type from `target.id_type`, filter Action slots by `target_id_type`, return the only compatible slot, and raise a `ValueError` containing the target name and available slot ID types if none exists or if multiple compatible slots would be ambiguous.

Add a test that creates a mesh with shape keys, then verifies a `KEY` action returns its unique `KEY` slot for `mesh.data.shape_keys`.

- [ ] **Step 6: Run the focused test module and commit**

Run:

```bash
/path/to/blender/5.x/python/bin/python3.11 -m pytest tests/test_blender5_face_action.py -v
```

Expected: all Task 1 tests pass on Blender 5; they skip cleanly in the standard non-Blender pytest environment.

Commit:

```bash
git add blender/core/helpers.py tests/test_blender5_face_action.py
git commit -m 'fix: create Blender 5 actions with typed slots'
```

### Task 2: Correct Direct and NLA Action Assignment

**Files:**
- Modify: [`blender/core/helpers.py`](blender/core/helpers.py)
- Test: [`tests/test_blender5_face_action.py`](tests/test_blender5_face_action.py)

**Interfaces:**
- Consumes: `apply_action(target: bpy.types.ID, action: bpy.types.Action, use_nla: bool = False, nla_always_new_track: bool = False)`.
- Consumes: `action_slot_for_target(action, target)` from Task 1.
- Produces: compatible `AnimData.action_slot` for direct assignment; compatible `NlaStrip.action_slot` plus a strip action range equal to `action.frame_range` for NLA assignment.

- [ ] **Step 1: Write failing direct-assignment coverage**

Build a mesh with Basis and `BS_test` shape keys. Create a `KEY` action with one F-curve on the `BS_test` value, call `apply_action(key, action)`, and assert the active action and active Action slot target ID type are `KEY`.

```python
apply_action(key, action, use_nla=False)
assert key.animation_data.action == action
assert key.animation_data.action_slot.target_id_type == 'KEY'
```

- [ ] **Step 2: Write failing NLA range and slot coverage**

Using an action with F-curves at frames `0.0` and `120.0`, call `apply_action(key, action, use_nla=True)`. Assert the created strip selects a `KEY` slot and has `action_frame_start == 0.0`, `action_frame_end == 120.0`, and an outer strip range spanning 120 frames.

```python
strip = key.animation_data.nla_tracks[-1].strips[-1]
assert strip.action_slot.target_id_type == 'KEY'
assert strip.action_frame_start == 0.0
assert strip.action_frame_end == 120.0
assert strip.frame_end - strip.frame_start == 120.0
```

- [ ] **Step 3: Run the new tests and confirm they fail on the baseline**

Run:

```bash
/path/to/blender/5.x/python/bin/python3.11 -m pytest tests/test_blender5_face_action.py -v
```

Expected: NLA coverage fails because [`apply_action()`](blender/core/helpers.py:251) leaves the action end at Blender's default `1.0` and does not set a strip slot.

- [ ] **Step 4: Implement target-compatible direct assignment**

In the direct-action branch of [`apply_action()`](blender/core/helpers.py:232), assign the action, then call `action_slot_for_target(action, object)` on Blender 5 and assign the returned slot to `object.animation_data.action_slot`. Do not use the first Action slot as a fallback.

- [ ] **Step 5: Implement target-compatible NLA creation and full frame bounds**

In the NLA branch of [`apply_action()`](blender/core/helpers.py:238), calculate the complete action bounds once from `action.frame_range`. Create the strip at the lower bound. Assign `strip.action_frame_start` and `strip.action_frame_end` to those bounds. For Blender 5, resolve the target-compatible slot and assign it to `strip.action_slot` after strip creation.

```python
frame_start, frame_end = action.frame_range
strip = nla_track.strips.new(action.name, int(frame_start), action)
strip.action_frame_start = frame_start
strip.action_frame_end = frame_end
if hasattr(strip, 'action_slot'):
    strip.action_slot = action_slot_for_target(action, object)
```

Use a small documented policy for negative action frames: retain the current importer convention of starting timeline strips at `max(0, frame_start)`, but do not truncate `action_frame_start` or `action_frame_end`; the inner action bounds must still cover all curve frames.

- [ ] **Step 6: Run direct/NLA tests and commit**

Run:

```bash
/path/to/blender/5.x/python/bin/python3.11 -m pytest tests/test_blender5_face_action.py -v
```

Expected: direct and NLA assertions pass, and no legacy behavior is exercised on Blender 3.6/4.x.

Commit:

```bash
git add blender/core/helpers.py tests/test_blender5_face_action.py
git commit -m 'fix: bind Blender 5 action slots to targets'
```

### Task 3: Author Face Actions as KEY Actions and Validate Curve Binding

**Files:**
- Modify: [`blender/core/animation.py`](blender/core/animation.py)
- Modify: [`blender/operators/importer.py`](blender/operators/importer.py)
- Test: [`tests/test_blender5_face_action.py`](tests/test_blender5_face_action.py)

**Interfaces:**
- Consumes: `load_sekai_keyshape_animation(name: str, data: Animation, crc_keyshape_table: dict, curve_key: int = SEKAI_BLENDSHAPE_CRC)`.
- Produces: a `KEY` Action and a structured import result that exposes generated-curve count and missing CRC hashes, or preserves the existing Action return type while emitting a deterministic warning list through the add-on logger.
- Consumes: `apply_action(mesh.data.shape_keys, action, ...)` from Task 2.

- [ ] **Step 1: Write failing unit coverage for a KEY action and a missing hash**

Construct a minimal animation fixture using the project Animation classes or a narrowly scoped fake with `CurvesT`, `Data`, and keyframe `value`, `time`, interpolation, and slopes. Include one mapped CRC and one unmapped CRC. Assert the loader returns a `KEY` action containing only the mapped curve path, and capture a warning containing the unmapped hash.

```python
action = load_sekai_keyshape_animation('face-test', animation, {'100': 'BS_test'})
assert action.slots[0].target_id_type == 'KEY'
assert curve_paths(action) == ['key_blocks["BS_test"].value']
assert '200' in caplog.text
```

Define `curve_paths()` in the test module to retrieve legacy `action.fcurves` when available and the `KEY` slot channelbag F-curves on Blender 5.

- [ ] **Step 2: Run the focused loader test and confirm it fails**

Run:

```bash
/path/to/blender/5.x/python/bin/python3.11 -m pytest tests/test_blender5_face_action.py::test_keyshape_loader_uses_key_slot_and_skips_unknown_crc -v
```

Expected: current loader creates an `OBJECT` action and raises `KeyError` on the unknown CRC.

- [ ] **Step 3: Create a typed face action and skip unknown mappings**

Update [`load_sekai_keyshape_animation()`](blender/core/animation.py:471) to call `create_action(name, id_type='KEY')`. Replace direct table indexing with a lookup. For every absent CRC, log a warning including action name and CRC hash, then continue. Retain `/100.0` value conversion and slope conversion for valid curves.

```python
action = create_action(name, id_type='KEY')
for attr, curve in data.CurvesT.get(curve_key, {}).items():
    bs_name = crc_keyshape_table.get(str(attr))
    if bs_name is None:
        logger.warning('Face action %s has no shape-key mapping for CRC32 %s', name, attr)
        continue
    load_fcurves(...)
```

- [ ] **Step 4: Reject a face import that generated no F-curves**

In [`SSSekaiBlenderImportSekaiCharacterFaceMotionOperator.execute()`](blender/operators/importer.py:643), inspect the generated action through a shared Action-curve count helper that understands Blender 5 channelbags. If the count is zero, report an error containing the animation name and cancel before calling `apply_action()`.

Add a focused test for the helper with a `KEY` action containing zero curves and one curve. Keep operator-level coverage manual unless the project already has a Blender UI test harness.

- [ ] **Step 5: Run loader and helper tests and commit**

Run:

```bash
/path/to/blender/5.x/python/bin/python3.11 -m pytest tests/test_blender5_face_action.py -v
```

Expected: mapped curves create a `KEY` slot, unknown mappings warn without aborting, and zero-curve actions are rejected before assignment.

Commit:

```bash
git add blender/core/animation.py blender/operators/importer.py tests/test_blender5_face_action.py
git commit -m 'fix: validate face shape-key action bindings'
```

### Task 4: Verify a Real Blender 5 Face-Motion Import

**Files:**
- Modify: [`README.md`](README.md) only if a short troubleshooting note is necessary after verification.
- Test: [`tests/test_blender5_face_action.py`](tests/test_blender5_face_action.py)

**Interfaces:**
- Consumes: a Blender 5 `.blend` file containing a selected `SekaiCharacterRoot`, an imported face armature, a visible face mesh with shape keys, and a Project SEKAI face-motion asset.
- Produces: observable nonzero shape-key values during imported NLA playback.

- [ ] **Step 1: Run the complete automated Blender 5 regression module**

Run:

```bash
/path/to/blender/5.x/python/bin/python3.11 -m pytest tests/test_blender5_face_action.py -v
```

Expected: all Blender 5 action-slot, direct binding, NLA binding, timing, and shape-key evaluation tests pass.

- [ ] **Step 2: Import one known face motion with NLA enabled in Blender 5**

Open the existing character scene, select `SekaiCharacterRoot`, select the same face-motion asset used for diagnosis, keep NLA enabled, and execute the face-motion import operator once. Do not retain previously generated test NLA tracks for this verification.

- [ ] **Step 3: Run the corrected read-only console audit**

Use the audit from the approved design, reading `ActionSlot.identifier` and `ActionSlot.target_id_type`. Confirm the visible `Face` mesh shape-key datablock has a strip with a `KEY` action slot; confirm its `action_frame_start` and `action_frame_end` match the action curve range; sample a frame inside the action where at least one non-Basis key value is nonzero.

- [ ] **Step 4: Verify viewport playback and record evidence**

Playback must visibly change the face expression. Record Blender version, imported action name, Action slot target ID type, NLA action range, and one sampled nonzero shape key in the commit or PR verification notes.

- [ ] **Step 5: Add documentation only if verification exposes a user prerequisite and commit**

If the import now succeeds without a user-side workaround, do not modify [`README.md`](README.md). If a durable prerequisite remains, add one concise Blender 5 troubleshooting note naming the expected `KEY` action slot and correct NLA range. Then commit all final documentation changes.

```bash
git add README.md
git commit -m 'docs: clarify Blender 5 face-motion playback'
```

If no documentation changed, do not create an empty documentation commit.

## Plan Self-Review

- Spec coverage: Task 1 implements typed Action creation and compatible-slot lookup. Task 2 implements direct and NLA slot binding plus complete inner action bounds. Task 3 applies the `KEY` contract to face actions, safely reports mapping gaps, and rejects empty actions. Task 4 covers automated and real-scene Blender 5 verification.
- Scope: no task changes rigs, mesh import, geometry, or user-selected NLA behavior.
- Compatibility: all Blender 5-only tests skip outside a real Blender 5 runtime; the runtime changes retain legacy Action behavior where slotted Actions are unavailable.
- Interfaces: all consumers use the shared `create_action()`, `action_slot_for_target()`, and `apply_action()` contract defined in Tasks 1 and 2.
