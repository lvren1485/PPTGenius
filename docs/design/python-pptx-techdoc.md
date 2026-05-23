# python-pptx 技术调研报告

> 日期：2026-06-03
> 调研范围：模板(制作/加载)、字体(含效果)、颜色、图表、表格、Shape(含渐变/图片填充)、背景、Agent Tool、DB 变更

---

## 一、核心发现摘要

| 能力 | 支持程度 | 关键限制 |
|------|---------|---------|
| **模板加载** | 完全支持 | `Presentation("template.pptx")` 即可 |
| **模板制作** | **不能通过高层 API 创建** | 必须 lxml 构造 XML，或视觉设计后加载 |
| **图表** | 原生支持 | 不支持 3D 变体，不支持组合图(多 plot) |
| **表格** | 基本支持 | 边框/单元格背景色需 lxml |
| **字体效果** | 基础可用 | bold/italic/underline/size/name/color 有 API；**阴影仅有粗粒度开关**；描边/发光/倒影/删除线/小型大写/字距均需 lxml |
| **颜色(图表)** | 系列/点/轴/标题有 .format | 图表区/绘图区背景需 lxml |
| **颜色(表格)** | 文字色有 API，填充有 API | 单元格边框需 lxml |
| **SVG** | **不支持** | 需 cairosvg → PNG，或 Inkscape → EMF |
| **Shape API** | 182 种形状完全支持 | 位置/尺寸/旋转/调节柄均可 |
| **Shape 纯色填充** | ✅ API | `shape.fill.solid()` + `fore_color.rgb/theme_color` |
| **Shape 渐变填充** | 基本支持 | 仅线性渐变(API)，径向渐变需 lxml；多 stop 需 lxml |
| **Shape 图片填充** | **无 API** | 需 lxml 构造 `<a:blipFill>` |
| **Shape 文字** | ✅ API | `shape.text` 简写或 `shape.text_frame.paragraphs[0].add_run()` |
| **幻灯片背景(纯色)** | ✅ API | `slide.background.fill.solid()` + `fore_color.rgb` |
| **幻灯片背景(渐变)** | ✅ API | `slide.background.fill.gradient()` + `gradient_angle` |
| **幻灯片背景(图片)** | **无 API** | 变通：全幅图片 shape 覆盖，或 lxml 操作 `p:bgPr` |
| **模板 JSON 存储** | ✅ 推荐 | layout + element 定义存为 JSON，agent 按需拼接 |

---

## 二、模板

### 2.1 模板加载 — 完全支持

```python
from pptx import Presentation

# 加载自定义模板（.pptx 文件）
prs = Presentation("template.pptx")

# 使用模板中的 slide layout
for i, layout in enumerate(prs.slide_layouts):
    print(f"Layout {i}: {layout.name}")
    for ph in layout.placeholders:
        print(f"  ph idx={ph.placeholder_format.idx} type={ph.placeholder_format.type}")

# 按 layout 创建幻灯片
slide = prs.slides.add_slide(prs.slide_layouts[1])

# 访问占位符
slide.placeholders[0].text = "标题"            # idx=0 总是 title
chart_frame = chart_ph.insert_chart(...)       # 图表占位符
table_frame = table_ph.insert_table(rows=3, cols=4)  # 表格占位符
picture = pic_ph.insert_picture("img.png")     # 图片占位符
```

**占位符 idx 约定**：内置布局 idx 范围 0-5（title=0），用户自定义占位符 idx 从 10 开始。

**标准布局顺序**（约定，非保证）：

| idx | 名称 | 用途 |
|-----|------|------|
| 0 | Title Slide | 标题 + 副标题 |
| 1 | Title and Content | 标题 + 内容 |
| 2 | Section Header | 章节标题 |
| 3 | Two Content | 双栏内容 |
| 4 | Comparison | 双栏对比 |
| 5 | Title Only | 仅标题 |
| 6 | Blank | 空白 |
| 7 | Content with Caption | 内容 + 说明 |
| 8 | Picture with Caption | 图片 + 说明 |

### 2.2 模板制作 — 不能通过高层 API 创建

**结论：python-pptx 没有 `add_slide_layout()` 或 `add_placeholder()` 方法。** `SlideLayouts` 集合只支持 `get_by_name()`、`index()`、`remove()`。

**两条路径**：

#### 路径 A：在 PowerPoint 中视觉设计（推荐）

1. 打开 PowerPoint → 视图 → 幻灯片母版
2. 设计自定义 layout（添加占位符、设置背景、字体、颜色）
3. 保存为 `template.pptx`
4. python-pptx 加载：`prs = Presentation("template.pptx")`

**优点**：所见即所得，可利用全部 PowerPoint 设计能力（主题色、字体方案、背景图形等）
**缺点**：模板数量固定，不可运行时动态创建新 layout

#### 路径 B：lxml 构造 XML（高级）

通过直接操作 `p:sldLayout` XML 创建 layout，添加 `p:sp` 占位符：

```python
from lxml import etree
from pptx.oxml.ns import qn
import copy

def add_custom_layout(master, name, placeholders_config):
    """在 slide master 上追加自定义 layout"""
    # 深拷贝现有 layout 的 XML 作为模板
    existing = master.slide_layouts[0]._element
    layout_el = copy.deepcopy(existing)

    # 设置唯一 ID 和名称
    max_id = max(int(el.get('id') or 0) for el in master._element.findall(qn('p:sldLayout')))
    layout_el.set('id', str(max_id + 1))

    cSld = layout_el.find(qn('p:cSld'))
    cSld.set('name', name)

    # 清空并重建 spTree 中的占位符...
    spTree = cSld.find(qn('p:spTree'))
    for sp in list(spTree.findall(qn('p:sp'))):
        spTree.remove(sp)

    shape_id = 2
    for cfg in placeholders_config:
        _add_placeholder(spTree, shape_id, cfg)
        shape_id += 1

    master._element.append(layout_el)
```

**优点**：完全编程化，可动态生成任意 layout
**缺点**：代码复杂，需要深入理解 OpenXML schema，维护成本高

### 2.3 三路径对比

| 维度 | 路径 A (视觉设计) | 路径 B (lxml) | 路径 C (纯代码无模板) |
|------|-----------------|--------------|-------------------|
| 复杂度 | 低 | 极高 | 中 |
| 灵活性 | 中 (预设) | 极高 | 高 (每次动态) |
| 可维护性 | 高 | 低 | 高 |
| 主题继承 | 自动 | 需手动 | 无 |
| 适用场景 | 品牌固定 | 全动态场景 | 风格多变 |

### 2.4 对架构的建议

**混合方案**：
- `resources/templates/` 放 3-5 个 .pptx 模板（商务、学术、创意、简约、暗色）
- `layout_agent` 负责：① 选择模板 ② 从模板中选择合适的 layout
- 对于模板中不存在的特殊 layout，回退到纯代码方案（在 blank layout 上用 add_textbox/add_table/add_chart 自由布局）
- **不采用路径 B**（lxml 构造 layout），投入产出比太低

---

## 三、图表

### 3.1 图表类型支持

python-pptx 支持以下图表类型（全部可通过 `XL_CHART_TYPE` 枚举）：

| 类别 | 支持的类型 |
|------|----------|
| 柱形图 | CLUSTERED, STACKED, 100% STACKED |
| 条形图 | CLUSTERED, STACKED, 100% STACKED |
| 折线图 | LINE, LINE_MARKERS, STACKED, 100% STACKED |
| 饼图 | PIE, PIE_EXPLODED |
| 环形图 | DOUGHNUT, DOUGHNUT_EXPLODED |
| 面积图 | AREA, STACKED, 100% STACKED |
| 散点图 | XY_SCATTER, XY_SCATTER_LINES, XY_SCATTER_LINES_NO_MARKERS |
| 气泡图 | BUBBLE, BUBBLE_3D_EFFECT |
| 雷达图 | RADAR, RADAR_FILLED, RADAR_MARKERS |
| **不支持** | 3D 变体、组合图(柱+折)、股价图、曲面图 |

### 3.2 图表颜色 — 逐元素能力清单

| 图表元素 | 有 .format？ | 填充色 | 线条色 | 实现方式 |
|----------|-------------|--------|--------|---------|
| **图表区** (chart area) | **无** | ✅ lxml | ✅ lxml | `chart._element.append(spPr)` |
| **绘图区** (plot area) | **无** | ✅ lxml | ✅ lxml | `chart._element.chart.plotArea.append(spPr)` |
| 图表标题 | ✅ | ✅ API | ✅ API | `chart.chart_title.format.fill/line` |
| 坐标轴 | ✅ | ✅ API | ✅ API | `chart.category_axis.format.fill/line` |
| 网格线 | ✅ | - | ✅ API | `chart.value_axis.major_gridlines.format.line` |
| 系列 (series) | ✅ | ✅ API | ✅ API | `chart.series[0].format.fill/line` |
| 数据点 (point) | ✅ | ✅ API | ✅ API | `chart.series[0].points[2].format.fill/line` |
| 数据标记 (marker) | ✅ | ✅ API | ✅ API | `chart.series[0].marker.format.fill/line` |
| 数据标签 | **无** | - | - | 仅 `font` 属性可设文字样式 |
| 图例 | **无** | - | - | 仅 `font` 属性 + `position` |

#### 图表区/绘图区背景示例（lxml）

```python
from pptx.oxml.xmlchemy import OxmlElement

# 图表区背景
spPr = OxmlElement("c:spPr")
solidFill = OxmlElement("a:solidFill")
srgbClr = OxmlElement("a:srgbClr")
srgbClr.set("val", "F5F5F5")       # 浅灰
solidFill.append(srgbClr)
spPr.append(solidFill)
chart._element.append(spPr)

# 绘图区背景
plotArea = chart._element.chart.plotArea
spPr2 = OxmlElement("c:spPr")
noFill = OxmlElement("a:noFill")   # 透明
spPr2.append(noFill)
plotArea.append(spPr2)
```

#### 系列/数据点颜色示例（API）

```python
from pptx.dml.color import RGBColor

# 系列填充
series = chart.series[0]
series.format.fill.solid()
series.format.fill.fore_color.rgb = RGBColor(0x1a, 0x73, 0xe8)

# 系列线条（折线图）
series.format.line.color.rgb = RGBColor(0xea, 0x43, 0x35)
series.format.line.width = Pt(2.5)

# 单个数据点高亮
point = chart.series[0].points[3]
point.format.fill.solid()
point.format.fill.fore_color.rgb = RGBColor(0xff, 0x00, 0x00)

# 网格线颜色
chart.value_axis.major_gridlines.format.line.color.rgb = RGBColor(0xd0, 0xd0, 0xd0)
```

### 3.3 结论：图表颜色几乎完全可控

- 系列/数据点/轴/标题/网格线：通过 `.format.fill/line` API 直接设置 → **LLM 友好**
- 图表区/绘图区背景：需 lxml，简单且固定（2-3 行代码）→ **封装为工具函数即可**
- 数据标签/图例颜色：仅字体样式可设 → 足够

---

## 四、表格

### 4.1 表格颜色能力清单

| 表格元素 | 实现方式 | 复杂度 |
|----------|---------|--------|
| 单元格文字色 | `cell.text_frame.paragraphs[0].runs[0].font.color.rgb` | 低 |
| 单元格文字字体/大小 | `cell.text_frame...font.name/size` | 低 |
| 单元格填充色 | `cell.fill.solid()` + `cell.fill.fore_color.rgb` | 低 |
| 单元格边框色 | **lxml**：操作 `<a:tcPr>` 下的 `<a:lnL>`, `<a:lnR>`, `<a:lnT>`, `<a:lnB>` | 中 |
| 单元格边框宽度 | lxml | 中 |
| 标题行整行样式 | 循环设置每个 cell | 低 |
| 斑马条纹 | 循环 + 条件设置填充色 | 低 |

#### 单元格边框示例（lxml）

```python
from pptx.oxml.xmlchemy import OxmlElement

def set_cell_border(cell, color="333333", width="12700"):
    """给单元格设置四边边框。width EMU，12700=1pt"""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for border_tag in ['a:lnL', 'a:lnR', 'a:lnT', 'a:lnB']:
        ln = OxmlElement(border_tag)
        ln.set('w', width)
        solidFill = OxmlElement('a:solidFill')
        srgbClr = OxmlElement('a:srgbClr')
        srgbClr.set('val', color)
        solidFill.append(srgbClr)
        ln.append(solidFill)
        tcPr.append(ln)

# 使用
cell = table.cell(0, 0)
cell.text = "表头"
cell.fill.solid()
cell.fill.fore_color.rgb = RGBColor(0x1a, 0x73, 0xe8)
set_cell_border(cell, color="FFFFFF", width="6350")  # 0.5pt 白边
```

### 4.2 结论：表格颜色完全可控

边框需要 lxml，但模式固定，封装 1 个工具函数即可。LLM 只需指定颜色值。

---

## 五、字体与文字效果

### 5.1 高层 API 支持的属性

```python
from pptx.util import Pt
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.enum.text import MSO_TEXT_UNDERLINE_TYPE

run = paragraph.add_run()
run.text = "Hello"
font = run.font

# ─── 以下属性均有高层 API ───
font.name = '微软雅黑'                              # 字体名称
font.size = Pt(18)                                 # 字号
font.bold = True                                   # 粗体
font.italic = False                                # 斜体
font.color.rgb = RGBColor(0x1a, 0x73, 0xe8)       # RGB 颜色
font.color.theme_color = MSO_THEME_COLOR.ACCENT_1  # 主题色

# 下划线（支持多种样式）
font.underline = True                               # 单下划线
font.underline = MSO_TEXT_UNDERLINE_TYPE.DOUBLE     # 双下划线
font.underline = MSO_TEXT_UNDERLINE_TYPE.WAVY       # 波浪下划线
font.underline = MSO_TEXT_UNDERLINE_TYPE.NONE       # 无下划线
```

`MSO_TEXT_UNDERLINE_TYPE` 枚举值：

| 值 | 效果 |
|---|------|
| SINGLE | 单下划线 |
| DOUBLE | 双下划线 |
| HEAVY | 粗下划线 |
| DOTTED | 点线下划线 |
| DASH | 虚线下划线 |
| WAVY | 波浪下划线 |
| WAVY_DOUBLE | 双波浪 |
| WAVY_HEAVY | 粗波浪 |
| NONE | 无 |

### 5.2 阴影

**`ShadowFormat` 已实现但极其简陋**。该功能自 [2014 年 Issue #130](https://github.com/scanny/python-pptx/issues/130) 提出至今仍只有粗粒度开关。

```python
from pptx.dml.effect import ShadowFormat

# 形状阴影（仅此一个属性可用）
shadow = shape.shadow          # 返回 ShadowFormat 实例
shadow.inherit = True          # 继承主题阴影（默认），删除所有显示的 effectLst
shadow.inherit = False         # 关闭阴影 + 断开继承链

# 文字阴影：ShadowFormat 不直接暴露在 run.font 上
# 需通过 run._r.rPr 手动添加 <a:effectLst> → <a:outerShdw>
```

**ShadowFormat 只有一个属性 `inherit`**：

| 操作 | 效果 |
|------|------|
| `shadow.inherit = True` | 移除 `effectLst`，恢复继承（可能显示主题阴影） |
| `shadow.inherit = False` | 创建空 `effectLst`，断开继承（**不自动添加阴影内容**） |

⚠️ **关键限制**：
- **无法设置阴影颜色**、偏移量（`sx`/`sy`）、模糊度（`blurRad`）、透明度（`alpha`）
- `inherit = False` 不等于"关闭阴影"，它只是断开继承链 + 创建空 effectLst
- 实际添加/自定义阴影需通过 lxml 构造 `<a:outerShdw>` / `<a:innerShdw>` 元素

**lxml 手动添加文字阴影示例**：

```python
from lxml import etree
from pptx.oxml.ns import qn

def add_text_shadow(run, blur=40000, dist=20000, angle=0, color="000000", alpha=50000):
    """给 run 添加外阴影"""
    rPr = run._r.get_or_add_rPr()
    effectLst = etree.SubElement(rPr, qn('a:effectLst'))
    outerShdw = etree.SubElement(effectLst, qn('a:outerShdw'))
    outerShdw.set('blurRad', str(blur))   # EMU, 40000 ≈ 3pt
    outerShdw.set('dist', str(dist))      # EMU, 20000 ≈ 1.5pt
    outerShdw.set('dir', str(angle * 60000))  # 角度×60000

    # 阴影颜色
    srgbClr = etree.SubElement(outerShdw, qn('a:srgbClr'))
    srgbClr.set('val', color)
    alpha_el = etree.SubElement(srgbClr, qn('a:alpha'))
    alpha_el.set('val', str(alpha))       # 0-100000, 50000=50% 透明度
```

⚠️ **注意**：为 run 设置阴影后，对应的 `defRPr`（段落默认 run 属性）可能需要单独处理。这是 OOXML 规范的限制，不是 python-pptx 的 bug。

### 5.3 不支持的文字效果（需 lxml）

| 效果 | 高层 API | 替代方案 |
|------|---------|---------|
| **删除线** (strikethrough) | ❌ 无 | lxml: `<a:rPr strike="sngStrike">` |
| **双删除线** | ❌ 无 | lxml: `<a:rPr strike="dblStrike">` |
| **文字描边** (text outline) | ❌ 无 | lxml: `<a:rPr>` → `<a:ln>` |
| **发光** (glow) | ❌ 无 | lxml: `<a:effectLst>` → `<a:glow>` |
| **倒影** (reflection) | ❌ 无 | lxml: `<a:effectLst>` → `<a:reflection>` |
| **小型大写** (small caps) | ❌ 无 | lxml: `<a:rPr cap="small">` |
| **全部大写** (all caps) | ❌ 无 | lxml: `<a:rPr cap="all">` |
| **字距调整** (kerning) | ❌ 无 | lxml: `<a:rPr kern="1200">` |
| **浮雕** (emboss) | ❌ 无 | lxml: 未确认 |
| **阴文** (engrave) | ❌ 无 | lxml: 未确认 |
| **高亮色** (highlight) | ❌ 无 | lxml: `<a:rPr highlight="yellow">` |
| **阴影详细参数** | ❌ 无 | lxml: `<a:outerShdw>` / `<a:innerShdw>` |

### 5.4 字体效果实现策略

**分层方案**：

```
第一层（API 直达，LLM 高频使用）：
  bold, italic, underline(含样式), size, name, color

第二层（封装 lxml 工具函数，LLM 可选使用）：
  strikethrough, shadow_detail, text_glow, small_caps

第三层（暂不实现，后续按需）：
  reflection, emboss, engrave, kerning
```

第一层覆盖 90% 的 PPT 文字效果需求。第二层封装 3-5 个工具函数给 Agent 调用。

---

## 六、Shape API

### 6.1 Shape 类型总览

`MSO_SHAPE` 枚举共 **182 种形状**，分为以下类别：

| 类别 | 数量 | 代表形状 |
|------|------|---------|
| 基础几何 | ~55 | RECTANGLE, ROUNDED_RECTANGLE, OVAL, DIAMOND, TRIANGLE, PENTAGON, STAR_5_POINT, HEART, MOON, LIGHTNING_BOLT, SUN, GEAR_6, GEAR_9, DONUT, CUBE, CROSS, ARC, CHORD, PIE, TEAR, WAVE, FRAME, FUNNEL |
| 块箭头 | ~20 | RIGHT_ARROW, LEFT_ARROW, UP_ARROW, DOWN_ARROW, CIRCULAR_ARROW, BENT_ARROW, QUAD_ARROW, U_TURN_ARROW, NOTCHED_RIGHT_ARROW, SWOOSH_ARROW |
| 标注 | ~30 | RECTANGULAR_CALLOUT, ROUNDED_RECTANGULAR_CALLOUT, OVAL_CALLOUT, CLOUD_CALLOUT, LINE_CALLOUT_1~4 系列 |
| 流程图 | 28 | FLOWCHART_PROCESS, FLOWCHART_DECISION, FLOWCHART_DATA, FLOWCHART_DOCUMENT, FLOWCHART_TERMINATOR 等 |
| 带状横幅 | 5 | UP_RIBBON, DOWN_RIBBON, CURVED_UP_RIBBON, CURVED_DOWN_RIBBON, LEFT_RIGHT_RIBBON |
| 数学符号 | 6 | MATH_PLUS, MATH_MINUS, MATH_MULTIPLY, MATH_DIVIDE, MATH_EQUAL, MATH_NOT_EQUAL |
| 动作按钮 | 12 | ACTION_BUTTON_HOME, ACTION_BUTTON_HELP, ACTION_BUTTON_BACK_OR_PREVIOUS 等 |
| 圆角矩形变体 | 10 | ROUND_1_RECTANGLE, ROUND_2_DIAG_RECTANGLE, SNIP_1_RECTANGLE, SNIP_ROUND_RECTANGLE, FOLDED_CORNER 等 |
| 其他 | ~16 | BRACE 系列, BRACKET 系列, EXPLOSION1/2, CHEVRON, SMILEY_FACE, BEVEL, CAN, CLOUD, SCROLL 系列 |

**对 Agent 的影响**：将 182 种 shape 按语义分组映射到 JSON schema 的 `shape_type` 字段。LLM 只需选择语义名（如 `"rounded_rectangle"`、`"star_5"`、`"right_arrow"`），parser 做映射。

### 6.2 Shape 创建与基本属性

```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_THEME_COLOR

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[6])

# 创建形状
shape = slide.shapes.add_shape(
    MSO_SHAPE.ROUNDED_RECTANGLE,
    Inches(1), Inches(1), Inches(8), Inches(5)
)

# 位置/尺寸（读写，EMU 单位）
shape.left = Inches(2)
shape.top = Inches(1.5)
shape.width = Inches(6)
shape.height = Inches(3)

# 旋转（度，逆时针为正）
shape.rotation = 45.0

# 调节柄（0-4 个，值域 0~100000）
shape.adjustments[0] = 0.5   # 第 1 个调节柄置中

# 名称
shape.name = "My Shape"
```

### 6.3 形状纯色填充

```python
# RGB 颜色
shape.fill.solid()
shape.fill.fore_color.rgb = RGBColor(0x1a, 0x73, 0xe8)

# 主题色
shape.fill.fore_color.theme_color = MSO_THEME_COLOR.ACCENT_1
shape.fill.fore_color.brightness = 0.25   # 25% 更亮

# 透明（无填充）
shape.fill.background()
```

### 6.4 形状线条（描边）

```python
line = shape.line

# 颜色
line.color.rgb = RGBColor(0x33, 0x33, 0x33)
line.color.theme_color = MSO_THEME_COLOR.DARK_1

# 宽度
line.width = Pt(2.0)

# 虚线样式
from pptx.enum.dml import MSO_LINE_DASH_STYLE
line.dash_style = MSO_LINE_DASH_STYLE.DASH

# 无线条
line.fill.background()
```

### 6.5 形状渐变填充

**支持程度**：

| 渐变属性 | 高层 API | 说明 |
|----------|---------|------|
| 线性渐变 | ✅ `fill.gradient()` | 默认 2-stop，主题色 Accent-1 |
| 渐变角度 | ✅ `fill.gradient_angle` | 0°=左→右, 90°=下→上 |
| 渐变 stop 颜色 | ✅ `stops[i].color.rgb` | 修改现有 stop |
| 渐变 stop 位置 | ❌ | 需 lxml 设 `pos` 属性 |
| 添加第 3+ stop | ❌ | 需 `parse_xml` + `append` |
| 径向渐变 | ❌ | 默认只能是线性，径向需 lxml |

```python
# 基本渐变（2 个 stop）
shape.fill.gradient()
shape.fill.gradient_angle = 0.0    # 左→右

# 修改 stop 颜色
stops = shape.fill.gradient_stops
stops[0].color.rgb = RGBColor(0x1a, 0x73, 0xe8)  # 左侧蓝色
stops[1].color.rgb = RGBColor(0x34, 0xa8, 0x53)  # 右侧绿色

# 添加第 3 个 stop（lxml）
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls
new_gs = parse_xml(
    '<a:gs pos="50000" %s>\n'          # pos=50% (单位: 千分之一)
    '  <a:srgbClr val="FF0000"/>\n'
    '</a:gs>' % nsdecls("a")
)
fill.gradient_stops._gsLst.insert(2, new_gs)   # 保持位置升序
```

### 6.6 形状图片填充

**无高层 API**。需通过 lxml 构造 `<a:blipFill>` 元素：

```python
from lxml import etree
from pptx.oxml.ns import qn

def set_shape_picture_fill(shape, image_path, fill_mode="stretch"):
    """给形状设置图片填充"""
    # 添加图片关系到 slide part
    rId = shape.part.relate_to(
        image_path,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
    )

    spPr = shape._element.spPr
    # 删除现有填充
    for child in list(spPr):
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag in ('solidFill', 'gradFill', 'pattFill', 'noFill'):
            spPr.remove(child)

    fill_mode_xml = '<a:stretch><a:fillRect/></a:stretch>' if fill_mode == "stretch" else '<a:tile/>'
    blipFill = etree.fromstring(f'''<a:blipFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        <a:blip r:embed="{rId}"/>
        {fill_mode_xml}
    </a:blipFill>''')
    spPr.append(blipFill)
```

### 6.7 形状文字

```python
# 方式 1：简写（清空后设文字）
shape.text = "Hello"

# 方式 2：完整控制
tf = shape.text_frame
tf.word_wrap = True
tf.vertical_anchor = MSO_ANCHOR.MIDDLE   # 垂直居中

p = tf.paragraphs[0]
p.alignment = PP_ALIGN.CENTER
run = p.add_run()
run.text = "标题文字"
run.font.size = Pt(18)
run.font.bold = True
run.font.color.rgb = RGBColor(0x1a, 0x73, 0xe8)
```

---

## 七、幻灯片背景

### 7.1 纯色背景

```python
slide = prs.slides.add_slide(prs.slide_layouts[6])

bg = slide.background
bg.fill.solid()
bg.fill.fore_color.rgb = RGBColor(0x1a, 0x73, 0xe8)

# 也可以使用主题色
bg.fill.fore_color.theme_color = MSO_THEME_COLOR.DARK_2
bg.fill.fore_color.brightness = 0.8
```

### 7.2 渐变背景

```python
bg = slide.background
bg.fill.gradient()
bg.fill.gradient_angle = 135.0           # 左上→右下

stops = bg.fill.gradient_stops
stops[0].color.rgb = RGBColor(0x1a, 0x73, 0xe8)
stops[1].color.rgb = RGBColor(0x34, 0xa8, 0x53)
```

### 7.3 图案背景

```python
bg.fill.patterned()
bg.fill.pattern = MSO_PATTERN_TYPE.DIAGONAL_BRICK
bg.fill.fore_color.rgb = RGBColor(0x33, 0x33, 0x33)
bg.fill.back_color.rgb = RGBColor(0xf5, 0xf5, 0xf5)
```

### 7.4 图片背景

**无高层 API**。两条路径：

**路径 1（推荐）**：在 slide 上加一个铺满全页的 Picture shape：

```python
slide.shapes.add_picture(
    "bg.jpg",
    Inches(0), Inches(0),
    width=prs.slide_width,
    height=prs.slide_height
)
```

**路径 2**：lxml 操作 `p:bgPr`，实现真正的 slide background（PPT 本身支持的背景属性）：

```python
from lxml import etree

bg = slide.background._element
bgPr = bg.find(qn('p:bgPr'))
bgPr.clear()

rId = slide.part.relate_to("bg.jpg", ".../image")
blipFill = etree.fromstring(f'''<p:blipFill xmlns:a="..." xmlns:r="...">
    <a:blip r:embed="{rId}"/><a:stretch><a:fillRect/></a:stretch>
</p:blipFill>''')
bgPr.append(blipFill)
```

### 7.5 背景能力总结

| 背景类型 | 高层 API | 推荐度 |
|----------|---------|--------|
| 纯色 | ✅ 完全支持 | ⭐⭐⭐ |
| 渐变(线性) | ✅ 支持 | ⭐⭐⭐ |
| 渐变(径向) | ❌ 需 lxml | ⭐ |
| 图案 | ✅ 支持 | ⭐⭐ |
| 图片 | ❌ 需 lxml 或全幅 Picture | ⭐⭐（用全幅 Picture 变通） |
| 透明(从母版继承) | ✅ `fill.background()` | ⭐⭐⭐ |

---

## 八、Template JSON 存储方案

### 8.1 设计思路

不使用 .pptx 模板文件。将 layout 定义、配色方案、元素布局全部存为 JSON 文件，放在 `resources/templates/` 下。Agent 按需读取、组合。

### 8.2 文件结构

```
resources/templates/
├── color_schemes/
│   ├── business_blue.json
│   ├── academic_warm.json
│   ├── minimal_dark.json
│   └── creative_vivid.json
├── layouts/
│   ├── title_slide.json
│   ├── content_bullet.json
│   ├── content_chart.json
│   ├── content_table.json
│   ├── two_column.json
│   ├── image_text.json
│   └── ending.json
└── index.json                          # 模板元信息
```

### 8.3 配色方案 JSON (color_schemes/business_blue.json)

```json
{
  "name": "business_blue",
  "label": "商务蓝",
  "colors": {
    "primary":    "#1a73e8",
    "primary_dark": "#1557b0",
    "primary_light": "#d2e3fc",
    "accent":     "#ea4335",
    "accent2":    "#34a853",
    "accent3":    "#fbbc04",
    "text":       "#202124",
    "text_secondary": "#5f6368",
    "bg":         "#ffffff",
    "bg_dark":    "#f8f9fa",
    "border":     "#dadce0"
  },
  "chart_colors": ["#1a73e8", "#ea4335", "#34a853", "#fbbc04", "#ab47bc", "#26c6da"],
  "fonts": {
    "title": { "name": "微软雅黑", "size": 32, "bold": true },
    "subtitle": { "name": "微软雅黑", "size": 18, "bold": false },
    "body": { "name": "微软雅黑", "size": 14, "bold": false },
    "caption": { "name": "微软雅黑", "size": 10, "bold": false, "italic": true }
  }
}
```

### 8.4 Layout 定义 JSON (layouts/content_bullet.json)

```json
{
  "name": "content_bullet",
  "label": "标题 + 要点列表",
  "placeholders": [
    {
      "id": "title",
      "type": "textbox",
      "position": { "left": 0.8, "top": 0.4, "width": 11.7, "height": 1.0 },
      "style": "title"
    },
    {
      "id": "body",
      "type": "textbox",
      "position": { "left": 1.2, "top": 1.8, "width": 10.9, "height": 5.0 },
      "style": "body",
      "default_content": [
        { "paragraph": { "level": 0, "runs": [{ "text": "要点 1" }] } },
        { "paragraph": { "level": 1, "runs": [{ "text": "子要点" }] } }
      ]
    },
    {
      "id": "page_number",
      "type": "textbox",
      "position": { "left": 11.8, "top": 6.9, "width": 1.0, "height": 0.4 },
      "style": "caption",
      "text": "{page_num} / {total_pages}"
    }
  ]
}
```

### 8.5 Layout 定义 JSON (layouts/content_chart.json)

```json
{
  "name": "content_chart",
  "label": "图表 + 图注",
  "placeholders": [
    {
      "id": "title",
      "type": "textbox",
      "position": { "left": 0.8, "top": 0.4, "width": 11.7, "height": 0.9 },
      "style": "title"
    },
    {
      "id": "chart",
      "type": "chart",
      "position": { "left": 0.8, "top": 1.6, "width": 8.5, "height": 5.0 },
      "style": "default"
    },
    {
      "id": "chart_notes",
      "type": "textbox",
      "position": { "left": 9.8, "top": 1.6, "width": 3.0, "height": 5.0 },
      "style": "body"
    }
  ]
}
```

### 8.6 index.json（模板索引）

```json
{
  "schema": "ppt_templates_v1",
  "color_schemes": [
    { "name": "business_blue", "label": "商务蓝", "themes": ["corporate", "tech", "finance"] },
    { "name": "academic_warm", "label": "学术暖色", "themes": ["education", "research"] },
    { "name": "minimal_dark", "label": "极简暗色", "themes": ["startup", "design"] },
    { "name": "creative_vivid", "label": "创意亮色", "themes": ["marketing", "creative"] }
  ],
  "layouts": [
    { "name": "title_slide", "label": "封面", "slots": 2 },
    { "name": "content_bullet", "label": "要点列表", "slots": 3 },
    { "name": "content_chart", "label": "图表页", "slots": 3 },
    { "name": "content_table", "label": "表格页", "slots": 2 },
    { "name": "two_column", "label": "双栏", "slots": 3 },
    { "name": "image_text", "label": "图文混排", "slots": 3 },
    { "name": "ending", "label": "结束页", "slots": 2 }
  ]
}
```

### 8.7 工作流

```
layout_agent:
  1. 读 resources/templates/index.json → 获取可用配色/layout
  2. 根据大纲内容选择 color_scheme + 每页 layout
  3. 输出: { "color_scheme": "business_blue", "slides": [{ "layout": "content_chart", ... }] }

supervisor:
  4. 合并 sub-agent 产出的 element JSON 到对应 page
  5. 注入 color_scheme 的字体/颜色到 element style 中

SlideBuilder:
  6. 读取 PPTInstruction JSON → 渲染
```

这样 layout_agent 不再需要"发明"布局，而是从 JSON 池中**选择**，输出的坐标和尺寸有明确的来源（JSON 文件），可预测、可调试。

---

## 九、数据库变更建议

### 9.1 设计原则

```
每个 Sub-Agent 独立产出 → 独立 checkpoint
  text_agent  → presentation_slides.agent_outputs["text"]
  chart_agent → presentation_slides.agent_outputs["chart"]
  table_agent → presentation_slides.agent_outputs["table"]
  image_agent → presentation_slides.agent_outputs["image"]
  layout_agent → presentation.template_id + presentation.color_scheme_id

单 agent 失败 ≠ 全部重做
  supervisor 检查 agent_outputs → 只重试失败的 agent
```

### 9.2 ER 图（新增部分）

```
┌───────────────────┐       ┌──────────────────────┐
│   presentations   │       │    color_schemes     │
│───────────────────│       │──────────────────────│
│ PK id             │   ┌──│ PK id                 │
│ FK conversation   │   │  │    name (unique)      │
│ FK outline        │   │  │    label              │
│ FK user           │   │  │    colors_json (JSON) │
│ FK template       │───┘  │    chart_colors_json  │
│ FK color_scheme   │──────│    fonts_json (JSON)  │
│    status         │      │    is_active          │
│    file_path      │      └──────────────────────┘
│    file_size      │
│    slide_count    │      ┌──────────────────────┐
└────────┬──────────┘      │      templates       │
         │                 │──────────────────────│
         │ 1:N             │ PK id                 │
         │                 │    name (unique)      │
┌────────▼──────────┐      │    label              │
│presentation_slides│      │    category           │
│──────────────────│      │    slide_width        │
│ PK id            │      │    slide_height       │
│ FK presentation  │      │    layouts_json (JSON)│
│ FK outline_slide │      │    is_active          │
│ FK template      │──────┘
│ FK color_scheme  │──┐
│    slide_index   │  │
│    layout_name   │  │
│    status        │  │
│    agent_outputs │  │  ┌───────────────┐
│    chart_data    │  │  │    agents     │ (可选：记录 agent 调用)
│    table_data    │  │  │───────────────│
│    image_paths   │  │  │ PK id         │
│    error_message │  │  │    slide_id   │
│    retry_count   │  │  │    agent_type │
└──────────────────┘  │  │    input_json │
                       │  │    output_json│
                       │  │    llm_model  │
                       │  │    tokens     │
                       │  │    duration_ms│
                       │  │    status     │
                       │  └───────────────┘
                       │
                       └── color_schemes (同上 FK)
```

### 9.3 新增表：templates

```sql
CREATE TABLE templates (
    id            INTEGER PRIMARY KEY AUTO_INCREMENT,
    name          VARCHAR(50)  NOT NULL UNIQUE COMMENT '模板标识, e.g. business_blue',
    label         VARCHAR(100) NOT NULL COMMENT '显示名, e.g. 商务蓝',
    category      VARCHAR(50)  COMMENT '分类: corporate|tech|education|creative|minimal',
    description   VARCHAR(500) COMMENT '模板描述',
    slide_width   FLOAT        NOT NULL DEFAULT 13.333 COMMENT '幻灯片宽度 (英寸), 16:9=13.333',
    slide_height  FLOAT        NOT NULL DEFAULT 7.5   COMMENT '幻灯片高度 (英寸)',
    layouts_json  JSON         NOT NULL COMMENT '布局定义数组 [{name, label, placeholders}]',
    is_active     BOOLEAN      DEFAULT TRUE,
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

| 字段 | 说明 |
|------|------|
| `layouts_json` | 该模板包含的所有 layout 定义，每个 layout 含 `name`/`label`/`placeholders[]`，格式同 `resources/templates/layouts/` 下的 JSON |

示例数据：
```json
{
  "layouts_json": [
    {
      "name": "title_slide",
      "label": "封面",
      "placeholders": [
        {"id": "title", "type": "textbox", "position": {"left": 1.0, "top": 2.5, "width": 11.3, "height": 1.2}, "style": "title"},
        {"id": "subtitle", "type": "textbox", "position": {"left": 1.0, "top": 4.0, "width": 11.3, "height": 0.8}, "style": "subtitle"}
      ]
    },
    { "name": "content_bullet", "label": "要点列表", "placeholders": [...] }
  ]
}
```

### 9.4 新增表：color_schemes

```sql
CREATE TABLE color_schemes (
    id                INTEGER PRIMARY KEY AUTO_INCREMENT,
    name              VARCHAR(50)  NOT NULL UNIQUE COMMENT '方案标识, e.g. business_blue',
    label             VARCHAR(100) NOT NULL COMMENT '显示名, e.g. 商务蓝',
    colors_json       JSON         NOT NULL COMMENT '颜色定义 {primary, accent, text, bg, ...}',
    chart_colors_json JSON         NOT NULL COMMENT '图表配色序列 ["#1a73e8", "#ea4335", ...]',
    fonts_json        JSON         NOT NULL COMMENT '字体定义 {title, subtitle, body, caption}',
    is_active         BOOLEAN      DEFAULT TRUE,
    created_at        DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

`colors_json` 结构：
```json
{
  "primary": "#1a73e8", "primary_dark": "#1557b0", "primary_light": "#d2e3fc",
  "accent": "#ea4335", "accent2": "#34a853", "accent3": "#fbbc04",
  "text": "#202124", "text_secondary": "#5f6368",
  "bg": "#ffffff", "bg_dark": "#f8f9fa",
  "border": "#dadce0"
}
```

`fonts_json` 结构：
```json
{
  "title":    { "name": "微软雅黑", "size": 32, "bold": true },
  "subtitle": { "name": "微软雅黑", "size": 18 },
  "body":     { "name": "微软雅黑", "size": 14 },
  "caption":  { "name": "微软雅黑", "size": 10, "italic": true }
}
```

### 9.5 变更：presentations 表

```sql
ALTER TABLE presentations
    ADD COLUMN template_id     INTEGER     COMMENT 'FK → templates.id',
    ADD COLUMN color_scheme_id INTEGER     COMMENT 'FK → color_schemes.id',
    ADD COLUMN slide_count     INTEGER     DEFAULT 0,
    ADD COLUMN file_size       INTEGER     COMMENT 'bytes',
    ADD FOREIGN KEY (template_id)     REFERENCES templates(id)     ON DELETE SET NULL,
    ADD FOREIGN KEY (color_scheme_id) REFERENCES color_schemes(id) ON DELETE SET NULL;
```

| 字段 | 理由 |
|------|------|
| `template_id` | FK 引用 `templates` 表，替代 JSON 文件中存储。可 JOIN 出完整模板信息 |
| `color_scheme_id` | FK 引用 `color_schemes` 表，同上 |
| `slide_count` / `file_size` | 便利字段 |

### 9.6 变更：presentation_slides 表（保留并增强）

```sql
CREATE TABLE presentation_slides (
    id                INTEGER PRIMARY KEY AUTO_INCREMENT,
    presentation_id   INTEGER       NOT NULL,
    outline_slide_id  INTEGER       COMMENT 'FK → outline_slides.id, 对应的大纲页',
    slide_index       INTEGER       NOT NULL COMMENT '页码 0-based',

    -- 模板引用
    template_id       INTEGER       COMMENT '本页使用的模板 FK → templates.id（可覆盖 presentation 级）',
    color_scheme_id   INTEGER       COMMENT '本页配色 FK → color_schemes.id（可覆盖 presentation 级）',
    layout_name       VARCHAR(50)   NOT NULL COMMENT 'layout 名, e.g. content_chart',

    -- 各 agent 产出的 element JSON，独立 checkpoint
    agent_outputs     JSON          COMMENT '{
        "text":  [...],   -- text_agent 产出
        "chart": {...},   -- chart_agent 产出
        "table": {...},   -- table_agent 产出
        "image": {...},   -- image_agent 产出
        "layout": {...}   -- layout_agent 产出（本页 color_scheme 覆盖等）
    }',

    -- 图表/表格的独立存储（方便 Agent 重试和前端展示）
    chart_data         JSON          COMMENT 'chart_agent 最终产出的图表数据 {chart_type, categories, series, style}',
    table_data         JSON          COMMENT 'table_agent 最终产出的表格数据 {rows, cols, cells, merges, style}',
    image_paths        JSON          COMMENT 'image_agent 产出的图片路径列表 ["/path/img1.png", ...]',

    -- 生成状态
    status             VARCHAR(20)   DEFAULT 'pending'
                       COMMENT 'pending|text_generating|chart_generating|table_generating|image_generating|completed|failed',
    error_message      TEXT          COMMENT '失败时的错误信息',
    retry_count        INTEGER       DEFAULT 0,

    created_at         DATETIME      DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (presentation_id)  REFERENCES presentations(id)  ON DELETE CASCADE,
    FOREIGN KEY (outline_slide_id) REFERENCES outline_slides(id) ON DELETE SET NULL,
    FOREIGN KEY (template_id)      REFERENCES templates(id)      ON DELETE SET NULL,
    FOREIGN KEY (color_scheme_id)  REFERENCES color_schemes(id)  ON DELETE SET NULL
);
```

**设计要点**：

| 字段 | 设计意图 |
|------|---------|
| `agent_outputs` | 每个 sub-agent 独立写入自己产出的 element JSON。supervisor 在重试时检查哪些 agent 已完成，**只重试失败的** |
| `chart_data` / `table_data` | LLM 产出的结构化数据。和 `agent_outputs` 冗余但语义不同——`agent_outputs` 是 element JSON（含 position/styling），而 `chart_data` 是纯数据（供 Agent 读取和修改） |
| `status` 细粒度 | `pending` → `text_done` → `chart_done` → `table_done` → `image_done` → `completed`。任何步骤失败置为 `failed` |
| `error_message` + `retry_count` | 记录失败原因，支持有限重试（如最多 3 次） |
| `outline_slide_id` | 关联大纲页，实现 `outline_slide → presentation_slide` 的 1:1 映射 |
| 页级 `template_id` / `color_scheme_id` | 允许单页覆盖 presentation 级别的模板/配色选择 |

### 9.7 可选：agent_calls 表

用于记录每个 sub-agent 的 LLM 调用详情（调试 + 成本追踪）：

```sql
CREATE TABLE agent_calls (
    id            INTEGER PRIMARY KEY AUTO_INCREMENT,
    slide_id      INTEGER       NOT NULL COMMENT 'FK → presentation_slides.id',
    agent_type    VARCHAR(20)   NOT NULL COMMENT 'text|chart|table|image|layout',
    input_json    JSON          COMMENT '传给 agent 的 prompt + context',
    output_json   JSON          COMMENT 'agent 产出的原始 JSON',
    llm_model     VARCHAR(50)   COMMENT '使用的 LLM 模型',
    tokens_in     INTEGER       DEFAULT 0,
    tokens_out    INTEGER       DEFAULT 0,
    duration_ms   INTEGER       COMMENT '调用耗时',
    status        VARCHAR(20)   DEFAULT 'pending' COMMENT 'pending|success|failed',
    error_message TEXT,
    created_at    DATETIME      DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (slide_id) REFERENCES presentation_slides(id) ON DELETE CASCADE
);
```

此表**可选**，如果不需要细粒度追踪可暂不建。`agent_outputs` 字段已经提供了 checkpoint 能力。

### 9.8 Agent 生成流程中的 checkpoint 行为

```
supervisor 为第 k 页调度 sub-agent：

1. text_agent 产出 → presentation_slides[k].agent_outputs["text"] = [...]
   状态: text_done

2. chart_agent 产出 → presentation_slides[k].agent_outputs["chart"] = {...}
                      presentation_slides[k].chart_data = {...}
   状态: chart_done

3. table_agent 产出 → presentation_slides[k].agent_outputs["table"] = {...}
                      presentation_slides[k].table_data = {...}
   状态: table_done

4. image_agent 产出 → presentation_slides[k].agent_outputs["image"] = {...}
                      presentation_slides[k].image_paths = [...]
   状态: completed

如果第 3 步 table_agent 失败：
   状态: failed  (charts_done)
   error_message = "LLM timeout after 30s"
   retry_count = 1
   → supervisor 只重试 table_agent，text 和 chart 的产出保留
```

### 9.9 完整 DDL

```sql
-- 新增表
CREATE TABLE templates (
    id            INTEGER PRIMARY KEY AUTO_INCREMENT,
    name          VARCHAR(50)  NOT NULL UNIQUE,
    label         VARCHAR(100) NOT NULL,
    category      VARCHAR(50),
    description   VARCHAR(500),
    slide_width   FLOAT        NOT NULL DEFAULT 13.333,
    slide_height  FLOAT        NOT NULL DEFAULT 7.5,
    layouts_json  JSON         NOT NULL,
    is_active     BOOLEAN      DEFAULT TRUE,
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE color_schemes (
    id                INTEGER PRIMARY KEY AUTO_INCREMENT,
    name              VARCHAR(50)  NOT NULL UNIQUE,
    label             VARCHAR(100) NOT NULL,
    colors_json       JSON         NOT NULL,
    chart_colors_json JSON         NOT NULL,
    fonts_json        JSON         NOT NULL,
    is_active         BOOLEAN      DEFAULT TRUE,
    created_at        DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- presentations 表变更
ALTER TABLE presentations
    ADD COLUMN template_id     INTEGER,
    ADD COLUMN color_scheme_id INTEGER,
    ADD COLUMN slide_count     INTEGER DEFAULT 0,
    ADD COLUMN file_size       INTEGER,
    ADD FOREIGN KEY (template_id)     REFERENCES templates(id)     ON DELETE SET NULL,
    ADD FOREIGN KEY (color_scheme_id) REFERENCES color_schemes(id) ON DELETE SET NULL;

-- presentation_slides 表：重建
DROP TABLE IF EXISTS presentation_slides;   -- 旧表结构废弃
CREATE TABLE presentation_slides (
    id                INTEGER PRIMARY KEY AUTO_INCREMENT,
    presentation_id   INTEGER       NOT NULL,
    outline_slide_id  INTEGER,
    slide_index       INTEGER       NOT NULL,
    template_id       INTEGER,
    color_scheme_id   INTEGER,
    layout_name       VARCHAR(50)   NOT NULL,
    agent_outputs     JSON,
    chart_data        JSON,
    table_data        JSON,
    image_paths       JSON,
    status            VARCHAR(20)   DEFAULT 'pending',
    error_message     TEXT,
    retry_count       INTEGER       DEFAULT 0,
    created_at        DATETIME      DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (presentation_id)  REFERENCES presentations(id)  ON DELETE CASCADE,
    FOREIGN KEY (outline_slide_id) REFERENCES outline_slides(id) ON DELETE SET NULL,
    FOREIGN KEY (template_id)      REFERENCES templates(id)      ON DELETE SET NULL,
    FOREIGN KEY (color_scheme_id)  REFERENCES color_schemes(id)  ON DELETE SET NULL
);

-- 索引
CREATE INDEX idx_pslide_pres      ON presentation_slides(presentation_id, slide_index);
CREATE INDEX idx_pslide_status    ON presentation_slides(status);
CREATE INDEX idx_pslide_outline   ON presentation_slides(outline_slide_id);
CREATE INDEX idx_pres_conv_status ON presentations(conversation_id, status);
CREATE INDEX idx_template_cat     ON templates(category);
CREATE INDEX idx_colorscheme_name ON color_schemes(name);
```

### 9.10 ORM 模型

```python
# infrastructure/db/models.py

class Template(Base):
    __tablename__ = "templates"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    category = Column(String(50))
    description = Column(String(500))
    slide_width = Column(Float, default=13.333)
    slide_height = Column(Float, default=7.5)
    layouts_json = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class ColorScheme(Base):
    __tablename__ = "color_schemes"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    colors_json = Column(JSON, nullable=False)
    chart_colors_json = Column(JSON, nullable=False)
    fonts_json = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Presentation(Base):
    __tablename__ = "presentations"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    outline_id = Column(Integer, ForeignKey("outlines.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("templates.id"))
    color_scheme_id = Column(Integer, ForeignKey("color_schemes.id"))
    file_path = Column(String(500))
    file_size = Column(Integer)
    slide_count = Column(Integer, default=0)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class PresentationSlide(Base):
    __tablename__ = "presentation_slides"
    id = Column(Integer, primary_key=True)
    presentation_id = Column(Integer, ForeignKey("presentations.id"), nullable=False)
    outline_slide_id = Column(Integer, ForeignKey("outline_slides.id"))
    slide_index = Column(Integer, nullable=False)
    template_id = Column(Integer, ForeignKey("templates.id"))
    color_scheme_id = Column(Integer, ForeignKey("color_schemes.id"))
    layout_name = Column(String(50), nullable=False)
    agent_outputs = Column(JSON)       # {"text": [...], "chart": {...}, "table": {...}, "image": {...}}
    chart_data = Column(JSON)          # 图表纯数据
    table_data = Column(JSON)          # 表格纯数据
    image_paths = Column(JSON)         # 图片路径列表
    status = Column(String(20), default="pending")
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

### 9.11 数据初始化：JSON → 数据库

`resources/templates/` 下的 JSON 文件在首次部署时通过 seed 脚本导入：

```python
# infrastructure/db/seed.py

async def seed_templates_and_colors(engine):
    import json, glob

    async with engine.begin() as conn:
        # 导入配色方案
        for f in glob.glob("resources/templates/color_schemes/*.json"):
            data = json.load(open(f, encoding="utf-8"))
            await conn.execute(
                insert(ColorScheme).values(
                    name=data["name"], label=data["label"],
                    colors_json=data["colors"],
                    chart_colors_json=data["chart_colors"],
                    fonts_json=data["fonts"],
                )
            )

        # 导入模板
        layouts = {f: json.load(open(f, encoding="utf-8"))
                    for f in glob.glob("resources/templates/layouts/*.json")}
        await conn.execute(
            insert(Template).values(
                name="default", label="默认模板", category="general",
                layouts_json=list(layouts.values()),
            )
        )
```

---

## 十、Agent Tool 集成方案

---

## 十、Agent Tool 集成方案

### 10.1 问题分析

LangGraph Agent 的 LLM 只能输出 JSON/文本，无法直接调用 python-pptx API。需要一层 **指令解析器（Instruction Parser）** 将 LLM 输出的结构化指令翻译为 python-pptx 调用。

### 10.2 设计：三层指令模型

```
LLM 输出 JSON 指令
       │
       ▼
┌─────────────────────────────┐
│  InstructionParser          │  解析 + 校验 JSON schema
│  (ppt_engine/parser.py)     │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  SlideBuilder               │  执行指令，调用 python-pptx
│  (ppt_engine/generator.py)  │
└─────────────────────────────┘
```

### 10.3 指令 JSON Schema

```json
{
  "$schema": "ppt_instruction_v1",
  "meta": {
    "template": "business_blue",        // 模板名（可选）
    "slide_width": 13.333,              // 英寸（16:9）
    "slide_height": 7.5,
    "language": "zh"
  },
  "slides": [
    {
      "layout": "title",               // 模板 layout 名 或 "blank"
      "color_scheme": {                 // 本页配色覆盖
        "primary": "#1a73e8",
        "accent": "#ea4335",
        "text": "#333333",
        "bg": "#ffffff"
      },
      "elements": [
        // ... 元素列表，按 z-order 排列
      ]
    }
  ]
}
```

### 10.4 元素类型定义

#### 文本框 (textbox)
```json
{
  "type": "textbox",
  "position": { "left": 1.0, "top": 0.5, "width": 11.3, "height": 1.2 },
  "content": [
    {
      "paragraph": {
        "alignment": "left",             // left|center|right|justify
        "level": 0,
        "space_before": 6,               // pt, 可选
        "space_after": 4,
        "runs": [
          {
            "text": "季度营收分析",
            "font": {
              "name": "微软雅黑",
              "size": 32,
              "bold": true,
              "italic": false,
              "color": "#1a73e8",
              "underline": "none"        // none|single|double|wavy
            }
          }
        ]
      }
    }
  ]
}
```

#### 图表 (chart)
```json
{
  "type": "chart",
  "chart_type": "column_clustered",      // column_clustered|bar_clustered|line|pie|doughnut|area|scatter|radar
  "position": { "left": 1.0, "top": 1.8, "width": 8.0, "height": 5.0 },
  "data": {
    "categories": ["Q1", "Q2", "Q3", "Q4"],
    "series": [
      { "name": "营收", "values": [120, 145, 138, 162] },
      { "name": "成本", "values": [80, 92, 88, 95] }
    ]
  },
  "style": {
    "has_legend": true,
    "legend_position": "bottom",         // bottom|right|left|top
    "has_data_labels": true,
    "data_label_position": "outside_end",
    "series_colors": ["#1a73e8", "#ea4335"],  // 按系列顺序
    "chart_area_fill": "#fafafa",        // 可选，图表区背景
    "plot_area_fill": "none"             // 可选，绘图区背景
  }
}
```

#### 表格 (table)
```json
{
  "type": "table",
  "position": { "left": 1.0, "top": 1.5, "width": 11.0, "height": 4.5 },
  "rows": 5,
  "cols": 4,
  "col_widths": [2.0, 3.0, 3.0, 3.0],   // 英寸
  "header": {
    "row": 0,
    "fill": "#1a73e8",
    "font_color": "#ffffff",
    "font_bold": true,
    "font_size": 14
  },
  "cells": [
    { "row": 0, "col": 0, "text": "类别" },
    { "row": 0, "col": 1, "text": "Q1" },
    { "row": 0, "col": 2, "text": "Q2" },
    { "row": 0, "col": 3, "text": "Q3" },
    // ...
  ],
  "merges": [                              // 可选，合并单元格
    { "from": [0, 0], "to": [0, 1] }
  ],
  "style": {
    "border_color": "#e0e0e0",
    "border_width": 0.5,                  // pt
    "stripe_rows": { "even": "#f5f8fc", "odd": "#ffffff" }
  }
}
```

#### 图片 (picture)
```json
{
  "type": "picture",
  "path": "workspace/images/chart_1.png",  // 相对 workspace 路径
  "position": { "left": 1.0, "top": 1.5, "width": 6.0 },
  "fit": "aspect"                          // aspect|stretch|crop，仅设 width 时自动等比
}
```

#### 形状 (shape)
```json
{
  "type": "shape",
  "shape_type": "rounded_rectangle",       // rectangle|rounded_rectangle|oval|chevron|arrow|...
  "position": { "left": 1.0, "top": 0.5, "width": 11.0, "height": 0.8 },
  "fill": "#1a73e81a",                     // 含透明度
  "line": { "color": "#1a73e8", "width": 1.0 },
  "text": {
    "content": [{ "paragraph": { "alignment": "center", "runs": [{ "text": "标题栏", "font": { "size": 16, "color": "#1a73e8", "bold": true } }] } }]
  }
}
```

### 10.5 InstructionParser 实现骨架

```python
# infrastructure/ppt_engine/parser.py

from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
import json

# ─── Pydantic 模型（自动校验） ───

class FontSpec(BaseModel):
    name: Optional[str] = None           # e.g. "微软雅黑"
    size: Optional[int] = None           # pt
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    color: Optional[str] = None          # "#1a73e8"
    underline: Optional[str] = None      # "none"|"single"|"double"|"wavy"

class RunSpec(BaseModel):
    text: str
    font: Optional[FontSpec] = None

class ParagraphSpec(BaseModel):
    alignment: Optional[str] = "left"
    level: Optional[int] = 0
    space_before: Optional[int] = None
    space_after: Optional[int] = None
    runs: list[RunSpec] = []

class ContentBlock(BaseModel):
    paragraph: ParagraphSpec

class Position(BaseModel):
    left: float
    top: float
    width: float
    height: Optional[float] = None

class ChartSeries(BaseModel):
    name: str
    values: list[float]

class ChartDataSpec(BaseModel):
    categories: list[str]
    series: list[ChartSeries]

class ChartStyleSpec(BaseModel):
    has_legend: bool = True
    legend_position: str = "bottom"
    has_data_labels: bool = False
    data_label_position: Optional[str] = None
    series_colors: Optional[list[str]] = None
    chart_area_fill: Optional[str] = None
    plot_area_fill: Optional[str] = None

class CellSpec(BaseModel):
    row: int
    col: int
    text: str
    font: Optional[FontSpec] = None

class MergeSpec(BaseModel):
    from_: tuple[int, int]
    to: tuple[int, int]

class TableStyleSpec(BaseModel):
    border_color: Optional[str] = "#e0e0e0"
    border_width: Optional[float] = 0.5
    stripe_rows: Optional[dict] = None

class ElementSpec(BaseModel):
    type: Literal["textbox", "chart", "table", "picture", "shape"]
    position: Position
    # textbox
    content: Optional[list[ContentBlock]] = None
    # chart
    chart_type: Optional[str] = None
    data: Optional[ChartDataSpec] = None
    style: Optional[ChartStyleSpec | TableStyleSpec] = None
    # table
    rows: Optional[int] = None
    cols: Optional[int] = None
    col_widths: Optional[list[float]] = None
    cells: Optional[list[CellSpec]] = None
    merges: Optional[list[MergeSpec]] = None
    header: Optional[dict] = None
    # picture
    path: Optional[str] = None
    fit: Optional[str] = "aspect"
    # shape
    shape_type: Optional[str] = None
    fill: Optional[str] = None
    line: Optional[dict] = None
    text: Optional[dict] = None

class SlideSpec(BaseModel):
    layout: str = "blank"
    color_scheme: Optional[dict] = None
    elements: list[ElementSpec] = []

class PPTInstruction(BaseModel):
    meta: dict = {}
    slides: list[SlideSpec]

    @field_validator("meta")
    @classmethod
    def check_version(cls, v):
        assert v.get("$schema") == "ppt_instruction_v1", "Unknown schema version"
        return v


# ─── 解析器 ───

class InstructionParser:
    """接收 LLM 输出的 JSON 字符串，解析为 PPTInstruction"""

    @staticmethod
    def parse(json_str: str) -> PPTInstruction:
        return PPTInstruction.model_validate_json(json_str)

    @staticmethod
    def parse_stream(chunks: list[str]) -> PPTInstruction:
        """处理流式输出的拼接结果"""
        return PPTInstruction.model_validate_json(''.join(chunks))
```

### 10.6 SlideBuilder 实现骨架

```python
# infrastructure/ppt_engine/generator.py

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.chart.data import CategoryChartData

from .parser import PPTInstruction, ElementSpec

CHART_TYPE_MAP = {
    "column_clustered": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "bar_clustered": XL_CHART_TYPE.BAR_CLUSTERED,
    "line": XL_CHART_TYPE.LINE,
    "pie": XL_CHART_TYPE.PIE,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
    "area": XL_CHART_TYPE.AREA,
    "radar": XL_CHART_TYPE.RADAR,
    # ...
}

class SlideBuilder:
    def __init__(self, template_dir: str = "resources/templates"):
        self.template_dir = template_dir

    def build(self, instruction: PPTInstruction, output_path: str) -> str:
        meta = instruction.meta

        # 加载模板
        template_name = meta.get("template")
        if template_name:
            prs = Presentation(f"{self.template_dir}/{template_name}.pptx")
        else:
            prs = Presentation()

        # 逐页构建
        for slide_spec in instruction.slides:
            slide = self._add_slide(prs, slide_spec)
            for element in slide_spec.elements:
                self._render_element(slide, element)

        prs.save(output_path)
        return output_path

    def _add_slide(self, prs, slide_spec):
        layout_name = slide_spec.layout
        # 尝试按名匹配 layout
        for i, lo in enumerate(prs.slide_layouts):
            if lo.name == layout_name:
                return prs.slides.add_slide(prs.slide_layouts[i])
        # 回退：用 blank layout
        return prs.slides.add_slide(prs.slide_layouts[6])

    def _render_element(self, slide, el: ElementSpec):
        left, top = Inches(el.position.left), Inches(el.position.top)
        width = Inches(el.position.width)
        height = Inches(el.position.height) if el.position.height else None

        if el.type == "textbox":
            self._render_textbox(slide, el, left, top, width, height)
        elif el.type == "chart":
            self._render_chart(slide, el, left, top, width, height)
        elif el.type == "table":
            self._render_table(slide, el, left, top, width, height)
        elif el.type == "picture":
            self._render_picture(slide, el, left, top, width, height)
        elif el.type == "shape":
            self._render_shape(slide, el, left, top, width, height)

    def _render_chart(self, slide, el, left, top, width, height):
        chart_type = CHART_TYPE_MAP[el.chart_type]
        chart_data = CategoryChartData()
        chart_data.categories = el.data.categories
        for s in el.data.series:
            chart_data.add_series(s.name, s.values)

        graphic_frame = slide.shapes.add_chart(
            chart_type, left, top, width, height, chart_data
        )
        chart = graphic_frame.chart

        style = el.style
        if style:
            if style.has_legend:
                chart.has_legend = True
                # legend position...
            if style.has_data_labels:
                chart.plots[0].has_data_labels = True
                # data label position...
            if style.series_colors:
                for i, color in enumerate(style.series_colors):
                    if i < len(chart.series):
                        chart.series[i].format.fill.solid()
                        chart.series[i].format.fill.fore_color.rgb = \
                            RGBColor.from_string(color.lstrip('#'))

    def _render_table(self, slide, el, left, top, width, height):
        shape = slide.shapes.add_table(el.rows, el.cols, left, top, width, height)
        table = shape.table

        # 列宽
        if el.col_widths:
            for i, w in enumerate(el.col_widths):
                table.columns[i].width = Inches(w)

        # 单元格内容
        for cell_spec in el.cells:
            cell = table.cell(cell_spec.row, cell_spec.col)
            cell.text = cell_spec.text

        # 表头样式
        if el.header:
            row = el.header["row"]
            fill_color = RGBColor.from_string(el.header["fill"].lstrip('#'))
            font_color = el.header.get("font_color", "#ffffff")
            for c in range(el.cols):
                cell = table.cell(row, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = fill_color
                for p in cell.text_frame.paragraphs:
                    for r in p.runs:
                        r.font.color.rgb = RGBColor.from_string(font_color.lstrip('#'))
                        if el.header.get("font_bold"):
                            r.font.bold = True
                        if el.header.get("font_size"):
                            r.font.size = Pt(el.header["font_size"])

        # 合并单元格
        if el.merges:
            for m in el.merges:
                c1 = table.cell(m["from"][0], m["from"][1])
                c2 = table.cell(m["to"][0], m["to"][1])
                c1.merge(c2)

        # 边框 + 斑马条纹
        if el.style:
            self._apply_table_style(table, el)

    def _render_textbox(self, slide, el, left, top, width, height):
        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        tf.word_wrap = True

        for i, block in enumerate(el.content):
            if i == 0:
                p = tf.paragraphs[0]
            else:
                p = tf.add_paragraph()
            self._apply_paragraph(p, block.paragraph)

    def _apply_paragraph(self, p, para_spec):
        from pptx.enum.text import PP_ALIGN
        align_map = {
            "left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER,
            "right": PP_ALIGN.RIGHT, "justify": PP_ALIGN.JUSTIFY
        }
        p.alignment = align_map.get(para_spec.alignment, PP_ALIGN.LEFT)
        p.level = para_spec.level

        for run_spec in para_spec.runs:
            run = p.add_run()
            run.text = run_spec.text
            if run_spec.font:
                self._apply_font(run.font, run_spec.font)

    def _apply_font(self, font, font_spec):
        if font_spec.name: font.name = font_spec.name
        if font_spec.size: font.size = Pt(font_spec.size)
        if font_spec.bold is not None: font.bold = font_spec.bold
        if font_spec.italic is not None: font.italic = font_spec.italic
        if font_spec.color:
            font.color.rgb = RGBColor.from_string(font_spec.color.lstrip('#'))

    # ... _render_picture, _render_shape, _apply_table_style 类似实现 ...
```

### 10.7 Agent 如何产出指令 JSON

```
Agent 调用链：
  supervisor 逐页决策：
    → text_agent:  LLM → [{ "type": "textbox", ... }]
    → chart_agent:  LLM → [{ "type": "chart", "chart_type": "column_clustered", ... }]
    → table_agent:  LLM → [{ "type": "table", ... }]
    → image_agent:  LLM → [{ "type": "picture", "path": "..." }]
    → layout_agent: LLM → {"layout": "title_and_content", "color_scheme": {...}}

  所有 sub-agent 输出 element JSON 数组

  supervisor 合并为 PPTInstruction JSON
     ↓
  InstructionParser.parse(json_str) → PPTInstruction
     ↓
  SlideBuilder.build(instruction) → output.pptx
```

**关键设计点**：
- 每个 sub-agent 的 prompt 中包含对应元素类型的 JSON Schema
- LLM 通过 `response_format: "json_object"` 或 structured output 保证输出有效 JSON
- Pydantic 校验作为第二道防线（字段类型不匹配 → 报错 + 重试）
- 坐标/尺寸由 layout_agent 计算，其他 agent 不关心位置

---

## 十一、总体结论

### 7.1 能力矩阵

| 需求 | 纯 python-pptx | 需 lxml |
|------|---------------|---------|
| 文字：字体/大小/粗斜体/颜色/下划线 | ✅ | - |
| 文字：阴影 | 粗粒度开关 | 详细参数 |
| 文字：删除线/描边/发光/大写 | - | ✅ |
| 图表：创建（柱/线/饼/散点/气泡） | ✅ | - |
| 图表：系列/点/轴/标题/网格线颜色 | ✅ | - |
| 图表：图表区/绘图区背景 | - | ✅(简单) |
| 表格：创建/合并/文字格式 | ✅ | - |
| 表格：单元格填充色 | ✅ | - |
| 表格：单元格边框 | - | ✅(需封装) |
| 形状：创建/填充/线条 | ✅ | - |
| 图片：插入 | ✅ | - |
| 模板：加载使用 | ✅ | - |
| 模板：运行时创建 | - | ✅(极复杂) |
| SVG | - | cairosvg 转换 |

### 7.2 架构影响总结

| 调整项 | 说明 |
|--------|------|
| `charts.py` | **从 matplotlib→PNG 改为 python-pptx 原生图表** |
| `images.py` | 增加 SVG→PNG 转换管线（cairosvg） |
| `parser.py` (新增) | InstructionParser：JSON→Pydantic 校验 |
| `generator.py` | 增强为 SlideBuilder，支持全部元素类型 |
| `styles.py` | 增加完整配色方案（含主题色映射） |
| `resources/templates/` (新增) | 3-5 个预制 .pptx 模板 |
| `pyproject.toml` | 增加 `cairosvg` 依赖 |
| agent/sub-agents | prompt 中嵌入 JSON Schema，输出 element JSON |
