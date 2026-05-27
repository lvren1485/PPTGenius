"""Icon search + color replacement tests.

Covers:
  - search_icons(query)  → top-5 by tag/category/name
  - get_colored_svg()    → SVG loaded, color replaced, temp saved
  - cleanup_temp_icons() → temp dir removed
  - validate_elements()  → name+color field checks
  - validate_instruction() → icon in full instruction
  - Full PPT generation   → icon slide renders correctly
"""

import json, os, sys, asyncio

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(backend_dir, "src"))

from pptgenius.infrastructure.ppt_engine import (
    validate_instruction,
    validate_elements,
    generate_ppt,
    search_icons,
)
from pptgenius.infrastructure.ppt_engine.icon_search import (
    get_colored_svg,
    cleanup_temp_icons,
)


def assert_pass(cond, label):
    if cond:
        print(f"  PASS: {label}")
    else:
        print(f"  FAIL: {label}")
    return cond


# ═══════════════════════════════════════════════════════════════════════
print("=== Test 1: search_icons ===")
r = search_icons("growth")
assert_pass(len(r) >= 3 and r[0]["name"] == "growth", f"search('growth') → top={len(r)}, first='{r[0]['name']}'")

r = search_icons("business")
assert_pass(len(r) >= 3, f"search('business') → {len(r)} results")
assert_pass(r[0]["name"] == "businessplan", f"first='{r[0]['name']}' score={r[0]['score']}")

r = search_icons("chart")
assert_pass(len(r) >= 5, f"search('chart') → {len(r)} results")
assert_pass(all("chart" in item["name"].lower() or item["category"] == "Charts" for item in r),
            "all chart results are chart-related")

r = search_icons("heart love")
assert_pass(len(r) >= 2, f"search('heart love') → {len(r)} results (cross-word)")

r = search_icons("nonexistent_xyz_12345")
assert_pass(len(r) == 0, f"search('nonexistent...') → 0 results")

r = search_icons("star")
assert_pass(any(item["name"] == "star" for item in r), "search('star') includes 'star' icon")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 2: get_colored_svg + cleanup ===")
workspace = os.path.join(backend_dir, "data", "test_output")
os.makedirs(workspace, exist_ok=True)

rel_path = get_colored_svg("chart-line", "3B82F6", workspace)
abs_path = os.path.join(workspace, rel_path)
assert_pass(os.path.exists(abs_path), f"colored SVG exists: {rel_path}")

with open(abs_path, "r", encoding="utf-8") as f:
    content = f.read()
assert_pass('stroke="#3B82F6"' in content, "stroke='#3B82F6' applied")
assert_pass("currentColor" not in content, "currentColor removed")

# Test color with hash prefix
rel_path2 = get_colored_svg("star", "#FF0000", workspace)
abs_path2 = os.path.join(workspace, rel_path2)
with open(abs_path2, "r", encoding="utf-8") as f:
    content2 = f.read()
assert_pass('stroke="#FF0000"' in content2, "color with # prefix works")

# Test cleanup
cleanup_temp_icons(workspace)
assert_pass(not os.path.exists(abs_path), "temp SVG cleaned")
assert_pass(not os.path.exists(abs_path2), "temp SVG2 cleaned")
assert_pass(not os.path.exists(os.path.join(workspace, ".temp_icons")), "temp dir removed")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 3: Validation — name+color fields ===")

# Valid: path mode
r = validate_elements([{
    "type": "picture", "position": {"left": 1, "top": 1, "width": 5},
    "path": "images/photo.png"
}])
assert_pass(r.is_valid, "valid path mode")

# Valid: name+color mode
r = validate_elements([{
    "type": "picture", "position": {"left": 1, "top": 1, "width": 5},
    "name": "chart-line", "color": "3B82F6"
}])
assert_pass(r.is_valid, "valid name+color mode")

# Invalid: missing both
r = validate_elements([{
    "type": "picture", "position": {"left": 1, "top": 1, "width": 5}
}])
assert_pass(not r.is_valid and any("path" in e["error"] or "name" in e["error"] for e in r.errors),
            f"missing path/name caught: {[e['error'] for e in r.errors]}")

# Invalid: name without color
r = validate_elements([{
    "type": "picture", "position": {"left": 1, "top": 1, "width": 5},
    "name": "chart-line"
}])
assert_pass(not r.is_valid and any("color" in e["error"] for e in r.errors),
            f"name without color caught: {[e['error'] for e in r.errors]}")

# Invalid: non-existent icon name
r = validate_elements([{
    "type": "picture", "position": {"left": 1, "top": 1, "width": 5},
    "name": "nonexistent_icon_xyz", "color": "FF0000"
}])
assert_pass(not r.is_valid and any("not found" in e["error"] for e in r.errors),
            f"invalid icon caught: {[e['error'] for e in r.errors]}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 4: Validation — icon in full instruction ===")

icon_instruction = {
    "meta": {},
    "slides": [{
        "layout": "blank",
        "elements": [
            {"type": "picture", "position": {"left": 1, "top": 1, "width": 3, "height": 3},
             "name": "chart-arcs-3", "color": "ea4335", "fit": "aspect"},
        ]
    }]
}
r = validate_instruction(icon_instruction)
assert_pass(r.is_valid, "full instruction with icon passes")

# Multi-element: mixed path + name
mixed_instruction = {
    "meta": {},
    "slides": [{
        "layout": "blank",
        "elements": [
            {"type": "picture", "position": {"left": 1, "top": 1, "width": 3},
             "path": "images/photo.png"},
            {"type": "picture", "position": {"left": 5, "top": 1, "width": 3, "height": 3},
             "name": "star", "color": "fbbc04"},
            {"type": "picture", "position": {"left": 9, "top": 1, "width": 3, "height": 3},
             "name": "nonexistent_bad", "color": "000000"},
        ]
    }]
}
r = validate_instruction(mixed_instruction)
assert_pass(not r.is_valid and len(r.errors) >= 1, f"mixed: 2 pass + 1 bad icon, errors={len(r.errors)}")
for e in r.errors:
    print(f"    {e['path']}: {e['error']}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 5: Full PPT — icon slide (17 slides) ===")

async def run_full_ppt():
    test_json = os.path.join(os.path.dirname(__file__), "test_all_elements.json")
    output = os.path.join(backend_dir, "data", "test_output", "test_output.pptx")

    with open(test_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Verify icon slide exists (slide 17)
    icon_slides = [s for s in data["slides"] if any(
        e.get("name") for e in s.get("elements", [])
    )]
    assert_pass(len(icon_slides) == 1, f"icon slide count: {len(icon_slides)}")

    result = await generate_ppt(data, output, backend_dir)
    if result["ok"]:
        assert_pass(result["slide_count"] == 17, f"17 slides generated (was {result['slide_count']})")
        assert_pass(result["file_size"] > 100000, f"file size OK ({result['file_size']} bytes)")

        # Verify cleanup
        temp_dir = os.path.join(backend_dir, ".temp_icons")
        assert_pass(not os.path.exists(temp_dir), "temp icons cleaned up after generation")
    else:
        print(f"  FAIL: generation errors:")
        for e in result.get("errors", []):
            print(f"    {e['path']}: {e['error']}")

asyncio.run(run_full_ppt())

print("\n=== All icon tests complete ===")
