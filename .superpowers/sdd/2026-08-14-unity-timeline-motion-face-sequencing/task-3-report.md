# Task 3 Report: Timeline Track Catalog

## Status

Implemented Task 3 and committed it as `feat: expose Unity Timeline track selections`.

## Scope

Changed only:

- `blender/panels/importer.py`
- `blender/__init__.py`
- `tests/test_timeline_catalog.py`
- This report

Pre-existing changes to `.gitignore`, prior task reports, and the untracked approved specification/plan were preserved and excluded from the Task 3 commit.

## Implementation

- Added `sssekai_global.timeline_tracks` and `sssekai_global.timeline_track_enum` caches.
- Cleared both caches from `reset_env()` and when no asset-bundle path is selected.
- Refreshed the catalog after the primary and auxiliary environments are loaded, before the existing container enum update.
- Consumed `discover_timeline_tracks()` through the existing `catalog_timeline_tracks()` resolver API.
- Filtered behavior remains owned by the resolver: only exact `Motion Group` and `Face  Group` parents are cataloged; arbitrary groups are ignored.
- Built importer-level track IDs from `id(reader.assets_file)` and the Unity `path_id`, preserving raw source track names separately in `TimelineTrackRef.name`.
- Added `enumerate_timeline_tracks(context)` and `timeline_track_by_id(track_id)`.
- Added searchable motion and face enum properties using the existing `register_serachable_enum()` pattern.
- Enum labels use the required format: `Group / raw track name / N clips`.
- Did not open, locate, parse, or otherwise depend on `xtract/mvdata.json`.
- Existing AnimationClip, Animator, hierarchy, container construction, and container enum indexing were left unchanged.

## Tests and Verification

Passing direct harness:

```text
.venv/bin/python tests/test_timeline_catalog.py
 task3 catalog tests passed
```

Passing static compilation:

```text
.venv/bin/python -m py_compile blender/panels/importer.py blender/__init__.py tests/test_timeline_catalog.py
```

Passing whitespace check:

```text
git diff --check
```

The requested `pytest tests/test_timeline_catalog.py -q` command could not be used: the system has no `python` command, pytest is unavailable/incompatible per the task constraints, and no local Blender executable is installed. The direct harness was used instead and exercises the production catalog function definitions, resolver behavior, labels, stable IDs, cache lookup/enumeration, arbitrary-group filtering, and absence of `mvdata.json` references.

The first test-first run failed before implementation because the catalog API did not exist and the Blender runtime stub could not provide `bpy.props`; this was the expected red state under the repository's no-Blender constraints. After implementation and harness isolation, the direct catalog tests passed.

## Commit

Commit: `feat: expose Unity Timeline track selections`

Commit hash: `1331f874195af3734bfd27b25009c504b5c25631`.

## Concerns

- IDs use Python object identity for the loaded `assets_file`, as requested. They are stable for the lifetime of the loaded environment, but are not intended to persist across a later reload of the same asset bundle.
- Full Blender UI registration and live UnityPy bundle loading were not executable in this environment. They were covered by static compilation and the direct resolver/catalog harness.
- Tasks 4-6 were not implemented.
