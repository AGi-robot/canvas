# Grace Canvas

Python drawing language and SVG renderer used by Grace. This package is a
library and command-line tool; it does not start a ROS node.

## Install

From this repository, install into your Python environment:

```sh
python -m pip install .
```

## Command-line tools

Render an action file to standalone SVG:

```sh
canvas render actions.json -o drawing.svg
```

Check actions and write normalized JSON:

```sh
canvas validate actions.json -o normalized.json
```

Input can be a JSON array of actions or an object with an `actions` array.
For example:

```json
{"actions": [{"kind": "ellipse", "x": 100, "y": 100, "width": 200, "height": 150, "fill": true, "fill_color": "#cc2222"}]}
```

Omit the input filename or use `-` to read standard input. Output goes to
standard output unless `-o` is supplied. `canvas render --no-grain` omits the
paper grain overlay. Invalid input returns exit status 2 with an error on stderr.
The same commands are available as `python -m canvas.cli`.


The production drawing adapter and eval share `build_draw_schema`, which defaults
to stable IDs, explicit hex paints, positive dimensions and kind-specific
geometry. `DRAW_TOOL` remains the extensible action-language definition for
clients that build their own schema. Install test dependencies with
`pip install -e '.[test]'` and run `pytest`.
