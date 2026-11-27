#!/usr/bin/env python3
"""E2E demo: cosmos3-edge (Jetson) paints, aiva-canvas (PC) renders.

Two passes, like AIVA's real loop:
  pass 1 - draft from the task text
  pass 2 - art review: the draft PNG is sent back as vision input and the
           model edits its own work (style/move/delete + additions)
No imagegen anywhere - the drawing is 100% vector, 100% local.
"""
import base64
import json
import re
import subprocess
import sys

from canvas import engine
from canvas import palette as palette_mod
from canvas import svg

TASK = ("Draw a still life on the canvas: a red apple with a stem and a leaf "
        "on a wooden table, soft morning light from the left casting a warm "
        "shadow to the right.")

REMOTE_TEMPLATE = r'''
import json, socket, http.client, glob, sys
payload = __PAYLOAD__

class U(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("localhost")
        self.p = sorted(glob.glob("/home/oppa-ai/.embedl/run/*/embedl.sock"))[0]
    def connect(self):
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.connect(self.p)
        self.sock = c

body = json.dumps({"model": "cosmos3-edge", "max_tokens": 1100,
                   "temperature": 0.4, "messages": payload["messages"]})
c = U()
c.request("POST", "/v1/chat/completions", body=body,
          headers={"Content-Type": "application/json",
                   "Content-Length": str(len(body))})
st = c.getresponse()
raw = st.read()
c.close()
if st.status != 200:
    print("HTTPERR", st.status, raw[:300].decode("utf-8", "replace"))
    sys.exit(1)
r = json.loads(raw)
print(json.dumps({"content": r["choices"][0]["message"]["content"],
                  "usage": r.get("usage", {})}))
'''


def repair_json_text(text):
    """Fix common small-model JSON slips so the parser gets a chance."""
    # unquoted or malformed hex colors: "color":#8d8e9 -> "color":"#8d8e900"
    text = re.sub(r'"(color|fill_color|gradient_color)"\s*:\s*#([0-9a-fA-F]{1,8})',
                  lambda m: f'"{m.group(1)}":"#{m.group(2)[:6].ljust(6, "0")}"', text)
    # quoted but wrong-length hex colors
    text = re.sub(r'"#([0-9a-fA-F]{1,5})"',
                  lambda m: f'"#{m.group(1).ljust(6, "0")}"', text)
    return text


def parse_model_draw(content):
    """canvas_draw JSON from model text; falls back to action salvage."""
    i = content.find("{")
    raw = content[i:]
    for text in (raw, repair_json_text(raw)):
        try:
            obj, _ = json.JSONDecoder().raw_decode(text)
            return obj.get("actions", []), obj.get("response", "")
        except json.JSONDecodeError:
            continue
    return engine.completed_stream_actions(repair_json_text(raw)), ""


def ask(messages):
    """One cosmos3-edge completion over SSH; returns (content, usage)."""
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "AuRoRA",
         "/home/oppa-ai/Aiko-chan/.venv/bin/python3 -"],
        input=REMOTE_TEMPLATE.replace("__PAYLOAD__", json.dumps({"messages": messages})),
        capture_output=True, text=True, timeout=600)
    if result.returncode != 0 or "HTTPERR" in result.stdout:
        print("remote failed:", result.stdout[-300:], result.stderr[-200:])
        sys.exit(1)
    reply = json.loads(result.stdout.strip().splitlines()[-1])
    print(f"  tokens: {reply['usage'].get('prompt_tokens')} in / "
          f"{reply['usage'].get('completion_tokens')} out")
    return reply["content"]


def render_png(actions, path, w=1000, h=650):
    out_svg = svg.render(actions, validate=False)
    with open(path.with_suffix(".svg"), "w") as f:
        f.write(out_svg)
    import cairosvg
    cairosvg.svg2png(bytestring=out_svg.encode(), write_to=str(path),
                     output_width=w, output_height=h)
    return str(path)


SYSTEM = (
    "You draw with vector shapes on a 1000x650 canvas. Reply with ONLY one "
    "JSON object: {\"actions\": [...], \"response\": \"...\"}\n\n"
    "Action grammar: curve = {\"kind\":\"curve\",\"points\":[[x,y],"
    "[c1x,c1y],[c2x,c2y],[ex,ey], ...]}, 1+3n points, fill:true closes+fills "
    "the shape. line = 2 points with color+size+stroke:true. "
    "path = connected points, smooth:true rounds. polygon = closed, auto-fill. "
    "rectangle/ellipse = x,y,width,height. style/move/delete/front/back take "
    "an id. paint props: color (outline), fill_color (interior), opacity, "
    "size (brush px), brush: ink|soft|marker, gradient optional.\n\n"
    "EXAMPLE - a coffee mug (do NOT copy these shapes; yours will differ):\n"
    "{\"actions\":["
    "{\"kind\":\"curve\",\"id\":\"mug\",\"points\":[[300,260],[280,320],[280,400],[310,460],[370,480],[430,470],[460,420],[470,340],[460,300],[440,260],[370,240],[300,260]],"
    "\"fill\":true,\"stroke\":false,\"fill_color\":\"#8c3a5a\"},"
    "{\"kind\":\"curve\",\"id\":\"handle\",\"points\":[[460,320],[510,310],[520,360],[480,390],[460,380]],"
    "\"fill\":false,\"stroke\":true,\"color\":\"#8c3a5a\",\"size\":6,\"brush\":\"ink\"},"
    "{\"kind\":\"ellipse\",\"id\":\"rim\",\"x\":300,\"y\":245,\"width\":140,\"height\":30,"
    "\"fill\":true,\"fill_color\":\"#c9a3a3\"}],"
    "\"response\":\"A mug.\"}\n\n"
    "Now draw the requested scene in exactly that JSON shape, 6-8 actions, "
    "with your OWN geometry and colors (always set fill_color on filled shapes "
    "and color on strokes).\n"
    "SCALE RULES: the canvas is BIG. The table spans nearly the full width "
    "(x=40..960) at y=470..560. The apple body is 260..340 px wide, sitting "
    "ON the table (bottom edge at y=490..520), centered near x=480. The stem "
    "and leaf sit on TOP of the apple. Shapes smaller than 150 px are wrong. "
    "Harmonious colors, light from the left, one cast shadow.")


def draft_pass():
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": TASK}]
    content = ask(messages)
    return parse_model_draw(content)


def review_pass(actions, draft_png):
    """Second pass: the model sees its own draft and edits it."""
    with open(draft_png, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    url = f"data:image/png;base64,{b64}"
    review_system = (
        "You are an art reviewer with editing actions on a 1000x650 canvas.\n"
        "Reply ONLY one JSON object: {\"actions\": [...], \"response\": \"...\"}.\n"
        "Available edits: style (id + color/fill_color/opacity/size), move "
        "(id + dx/dy), delete (id), front/back (id), plus NEW shapes "
        "(ellipse/rectangle/curve as usual, new unique ids).\n"
        "Look at the draft image. Fix what is off: sizes too small, wrong "
        "placement, missing shadow, missing shading. 4-8 actions. Do not "
        "restart the drawing; edit it.")
    history = [
        {"role": "system", "content": review_system},
        {"role": "user", "content": TASK},
        {"role": "assistant", "content": json.dumps({"actions": actions})},
        {"role": "user", "content": [
            {"type": "text", "text":
             "This is your draft. Review it and send the edit actions."},
            {"type": "image_url", "image_url": {"url": url}},
        ]},
    ]
    content = ask(history)
    return parse_model_draw(content)


def main():
    from pathlib import Path
    demo = Path(__file__).resolve().parent / "demo"
    demo.mkdir(exist_ok=True)

    print("== pass 1: draft ==")
    draft, response = draft_pass()
    print(f"  response: {response!r}")
    print(f"  actions: {len(draft)}")
    if not draft:
        print("no draft actions - aborting")
        return 1
    draft_valid = engine.validate_actions(engine.repair_model_actions(draft))
    draft_png = demo / "aiva_drawing_draft.png"
    render_png(draft_valid, draft_png)
    print(f"  wrote {draft_png.name}")

    print("== pass 2: art review (vision) ==")
    try:
        edits, response = review_pass(draft_valid, draft_png)
        print(f"  response: {response!r}")
        print(f"  actions: {len(edits)} -> {json.dumps(edits)[:200]}")
    except SystemExit:
        print("  review pass failed (likely 413 input cap) - keeping draft")
        edits = []

    final = draft_valid + engine.validate_actions(
        engine.repair_model_actions(edits))
    harmonized = palette_mod.harmonize_actions(final, scheme='balanced')

    out = render_png(harmonized, demo / "aiva_drawing.png")
    print(f"wrote {out}")
    raw = render_png(final, demo / "aiva_drawing_raw.png")
    print(f"wrote {raw} (no palette harmonization)")
    (demo / "actions.json").write_text(json.dumps(final, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
