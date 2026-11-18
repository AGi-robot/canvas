import io
import json
import xml.etree.ElementTree as ET

import pytest

from canvas.cli import main


SHAPE = {
    "kind": "ellipse", "x": 100, "y": 100, "width": 200, "height": 150,
    "fill": True, "fill_color": "#cc2222",
}


def test_render_action_envelope_to_svg_file(tmp_path):
    source = tmp_path / "actions.json"
    target = tmp_path / "drawing.svg"
    source.write_text(json.dumps({"actions": [SHAPE]}), encoding="utf-8")
    assert main(["render", str(source), "-o", str(target), "--no-grain"]) == 0
    svg = ET.fromstring(target.read_text(encoding="utf-8"))
    assert svg.tag == "{http://www.w3.org/2000/svg}svg"
    assert any(element.get("fill") == "#cc2222" for element in svg.iter())
    assert 'filter="url(#grain)"' not in target.read_text(encoding="utf-8")


def test_validate_stdin_outputs_normalized_actions(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([SHAPE])))
    assert main(["validate"]) == 0
    actions = json.loads(capsys.readouterr().out)
    assert actions[0]["kind"] == "ellipse"
    assert actions[0]["fill_color"] == "#cc2222"


@pytest.mark.parametrize("payload", ['{', '{}', '[{"kind":"unknown"}]'])
def test_invalid_input_returns_error_without_svg(payload, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    with pytest.raises(SystemExit) as error:
        main(["render"])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("canvas: ")


def test_missing_input_reports_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        main(["render", str(tmp_path / "missing.json")])
    assert error.value.code == 2
    assert "canvas: " in capsys.readouterr().err
