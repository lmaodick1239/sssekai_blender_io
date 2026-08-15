# Task 4 Report: Unity Timeline Motion and Face Import

## Status

Implemented Task 4: Timeline body import with optional, explicit face-track pairing.

Task 5 and Task 6 were not implemented.

## Changed Files

- `blender/operators/importer.py`
- `blender/panels/importer.py`
- `tests/test_timeline_import_operator.py`

## Implementation

Added `SSSekaiBlenderImportSekaiTimelineOperator` with `bl_idname` `sssekai.import_sekai_timeline_op`.

The operator:

- Requires the active object to be a Sekai character controller.
- Reads the selected motion and face track IDs from the Window Manager.
- Treats pairing as explicit: face import occurs only for the selected face track when the pairing option is enabled or a face track is selected.
- Rejects paired mode when the motion track or explicit face track is missing.
- Supports body-only, face-only, and body-plus-face imports.
- Resolves tracks by catalog source ID and expected track kind; it does not infer pairing by name, index, source order, character ID, or source file metadata.
- Uses the active controller's stored body object and face object independently.
- Rebuilds the body animation CRC-to-bone map from imported armature hierarchy metadata.
- Uses `read_animation()` and `load_armature_animation()` for body clips.
- Uses `load_sekai_keyshape_animation()` and rejects generated face Actions with zero curves.
- Prevalidates and generates all selected clip Actions before creating NLA strips.
- Skips invalid clips and reports each track's imported count, skipped count, and warnings.
- Cancels before strip creation if no valid motion clips remain.
- Uses `timeline_clip_frames()` and `validate_timeline_clip()` for the shared scene-FPS frame conversion and semantic warnings.
- Uses `append_start_frame()` and `place_action_strip()` for explicit placement on independent body and face targets.
- Updates `Scene.frame_end` and the rigidbody point-cache end frame to the largest resulting strip end.

Added the `sssekai_import_matching_face_track` Window Manager Boolean property with a default of `False`. The motion and face track selectors were already registered as searchable enums by Task 3 and are used unchanged.

Added an `IMPORT_TIMELINE` mode to the existing import panel. The panel exposes motion selection, explicit face pairing, and face selection only in paired mode. Existing standalone `IMPORT_ANIMATION` and legacy body/face AnimationClip controls remain present.

## Tests

Added `tests/test_timeline_import_operator.py` with:

- Operator ID and explicit pairing contract checks.
- Loader, placement, validation, and independent target contract checks.
- Panel and legacy standalone-control checks.
- Guarded Blender property registration checks.
- Guarded Blender operator registration and missing-face-selection cancellation checks.
- Guarded active-controller target checks.

The test-first red run was attempted as required. The system Python could not collect the test because `UnityPy` is unavailable. The repository virtual environment contains no `pytest` module, so the focused test suite could not be executed there either.

Direct verification completed successfully:

- `python3 -m py_compile blender/operators/importer.py blender/panels/importer.py tests/test_timeline_import_operator.py`
- AST/source contract checks for the operator and panel
- `git diff --check`
- Static scan confirming no `mvdata` or `xtract` dependency in the new operator

No Blender executable or Blender Python runtime is available, so guarded `bpy` tests were not run.

## Concerns

- Runtime Blender integration remains unverified because no local Blender executable or `bpy` test runtime is installed.
- Runtime clip loader behavior depends on the existing body hierarchy metadata and face shapekey hash-table conventions.
- Face-only import is supported by the operator, while paired mode intentionally requires both an explicit motion and face selection.
- The working tree contains unrelated pre-existing changes. They were not modified or staged.

## Commit

The Task 4 commit contains only the requested production and test files.

## Review Fix Report

### Status

Implemented the requested Task 4 review fixes. Tasks 5 and 6 remain unimplemented.

### Fixes

- Made the shipped Timeline face selector usable when pairing is disabled, allowing face-only imports while retaining explicit paired body-plus-face semantics.
- Gated face-track resolution on explicit pairing when a motion track is selected, so stale face selections do not mutate the face target during body-only imports.
- Added zero-curve body Action prevalidation with a per-track/per-clip skipped warning, preventing empty body NLA strips.
- Structured validation and loader warnings as `track / clip: reason` entries in per-track summaries.
- Replaced source-only operator coverage with executable doubles that invoke the real operator `execute()` flow for body-only, face-only, paired, invalid clip, synchronized placement, independent targets, summaries, and empty-action behavior.
- Retained guarded Blender checks for registration and Blender-specific coverage where `bpy` is available.

### Verification

- Passed isolated executable-double checks for all non-Blender operator-flow tests (8 checks, including both pairing parameterizations).
- Passed `python3 -m py_compile blender/operators/importer.py blender/panels/importer.py tests/test_timeline_import_operator.py`.
- Passed `git diff --check`.
- Passed static scan confirming no `mvdata` or `xtract` dependency in the scoped implementation/tests.
- Focused `pytest` collection remains unavailable because the environment lacks `UnityPy`; no local Blender/compatible `bpy` runtime is available for guarded tests.

### Concerns

- Runtime Blender NLA placement, registration, and Blender 5 Action-slot behavior remain unverified in this environment.
- Existing unrelated working-tree changes were not modified or staged.
