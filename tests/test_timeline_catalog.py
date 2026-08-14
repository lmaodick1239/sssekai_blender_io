"""Task 3 catalog tests; executable with a small direct harness."""

import importlib.util
from dataclasses import replace
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _load_timeline():
    name = "task3_timeline_under_test"
    spec = importlib.util.spec_from_file_location(name, ROOT / "blender/core/timeline.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TIMELINE = _load_timeline()


class Reader:
    def __init__(self, value, path_id, assets_file):
        self.value = value
        self.path_id = path_id
        self.assets_file = assets_file

    def read(self):
        return self.value


class Group:
    def __init__(self, name):
        self.m_Name = name


class Animation:
    def __init__(self, name):
        self.m_Name = name


class Playable:
    def __init__(self, animation_reader):
        self.m_Clip = animation_reader


class Clip:
    def __init__(self, name, asset_reader):
        self.m_DisplayName = name
        self.m_Asset = asset_reader
        self.m_Start = 0.0
        self.m_Duration = 1.0
        self.m_ClipIn = 0.0
        self.m_TimeScale = 1.0


class Track:
    def __init__(self, name, parent_reader, clips):
        self.m_Name = name
        self.m_Parent = parent_reader
        self.m_Clips = clips


def make_track(name, group_name, path_id, assets_file, clip_count=1):
    clips = []
    for index in range(clip_count):
        animation_reader = Reader(Animation(f"clip-{index}"), 1000 + index, assets_file)
        playable_reader = Reader(Playable(animation_reader), 2000 + index, assets_file)
        clips.append(Clip(f"raw clip {index}", playable_reader))
    parent_reader = Reader(Group(group_name), path_id + 1, assets_file)
    return Reader(Track(name, parent_reader, clips), path_id, assets_file)


def _load_catalog_functions():
    """Execute production catalog definitions without importing Blender UI code."""
    import ast

    source = (ROOT / "blender/panels/importer.py").read_text()
    tree = ast.parse(source)
    names = {
        "_timeline_source_key",
        "timeline_track_enum",
        "catalog_timeline_tracks",
        "enumerate_timeline_tracks",
        "timeline_track_by_id",
    }
    namespace = {
        "ObjectReader": object,
        "TimelineTrackRef": TIMELINE.TimelineTrackRef,
        "resolve_timeline_tracks": TIMELINE.catalog_timeline_tracks,
        "EMPTY_OPT": ("<empty>", "Not Available", "", "ERROR", 0),
        "sssekai_global": SimpleNamespace(timeline_tracks=[], timeline_track_enum=[]),
    }
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            module = ast.Module(body=[node], type_ignores=[])
            exec(compile(module, "importer.py", "exec"), namespace)
    return namespace


def test_catalog_discovers_recognized_tracks_and_formats_searchable_labels():
    catalog = _load_catalog_functions()
    catalog_timeline_tracks = catalog["catalog_timeline_tracks"]
    timeline_track_enum = catalog["timeline_track_enum"]
    assets_file = object()
    tracks = catalog_timeline_tracks(
        [
            make_track("Character0", "Motion Group", 10, assets_file, 2),
            make_track("Character0_insert", "Face  Group", 20, assets_file, 7),
            make_track("Ignored", "Other Group", 30, assets_file, 1),
        ]
    )

    assert [track.name for track in tracks] == ["Character0", "Character0_insert"]
    assert [entry[1] for entry in timeline_track_enum(tracks)] == [
        "Motion Group / Character0 / 2 clips",
        "Face  Group / Character0_insert / 7 clips",
    ]
    assert [entry[0] for entry in timeline_track_enum(tracks)] == [
        f"{id(assets_file)}:10",
        f"{id(assets_file)}:20",
    ]


def test_catalog_ids_include_assets_file_identity_and_path_id_not_display_name():
    catalog_timeline_tracks = _load_catalog_functions()["catalog_timeline_tracks"]
    first_file = object()
    second_file = object()
    first = make_track("same display name", "Motion Group", 42, first_file)
    second = make_track("same display name", "Motion Group", 42, second_file)
    tracks = catalog_timeline_tracks([first, second])

    assert tracks[0].source_id != tracks[1].source_id
    assert tracks[0].source_id == f"{id(first_file)}:42"
    assert tracks[1].source_id == f"{id(second_file)}:42"
    assert tracks[0].name == tracks[1].name == "same display name"


def test_cached_lookup_and_enumeration_use_catalog_ids():
    catalog = _load_catalog_functions()
    tracks = catalog["catalog_timeline_tracks"]([
        make_track("Character0", "Motion Group", 42, object()),
    ])
    catalog["sssekai_global"].timeline_tracks = tracks
    catalog["sssekai_global"].timeline_track_enum = catalog["timeline_track_enum"](tracks)

    assert catalog["timeline_track_by_id"](tracks[0].source_id) is tracks[0]
    assert catalog["enumerate_timeline_tracks"](None) == catalog["timeline_track_enum"](tracks)


def test_catalog_does_not_use_external_mvdata_or_arbitrary_groups():
    catalog_timeline_tracks = _load_catalog_functions()["catalog_timeline_tracks"]
    tracks = catalog_timeline_tracks([
        make_track("not character", "Stage Group", 1, object()),
    ])
    assert tracks == []
    assert "mvdata.json" not in (ROOT / "blender/panels/importer.py").read_text()


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_"):
            value()
    print("task3 catalog tests passed")
