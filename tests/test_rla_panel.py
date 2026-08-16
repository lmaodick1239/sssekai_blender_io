"""Regression coverage for RLA panel enum callback behavior."""

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PANEL_SOURCE = ROOT / "blender/panels/sekai_rla.py"
EMPTY_RLA_ENUM = [("NONE", "None", "", 0)]


def _load_enumerator(*, bundle_error):
    tree = ast.parse(PANEL_SOURCE.read_text(encoding="utf-8"), filename=str(PANEL_SOURCE))
    panel = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SSSekaiRLAImportPanel"
    )
    method = next(
        node
        for node in panel.body
        if isinstance(node, ast.FunctionDef) and node.name == "enumerate_rla_assets"
    )
    namespace = {
        "os": SimpleNamespace(path=SimpleNamespace(isfile=lambda _: True)),
        "open": lambda *_args, **_kwargs: (_ for _ in ()).throw(bundle_error),
        "sssekai_global": SimpleNamespace(
            rla_sekai_streaming_live_bundle_path=None,
            rla_enum_entries=None,
            rla_raw_clips={},
        ),
        "logger": SimpleNamespace(debug=lambda *_: None, error=lambda *_: None),
    }
    module = ast.Module(body=[method], type_ignores=[])
    exec(compile(module, str(PANEL_SOURCE), "exec"), namespace)
    return namespace["enumerate_rla_assets"]


def test_rla_enum_callback_returns_fallback_sequence_when_bundle_load_fails():
    enumerate_rla_assets = _load_enumerator(bundle_error=OSError("not an RLA archive"))
    context = SimpleNamespace(
        window_manager=SimpleNamespace(sssekai_streaming_live_archive_bundle="unitysource/character")
    )

    assert enumerate_rla_assets(None, context) == EMPTY_RLA_ENUM
