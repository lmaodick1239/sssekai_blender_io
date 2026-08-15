# Task 6 Verification

## Scope

Task 6 adds a dependency-free end-to-end synthetic Timeline regression, extends the Blender 5 Action-slot test with body/face strip range checks, and records the user workflow and unsupported Timeline semantics.

The synthetic graph contains two `Motion Group` body clips and two `Face  Group` face clips. Both tracks use authored starts of 0 and 5 seconds, with 2-second durations, preserving a 3-second gap. A second body placement begins inside the first clip to verify separate NLA-track allocation. A standalone body append is placed after the body endpoint while the face target's strips are snapshotted and verified unchanged.

## Commands and Results

- `python3 tests/test_timeline_end_to_end.py`
  - PASS: `task 6 end-to-end tests passed`.
- `pytest tests/test_timeline_end_to_end.py -q`
  - BLOCKED during collection by the system Python environment: `ModuleNotFoundError: No module named 'UnityPy'`, followed by the package dependency guard. This is an environment limitation, not a regression assertion failure.
- `python3 -m py_compile blender/core/timeline.py blender/core/helpers.py blender/core/animation.py blender/operators/importer.py blender/panels/importer.py`
  - PASS.
- `pytest tests/test_timeline_resolver.py tests/test_timeline_placement.py tests/test_timeline_catalog.py tests/test_timeline_import_operator.py tests/test_motion_append.py tests/test_timeline_end_to_end.py -v`
  - BLOCKED during collection: all six modules hit the package dependency guard because system Python has no `UnityPy`.
- `git diff --check`
  - PASS.

## Blender 5 Coverage

`tests/test_blender5_face_action.py` remains guarded by `pytest.importorskip("bpy")` and a Blender version check requiring Blender 5 Action slots. The added assertions verify:

- body Actions and strips use an `OBJECT` slot;
- face Actions and strips use a `KEY` slot;
- inner Action ranges are distinct from and explicitly assigned to authored strip ranges;
- outer strip start and duration follow explicit Timeline placement values.

No compatible Blender 5 executable or bundled Python runtime is available locally, so these integration tests were not executed here. The guarded module is skipped outside Blender 5 as intended.

## User Workflow and Limitations

The importer workflow is documented in `README.md`: select the active Blender character controller, choose a raw `Motion Group` track, optionally enable and choose a raw `Face  Group` track for explicit pairing, and use standalone append for body-only clips. Timeline import does not require `xtract/mvdata.json`; source track names do not automatically map to Blender characters. Blend/ease, loop, extrapolation, root matching, and foot-IK settings remain finite clips with warnings rather than silently emulating unsupported runtime semantics.

## Remaining Runtime Verification

Run the guarded Blender 5 suite with Blender's bundled Python against a real character controller and shape-key target. Verify registration, generated body/face Action slot IDs, explicit inner and outer strip ranges, authored gap/overlap behavior in the NLA editor, and standalone body append without face-target mutation. No `xtract/mvdata.json` access is part of Task 6.
