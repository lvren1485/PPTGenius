"""Validation test suite — element-level parallel validation.

Covers:
  - validate_instruction() for full PPTInstruction
  - validate_elements() for flat element list (chart_agent / table_agent output)
  - ALL errors collected per-element, regardless of other elements on the same slide
"""

import json, sys, os

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(backend_dir, "src"))

from pptgenius.infrastructure.ppt_engine import validate_instruction, validate_elements


def assert_valid(result, label):
    if result.is_valid:
        print(f"  PASS: {label}")
    else:
        print(f"  FAIL: {label} — expected valid, got {len(result.errors)} errors")
        for e in result.errors[:5]:
            print(f"    {e['path']}: {e['error']}")
    return result


def assert_invalid(result, label, expected_min=1):
    if not result.is_valid and len(result.errors) >= expected_min:
        print(f"  PASS: {label} ({len(result.errors)} errors, min={expected_min})")
    else:
        print(f"  FAIL: {label} — expected >= {expected_min} errors, got {len(result.errors)}")
        for e in result.errors:
            print(f"    {e['path']}: {e['error']}")
    return result


# ═══════════════════════════════════════════════════════════════════════
print("=== Test 1: Valid full instruction ===")
with open(os.path.join(os.path.dirname(__file__), "test_all_elements.json"), "r", encoding="utf-8") as f:
    assert_valid(validate_instruction(json.load(f)), "test_all_elements.json (16 slides)")


# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 2: validate_elements — flat list (agent partial output) ===")
chart_elements = [
    {"type": "chart", "chart_type": "column_clustered",
     "position": {"left": 1, "top": 1, "width": 8, "height": 5},
     "data": {"categories": ["Q1","Q2"], "series": [{"name":"s1","values":[1,2]}]}},
    {"type": "chart", "chart_type": "pie",
     "position": {"left": 1, "top": 1, "width": 8, "height": 5},
     "data": {"categories": ["A","B"], "series": [
         {"name":"s1","values":[10,20]}, {"name":"s2","values":[5,15]}]}},
    {"type": "textbox",
     "position": {"left": 1, "top": 1, "width": 8, "height": 2},
     "content": [{"paragraph": {"runs": []}}]}
]
assert_valid(validate_elements([chart_elements[0]]), "1 valid chart element")
assert_invalid(validate_elements([chart_elements[1]]), "pie with 2 series", expected_min=1)
r = assert_invalid(validate_elements(chart_elements), "3 mixed elements = 2 bad caught (pie+textbox)", expected_min=2)


# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 3: Element-level parallel — bad element doesn't block good ones ===")
multi_error = {
    "meta": {"slide_width": 13.333, "slide_height": 7.5},
    "slides": [{"layout": "blank", "elements": [
        # element 0: valid chart (should pass semantic checks)
        {"type": "chart", "chart_type": "column_clustered",
         "position": {"left": 1, "top": 1, "width": 8, "height": 5},
         "data": {"categories": ["A"], "series": [{"name":"x","values":[1]}]}},
        # element 1: table with OOB cells
        {"type": "table",
         "position": {"left": 1, "top": 1, "width": 10, "height": 5},
         "rows": 2, "cols": 2,
         "cells": [{"row": 5, "col": 0, "text": "bad"}, {"row": 0, "col": 9, "text": "bad"}]},
        # element 2: invalid shape_type (Pydantic error)
        {"type": "shape", "shape_type": "not_a_real_shape",
         "position": {"left": 1, "top": 1, "width": 3, "height": 2}},
        # element 3: textbox no runs
        {"type": "textbox",
         "position": {"left": 1, "top": 1, "width": 8, "height": 2},
         "content": [{"paragraph": {"runs": []}}]},
        # element 4: picture empty path
        {"type": "picture",
         "position": {"left": 1, "top": 1, "width": 5}, "path": ""},
        # element 5: valid textbox (should pass)
        {"type": "textbox",
         "position": {"left": 1, "top": 1, "width": 8, "height": 2},
         "content": [{"paragraph": {"runs": [{"text": "hello"}]}}]},
    ]}]
}
r = assert_invalid(validate_instruction(multi_error),
                   "6 elements: 4 errors (table OOB+shape type+no runs+empty path), 2 pass",
                   expected_min=4)
print("  ALL errors on same slide — no blocking:")
for e in r.errors:
    print(f"    {e['path']}: {e['error']}")


# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 4: Multi-slide parallelism ===")
multi_slide = {
    "meta": {"slide_width": 13.333, "slide_height": 7.5},
    "slides": [
        {"layout": "blank", "elements": [
            {"type": "chart", "chart_type": "pie",
             "position": {"left": 1, "top": 1, "width": 8, "height": 5},
             "data": {"categories": ["A","B"], "series": [
                 {"name":"s1","values":[1,2]}, {"name":"s2","values":[3,4]}]}}]},
        {"layout": "blank", "elements": [
            {"type": "chart", "chart_type": "scatter",
             "position": {"left": 1, "top": 1, "width": 8, "height": 5},
             "data": {"series": [{"name":"empty","points":[]}]}}]},
        {"layout": "blank", "elements": [
            {"type": "table", "rows": 2, "cols": 1,
             "position": {"left": 1, "top": 1, "width": 10, "height": 5},
             "cells": [{"row": 3, "col": 0, "text": "bad"}]}]},
        {"layout": "blank", "elements": [
            {"type": "chart", "chart_type": "doughnut",
             "position": {"left": 1, "top": 1, "width": 8, "height": 5},
             "data": {"categories": ["A","B"], "series": [
                 {"name":"s1","values":[1,2]}, {"name":"s2","values":[3,4]}]}}]},
    ]
}
assert_invalid(validate_instruction(multi_slide),
               "4 slides with errors, all caught in parallel", expected_min=4)


# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 5: Pydantic type/enum errors (per-element) ===")
assert_invalid(validate_instruction({
    "meta": {}, "slides": [{"layout": "blank", "elements": [
        {"type": "chart", "chart_type": "unknown_chart",
         "position": {"left": 1, "top": 1, "width": 8, "height": 5},
         "data": {"categories": ["A"], "series": [{"name":"x","values":[1]}]}}
    ]}]
}), "unknown chart_type per-element", expected_min=1)

assert_invalid(validate_elements([
    {"type": "chart"}  # missing position + data
]), "missing required fields per-element", expected_min=2)


# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 6: Unknown element type ===")
assert_invalid(validate_elements([
    {"type": "unknown_xyz", "foo": "bar"}
]), "unknown element type", expected_min=1)

assert_invalid(validate_instruction({
    "meta": {}, "slides": [{"layout": "blank", "elements": [
        {"type": "video"}  # not supported
    ]}]
}), "unsupported type in full instruction", expected_min=1)


# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 7: Empty slides / no meta ===")
assert_invalid(validate_instruction({"meta": {}, "slides": []}), "empty slides", expected_min=1)
result = validate_elements([])
if result.is_valid and len(result.errors) == 0:
    print("  PASS: empty element list (is_valid=True, 0 errors — technically valid)")
else:
    print(f"  FAIL: empty element list — is_valid={result.is_valid}, errors={len(result.errors)}")

print("\n=== All validation tests complete ===")
