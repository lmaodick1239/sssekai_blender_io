# Blender 5 Face-Motion Fix Report

## Files

- [`blender/core/helpers.py`](../../../../blender/core/helpers.py): added slotted-action curve counting and target-compatible direct/NLA slot binding; NLA strips now use the complete action range and positive default influence.
- [`blender/core/animation.py`](../../../../blender/core/animation.py): face keyshape actions are created with a `KEY` slot; unmapped CRC32 entries are warned and skipped.
- [`blender/operators/importer.py`](../../../../blender/operators/importer.py): face imports with zero generated curves are reported as errors and cancelled before action assignment.
- [`tests/test_blender5_face_action.py`](../../../../tests/test_blender5_face_action.py): added Blender 5 regression coverage for typed slots, direct/NLA binding, full ranges, unknown CRCs, and empty actions.

## Tests

- `python3 -m py_compile blender/core/helpers.py blender/core/animation.py blender/operators/importer.py tests/test_blender5_face_action.py`
  - Passed.
- `git diff --check`
  - Passed.
- `./.venv/bin/python -m py_compile blender/core/helpers.py blender/core/animation.py blender/operators/importer.py tests/test_blender5_face_action.py`
  - Passed.
- `./.venv/bin/python -m pytest tests/test_blender5_face_action.py -v`
  - Not runnable: the project virtualenv does not contain `pytest`.
- `PYTHONPATH=".venv/lib/python3.10/site-packages:." /usr/bin/python3 -m pytest tests/test_blender5_face_action.py -v`
  - Collection blocked before the Blender guard: the system Python imports the virtualenv `UnityPy`, but its compiled `lz4` installation is incompatible and lacks `lz4._version`.
- Blender 5 regression execution
  - Not runnable locally: no Blender executable is installed or available on `PATH`.

## Commit

Commit [`bb5f523`](../../../../.git/COMMIT_EDITMSG:1) was created with message `fix: import face motion in Blender 5`.

## Remaining Remote Verification

1. Run `tests/test_blender5_face_action.py` with Blender 5's bundled Python and pytest.
2. Import one known face motion into a clean Blender 5 scene with NLA enabled.
3. Audit the face mesh shape-key datablock's NLA strip and confirm its action slot has target ID type `KEY`.
4. Confirm `action_frame_start` and `action_frame_end` equal the action's complete `frame_range`, and the outer strip range spans the same duration.
5. Sample a frame inside the action and record at least one non-Basis shape key with a nonzero value.
6. Confirm viewport playback visibly changes the face expression.

## Concerns

- Blender 5 Action-slot and shape-key evaluation behavior remains unverified on the unavailable remote runtime.
- The system pytest/project dependency mismatch prevents local collection; static compilation is the available local verification.
- No README change was made because the requested fix does not add a durable user-side prerequisite.
