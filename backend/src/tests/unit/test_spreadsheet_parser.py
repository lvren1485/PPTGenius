"""Test spreadsheet parser: small → full Markdown, large → summary."""

from pathlib import Path

from pptgenius.infrastructure.rag.parser import parse_file
from pptgenius.infrastructure.rag.parser.base import ParsedDocument

_RESOURCES = Path(__file__).parent.parent / "resources"


def assert_pass(cond, label):
    if cond:
        print(f"  PASS: {label}")
    else:
        print(f"  FAIL: {label}")
    return cond


# ═══════════════════════════════════════════════════════════════════════
print("=== Test 1: Small CSV (≤30 cells) → full Markdown table ===")
doc = parse_file(_RESOURCES / "test_sales_small.csv")
assert_pass(doc.file_type == "csv", f"file_type={doc.file_type}")
assert_pass(doc.metadata["total_cells"] == 15, f"cells=15 → small path (got {doc.metadata['total_cells']})")
assert_pass("Region" in doc.text and "East" in doc.text, "data in Markdown table")
# Small path must NOT contain "Summary"
assert_pass("Summary" not in doc.text, "small sheet = full table, no 'Summary' header")
print(f"  small output: {len(doc.text)} chars, {doc.text.count(chr(10))} lines")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 2: Large CSV (>30 cells) → statistical summary ===")
doc = parse_file(_RESOURCES / "test_sales_large.csv")
assert_pass(doc.file_type == "csv", f"file_type={doc.file_type}")
assert_pass(doc.metadata["total_cells"] == 600, f"cells=600 → summary path (got {doc.metadata['total_cells']})")

# ── Section presence ──
assert_pass("## Sheet: test_sales_large (Summary)" in doc.text, "title with 'Summary'")
assert_pass("### Overview" in doc.text, "Overview section")
assert_pass("### Column Profiles" in doc.text, "Column Profiles section")
assert_pass("### Numeric Statistics" in doc.text, "Numeric Statistics section")
assert_pass("### Categorical Summary" in doc.text, "Categorical Summary section")
assert_pass("### Data Preview" in doc.text, "Data Preview section")

# ── Overview assertions ──
assert_pass("**Rows:** 60" in doc.text, "rows=60")
assert_pass("**Columns:** 10" in doc.text, "cols=10")
assert_pass("**Total cells:** 600" in doc.text, "total=600")

# ── Column Profiles assertions ──
assert_pass("| 1 | Region | str | 60 | 0.0% | 5 |" in doc.text, "profile: Region str 5 unique")
assert_pass("| 3 | Product | str | 60 | 0.0% | 7 |" in doc.text, "profile: Product str 7 unique")
assert_pass("| 5 | Sales | int64 | 60 | 0.0%" in doc.text, "profile: Sales int64")
assert_pass("| 7 | Profit | int64 | 60 | 0.0%" in doc.text, "profile: Profit int64")

# ── Numeric Statistics assertions ──
assert_pass("#### Sales (int64)" in doc.text, "numeric: Sales header")
assert_pass("| Min | 2900 |" in doc.text, "Sales min=2900")
assert_pass("| Max | 31000 |" in doc.text, "Sales max=31000")
assert_pass("| Median |" in doc.text and "Sales" in doc.text, "median present")
assert_pass("| Std |" in doc.text, "std present")
assert_pass("| Variance |" in doc.text, "variance present")
assert_pass("| Q1 (25%) |" in doc.text, "Q1 present")
assert_pass("| Q3 (75%) |" in doc.text, "Q3 present")
assert_pass("| Skewness |" in doc.text, "skew present")
assert_pass("| Sum |" in doc.text, "sum present")

assert_pass("#### Profit (int64)" in doc.text, "numeric: Profit header")
assert_pass("#### Quantity (int64)" in doc.text, "numeric: Quantity header")
assert_pass("#### Discount (float64)" in doc.text, "numeric: Discount float")
assert_pass("#### Rating (float64)" in doc.text, "numeric: Rating float")

# ── Categorical assertions ──
assert_pass("#### Region" in doc.text, "categorical: Region")
assert_pass("#### Category" in doc.text, "categorical: Category")
assert_pass("#### Product" in doc.text, "categorical: Product")
assert_pass("#### Month" in doc.text, "categorical: Month")
assert_pass("#### Returned" in doc.text, "categorical: Returned")

# Region has 5 unique values → top10 should list all 5
for region in ["East", "West", "North", "South", "Central"]:
    assert_pass(region in doc.text, f"Region top10 includes '{region}'")

# Returned has Yes/No
assert_pass("Yes" in doc.text and "No" in doc.text, "Returned has Yes/No values")

# ── Data Preview assertions ──
assert_pass("Data Preview (first 50 rows)" in doc.text, "preview: 50 rows header")
assert_pass("| East | Electronics | Smartphone |" in doc.text, "preview: first data row")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 3: Sheet with headers but no data ===")
from pptgenius.infrastructure.rag.parser.spreadsheet_parser import parse_spreadsheet
import tempfile, os

# CSV with only headers (no data rows)
tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", encoding="utf-8-sig")
tmp.write("A,B,C\n")
tmp.close()

doc = parse_spreadsheet(tmp.name)
os.unlink(tmp.name)
assert_pass("empty sheet" in doc.text.lower(), f"empty (header only): {doc.text[:100].strip()}")
assert_pass(doc.metadata["total_cells"] == 0, "total_cells=0 for header-only")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 4: Sheet with nulls ===")
import pandas as pd, numpy as np
np.random.seed(1)
df = pd.DataFrame({
    "Name": np.random.choice(["Alice", "Bob", "Diana", "Eve", "Frank", "Grace", "Henry"], 50),
    "Score": np.random.choice([85.0, np.nan, 78.0, 92.0, np.nan, 88.0, 65.0, 99.0, 72.0, np.nan], 50),
    "Grade": np.random.choice(["B", "C", "A", "D"], 50),
    "Dept": np.random.choice(["Eng", "Sales", "HR"], 50),
})
tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", encoding="utf-8-sig")
df.to_csv(tmp.name, index=False)
tmp.close()

doc = parse_spreadsheet(tmp.name)
os.unlink(tmp.name)
assert_pass("Density:" in doc.text and "non-null" in doc.text.lower(), "density reported")
assert_pass("Column Profiles" in doc.text, "profiles for null-containing data")
assert_pass("| 1 | Name |" in doc.text, "Name column in profile")
# Score: numeric float column with NaN values — stats should handle it
assert_pass("Score" in doc.text and "Min |" in doc.text and "Max |" in doc.text, "Score numeric stats present")
assert_pass("| Mean |" in doc.text and "| Median |" in doc.text, "Score has mean/median")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== Test 5: Single-numeric-column edge case ===")
import pandas as pd
df = pd.DataFrame({"Value": [10.5, 20.3, 30.7]})  # 3 cells ≤ 30 → small path
tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", encoding="utf-8-sig")
df.to_csv(tmp.name, index=False)
tmp.close()

doc = parse_spreadsheet(tmp.name)
os.unlink(tmp.name)
assert_pass("Sheet:" in doc.text and "Summary" not in doc.text,
            "≤30 cells → full table, no summary")
assert_pass("10.5" in doc.text and "20.3" in doc.text, "all values in small table")

print("\n=== All spreadsheet parser tests complete ===")
