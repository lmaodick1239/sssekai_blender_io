# Task 1 implementation report

## Status

Implemented Task 1: Timeline source models and pure Unity Timeline graph resolver.

The implementation is limited to [`blender/core/timeline.py`](../../../blender/core/timeline.py) and [`tests/test_timeline_resolver.py`](../../../tests/test_timeline_resolver.py). [`blender/core/__init__.py`](../../../blender/core/__init__.py) was not modified because package exports are not required by the approved interfaces.

Tasks 2–6 were not implemented.

## Implementation

- Added immutable [`TimelineTrackRef`](../../../blender/core/timeline.py:54) and [`TimelineClipSpec`](../../../blender/core/timeline.py:37) dataclasses.
- Added typed [`TimelineResolutionError`](../../../blender/core/timeline.py:65) diagnostics carrying track ID/name, playable-asset clip ID, animation-clip ID, clip/display context, and source order where available.
- Added [`discover_timeline_tracks()`](../../../blender/core/timeline.py:226), [`resolve_timeline_clip()`](../../../blender/core/timeline.py:181), and [`catalog_timeline_tracks()`](../../../blender/core/timeline.py:298).
- Discovery preserves source object order, raw parent/track/clip labels, empty recognized tracks, and clip source order.
- Classification recognizes only direct parent groups named `Motion Group` and `Face  Group`, producing `MOTION` and `FACE` kinds; other groups are ignored.
- Pointer traversal is exactly `m_Clips -> m_Asset.read() -> playable.m_Clip.read()` and retains the `m_Clip` reader as `animation_reader`.
- Raw transition, extrapolation, and playable metadata are captured without mutating Unity objects.
- The resolver contains no `mvdata`, `xtract`, or file-reading dependency.
- No timing validation or placement behavior was added; those belong to Task 2.

## TDD and verification

### Failing-test phase

Command:

```text
pytest tests/test_timeline_resolver.py -q
```

Result: collection was blocked before test execution because the system Python could not import the project dependency `UnityPy`.

Additional environment attempt:

```text
.venv/bin/python -m pytest tests/test_timeline_resolver.py -q
```

Result: the bundled Blender virtual environment has no `pytest` module.

The requested regression tests were added before the implementation fixes. They cover consistent playable-asset and animation-clip diagnostic IDs, typed unreadable track/parent diagnostics, preservation of ignored unrecognized groups, nested metadata detachment/deep immutability, and the repository-root test import path.

### Static verification

Commands:

```text
.venv/bin/python -m py_compile blender/core/timeline.py tests/test_timeline_resolver.py

git diff --check
```

Result: exit code 0, no output.

The focused pytest suite remains blocked in this environment because the bundled virtual environment does not include `pytest`, while the system interpreter cannot collect the package without `UnityPy`. No local Blender/pytest-compatible UnityPy environment is available.

## Fixes for review findings

- Animation-reference diagnostics now preserve the playable asset reference as `clip_source_id` and the animation reference as `animation_source_id`; track-level re-wrapping retains both IDs.
- Track reference read failures, null track values, and parent reference read failures/nulls/non-readable references now raise [`TimelineResolutionError`](../../../blender/core/timeline.py:65) with track context. Unrecognized parent groups continue to be ignored, including when their clips are broken.
- Metadata capture now recursively copies and freezes mappings, sequences, sets, and bytearrays through [`_deep_freeze()`](../../../blender/core/timeline.py:155), preventing nested source-owned containers from being mutated through the resolved model.
- Corrected the test root insertion to use the repository root (`parents[1]`).

## Commit

Created commit:

```text
PENDING
```

## Scope and preservation concerns

- The pre-existing modified [`/.gitignore`](../../../.gitignore) remains unstaged and uncommitted.
- The pre-existing untracked approved plan and design spec remain untracked and untouched:
  - [`docs/superpowers/plans/2026-08-14-unity-timeline-motion-face-sequencing.md`](../../../docs/superpowers/plans/2026-08-14-unity-timeline-motion-face-sequencing.md)
  - [`docs/superpowers/specs/2026-08-14-unity-timeline-motion-face-sequencing-design.md`](../../../docs/superpowers/specs/2026-08-14-unity-timeline-motion-face-sequencing-design.md)
- No code path reads or parses `xtract/mvdata.json`.
- No changes were made to existing importer, animation, helper, panel, or package initialization code.
- Runtime pytest success remains unconfirmed until executed in an environment with compatible project dependencies and pytest available.
