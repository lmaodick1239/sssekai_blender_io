# Task 2 Report: Explicit Timeline Frame Conversion and NLA Placement

## Status

Implemented Task 2 only. Tasks 3-6 were not implemented. The pre-existing `.gitignore`, Task 1 report, and untracked approved specification/plan files were preserved.

## Commit

Commit hash: `69fd1e8` (`feat: place animation clips on explicit timeline frames`).

Planned commit scope:

- [`blender/core/timeline.py`](../../../blender/core/timeline.py:1)
- [`blender/core/helpers.py`](../../../blender/core/helpers.py:313)
- [`tests/test_timeline_placement.py`](../../../tests/test_timeline_placement.py:1)
- This report

## Implementation

- Added immutable [`TimelineFrameRange`](../../../blender/core/timeline.py:55).
- Added [`timeline_clip_frames()`](../../../blender/core/timeline.py:239) using the required single scene-FPS formulas for Timeline start/end and action clip-in/source-duration bounds.
- Added finite timing validation for FPS, start, duration, clip-in, and time scale. Duration and time scale must be positive; clip-in must be nonnegative; generated action bounds must increase.
- Added [`validate_timeline_clip()`](../../../blender/core/timeline.py:280), including action-range comparison with `1e-3` tolerance and finite warnings for ease/blend/mix, looping, non-default extrapolation, root matching, and foot IK semantics.
- Added [`place_action_strip()`](../../../blender/core/helpers.py:326) with explicit fractional frame placement, complete inner Action range, explicit outer Timeline duration, positive influence, deterministic first reusable NLA track allocation, and new-track creation for overlaps.
- Added [`append_start_frame()`](../../../blender/core/helpers.py:377), which inspects only the requested target's NLA tracks and returns `0.0` for an empty target.
- Preserved existing [`apply_action()`](../../../blender/core/helpers.py:265) behavior and its Blender 5 slot binding through [`action_slot_for_target()`](../../../blender/core/helpers.py:218).
- Did not access or parse `xtract/mvdata.json`.

## Tests and Verification

### RED check

The first direct placement harness run failed at the expected missing production interface:

```text
AttributeError: module 'task2_helpers_package.core.helpers' has no attribute 'place_action_strip'
```

### Passing commands

```text
.venv/bin/python tests/test_timeline_placement.py
=> task-2 placement harness: PASS

.venv/bin/python -m py_compile blender/core/timeline.py blender/core/helpers.py tests/test_timeline_placement.py
=> exit code 0

git diff --check
=> exit code 0
```

The test module covers conversion, invalid duration/scale/clip-in, action-range validation tolerance and mismatch, semantic warnings, fractional strip placement, gaps, overlap track allocation, compatible slot binding through a fake Blender-shaped API, and target-isolated append endpoints.

### Environment limitations

- No local `blender` executable was found.
- The installed `bpy` package is only a namespace package and is not a runnable Blender runtime.
- Neither the system Python nor the repository virtualenv provides `pytest`; the requested pytest command could not be executed.
- Existing resolver pytest collection under system Python is also blocked by missing `UnityPy`; the repository virtualenv has `UnityPy` but no pytest.
- Blender 5 integration coverage remains guarded in the existing face-action test and was not claimed as runtime-tested.

## Concerns

- Runtime behavior against actual Blender NLA collections and Blender 5 slot APIs still requires a Blender 5 executable or bundled test runner.
- The Task 2 placement API is intentionally standalone; importer/operator wiring belongs to Tasks 3-5 and was left untouched.

## Review Fix Report

### Fixes

- Changed extrapolation metadata handling so only the documented `None`/`NoneMode` sentinel values are silent; `Hold` now emits the required unsupported-extrapolation warning, with pure regression coverage.
- Added guarded Blender 5 coverage for explicit NLA placement on a real shape-key `KEY` target/action slot, including fractional outer range, complete inner action range, and positive influence. Existing fake `OBJECT`/`KEY` tests remain for pure placement math and slot-selection coverage because no Blender runtime is installed.
- Documented the placement caller contract: clips are submitted in nondecreasing timeline-start/source-order order, with existing NLA collection order as the deterministic allocation tie-breaker. The pure harness now exercises overlap allocation and gap reuse under that order.
- Removed the unused test import and added NaN, positive-infinity, and negative-infinity cases for every required finite timeline and placement input.
- Preserved legacy `apply_action()` semantics and did not access `xtract/mvdata.json`.

### Verification

```text
.venv/bin/python tests/test_timeline_placement.py
=> task-2 placement harness: PASS

.venv/bin/python -m py_compile blender/core/timeline.py blender/core/helpers.py tests/test_timeline_placement.py tests/test_blender5_face_action.py
=> exit code 0

git diff --check
=> exit code 0

.venv/bin/python -m pytest tests/test_timeline_placement.py -q
=> unavailable: No module named pytest

Blender 5 runtime
=> unavailable: no blender executable found
```

### Remaining Concerns

- Guarded Blender 5 tests were added but could not execute without a Blender 5 runtime.
- Pytest collection remains unavailable in the repository virtualenv; the direct harness is the executable pure-test substitute.
