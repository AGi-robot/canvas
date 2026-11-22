"""canvas - Grace's vector drawing engine.

The language: `canvas.engine` (validate/normalize actions)
The output:  `canvas.svg` (replay actions into standalone SVG)
The beauty:  `canvas.stroke` (pressure-tapered strokes), `canvas.palette`
             (hue harmonization - a deliberate beauty floor)
"""
from .engine import (KINDS, ACTION_SCHEMA, DRAW_TOOL, DRAW_INSTRUCTIONS,
                     validate_actions, repair_model_actions, canvas_context,
                     drawing_history, drawing_summary,
                     completed_stream_actions, register_action_kind,
                     build_draw_tool, build_draw_schema)
from .svg import render

__all__ = ['KINDS', 'ACTION_SCHEMA', 'DRAW_TOOL', 'DRAW_INSTRUCTIONS',
           'validate_actions', 'repair_model_actions', 'canvas_context',
           'drawing_history', 'drawing_summary', 'completed_stream_actions',
           'register_action_kind', 'build_draw_tool', 'build_draw_schema', 'render']
__version__ = '0.2.0'
