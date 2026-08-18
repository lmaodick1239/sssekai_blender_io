# Timeline First-Clip Label Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the first successfully resolved clip name in every Motion and Face Timeline dropdown label while preserving existing track selection behavior.

**Architecture:** Keep the change at the UI enum-label formatting boundary in [`timeline_track_enum()`](../../../blender/panels/importer.py:68). Read the first resolved [`TimelineClipSpec.display_name`](../../../blender/core/timeline.py:43) from each track’s existing [`clips`](../../../blender/core/timeline.py:77) tuple, use `<no clips>` when the tuple is empty, and leave source IDs, icons, catalog discovery, and import behavior unchanged.

**Tech Stack:** Python, Blender searchable enum tuples, pytest, AST-isolated catalog tests.

## Global Constraints

- Do not modify Timeline resolver or catalog semantics.
- Preserve enum identifiers derived from [`TimelineTrackRef.source_id`](../../../blender/core/timeline.py:73).
- Preserve Motion and Face icons derived from [`TimelineTrackRef.kind`](../../../blender/core/timeline.py:76).
- Use the exact label order `{parent_name} / {track_name} / {first_clip_name} / {clip_count} clips`.
- Use `<no clips>` when a track has no successfully resolved clips.
- Do not read or depend on external metadata such as [`mvdata.json`](../../../xtract/mvdata.json).
- Keep the change limited to the enum formatter and focused catalog tests.

---

### Task 1: Add failing catalog-label tests

**Files:**
- Modify: [`tests/test_timeline_catalog.py`](../../../tests/test_timeline_catalog.py:105)

**Interfaces:**
- Consumes: [`timeline_track_enum()`](../../../blender/panels/importer.py:68) loaded through the test module’s existing AST harness.
- Produces: Regression coverage requiring first clip names in Motion and Face labels, plus safe empty-track formatting.

- [ ] **Step 1: Update the existing searchable-label expectation**

In [`test_catalog_discovers_recognized_tracks_and_formats_searchable_labels()`](../../../tests/test_timeline_catalog.py:105), change the expected labels from:

```python
[
    "Motion Group / Character0 / 2 clips",
    "Face  Group / Character0_insert / 7 clips",
]
```

to:

```python
[
    "Motion Group / Character0 / raw clip 0 / 2 clips",
    "Face  Group / Character0_insert / raw clip 0 / 7 clips",
]
```

The fixture already creates those display names in [`make_track()`](../../../tests/test_timeline_catalog.py:67), so no production-like data fixture changes are required.

- [ ] **Step 2: Add an empty-track fallback test**

Add a test after the existing label test that constructs a zero-clip recognized track and verifies the formatter does not raise:

```python
def test_timeline_track_enum_uses_placeholder_for_tracks_without_resolved_clips():
    catalog = _load_catalog_functions()
    empty_track = catalog["catalog_timeline_tracks"]([
        make_track("Character_empty", "Motion Group", 50, object(), 0),
    ])[0]

    assert catalog["timeline_track_enum"]([empty_track])[0][1] == (
        "Motion Group / Character_empty / <no clips> / 0 clips"
    )
```

- [ ] **Step 3: Run the focused tests and verify failure**

Run:

```bash
pytest tests/test_timeline_catalog.py -q
```

Expected result: the existing label assertion fails because production currently omits the first clip name. The new fallback test may pass before implementation if the formatter does not index the clip tuple, but the full label test must fail before the production change.

- [ ] **Step 4: Commit the failing-test changes**

```bash
git add tests/test_timeline_catalog.py
git commit -m "test: require first clip names in timeline labels"
```

---

### Task 2: Format Timeline labels with the first clip name

**Files:**
- Modify: [`blender/panels/importer.py`](../../../blender/panels/importer.py:68)
- Test: [`tests/test_timeline_catalog.py`](../../../tests/test_timeline_catalog.py:105)

**Interfaces:**
- Consumes: [`TimelineTrackRef.clips`](../../../blender/core/timeline.py:77) and each clip’s [`display_name`](../../../blender/core/timeline.py:43).
- Produces: Searchable enum entries with labels formatted as `parent / track / first clip / count clips`, retaining the existing source ID and icon.

- [ ] **Step 1: Implement the minimal formatter change**

Update [`timeline_track_enum()`](../../../blender/panels/importer.py:68) so each entry computes the first clip name safely:

```python
def timeline_track_enum(tracks):
    icons = {"MOTION": "ARMATURE_DATA", "FACE": "SHAPEKEY_DATA"}
    return [
        (
            str(track.source_id),
            f"{track.parent_name} / {track.name} / "
            f"{track.clips[0].display_name if track.clips else '<no clips>'} / "
            f"{len(track.clips)} clips",
            "",
            icons[track.kind],
            index,
        )
        for index, track in enumerate(tracks)
    ]
```

Keep the existing identifier conversion, description, icon lookup, and enumeration index unchanged. Do not change [`catalog_timeline_tracks()`](../../../blender/panels/importer.py:102) or [`TimelineTrackRef`](../../../blender/core/timeline.py:70).

- [ ] **Step 2: Run catalog tests and verify pass**

Run:

```bash
pytest tests/test_timeline_catalog.py -q
```

Expected result: all catalog tests pass, including Motion and Face first-clip labels, stable IDs, environment refresh behavior, arbitrary-group filtering, and the empty-track fallback.

- [ ] **Step 3: Run the broader relevant test set**

Run:

```bash
pytest tests/test_timeline_resolver.py tests/test_timeline_catalog.py tests/test_timeline_import_operator.py -q
```

Expected result: all relevant Timeline resolver, catalog, and import-operator tests pass. The formatter-only change must not alter resolver or operator behavior.

- [ ] **Step 4: Review the diff for scope and label consistency**

Verify that the diff changes only the intended formatter and test expectations/coverage. Confirm both labels use the first resolved clip’s `display_name`, not the underlying AnimationClip reader name, and that empty tracks use `<no clips>`.

- [ ] **Step 5: Commit the implementation**

```bash
git add blender/panels/importer.py tests/test_timeline_catalog.py
git commit -m "feat: show first clip in timeline labels"
```

---

## Self-review

- **Spec coverage:** The label format, Motion/Face behavior, empty-track fallback, stable IDs/icons, unchanged resolver/catalog semantics, and focused tests are covered by Tasks 1 and 2.
- **Placeholder scan:** No TODO, TBD, or unspecified implementation steps remain.
- **Type consistency:** The plan uses the existing `TimelineTrackRef.clips` tuple and `TimelineClipSpec.display_name` field; no new interfaces are introduced.
- **Scope:** Only [`blender/panels/importer.py`](../../../blender/panels/importer.py:68) and [`tests/test_timeline_catalog.py`](../../../tests/test_timeline_catalog.py:105) are changed.
