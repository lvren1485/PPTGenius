# PPT Agent 实现规划

> 日期：2026-06-04 · 状态：规划中

---

## 一、总体架构

```
coordinator ──dispatch──► PPT Agent Graph
                              │
              ┌───────────────┼───────────────┐
              │   Phase 1                    │   Phase 2
              │   Style Definition           │   Per-Slide Generation
              │                              │
              │   StyleAgent                 │   Supervisor (per slide)
              │   (color_scheme + layout)    │     Sub-agent方案:
              │                              │     ├── TextAgent (textbox + table)
              │                              │     ├── ChartAgent (chart)
              │                              │     └── ShapeAgent (decoration)
              │                              │     Freedom方案:
              │                              │     └── FreedomAgent (all at once)
              └───────────────┼───────────────┘
                              │
                         Assembly + Render .pptx
```

**两层图结构** + **双方案隔离**：

- 外层 graph：`create_presentation` → Phase 1 (style) → Phase 2 (per-slide loop) → Assembly
- Phase 2 内部：根据 `ppt_mode` 配置选择 Sub-agent 方案或 Freedom 方案
- 两种方案共享 Phase 1，但 Phase 2 代码完全隔离（不同文件/不同 graph 节点）

---

## 二、PPTState 定义

```python
class PPTState(TypedDict):
    # 入口参数
    user_id: int
    conversation_id: int
    query: str                          # 用户消息（修改时 = 修改意图描述）
    outline_id: int

    # 修改 vs 新建
    is_modify: bool                     # coordinator 传入
    presentation_id: int | None         # 修改时传入已有 ID

    # Phase 1 产出
    color_scheme_id: int | None
    template_id: int | None             # FK → templates.id
    selected_layouts: dict[str, dict]   # {layout_name: full_definition}
    style_rationale: str

    # Phase 2 进度
    current_slide_index: int
    total_slides: int
    ppt_mode: str                       # "sub_agent" | "freedom"

    # 上下文
    outline_slides: list[dict]          # 从 DB 加载
    design_rationales: Annotated[list[str], operator.add]
    file_path: str                      # output/{title}.pptx
    messages: Annotated[list[BaseMessage], operator.add]
```

### 修改入口

```
coordinator ──classify──► decision.task = "modify_ppt"
                              │
                         _run_ppt():
                           读取已有 presentation → 填充 PPTState
                           is_modify=True, presentation_id=existing.id
                           color_scheme_id=existing.color_scheme_id
                           保留已有 style 除非用户明确要求改
```

修改模式下 Phase 1 的行为：
- 用户说"换个深色配色"→ StyleAgent 重新选择 color_scheme
- 用户说"第5页图表改成饼图"→ Phase 1 跳过，Phase 2 只重做第5页
- 用户说"整体风格太单调了"→ StyleAgent 提高 style_density，可能重新选 layout

---

## 三、各 Agent 完整指令集清单

### 3.1 指令文件总览

```
instructions/
├── HOW_TO_READ.md                [元文档，不传给 Agent]
├── README.md                     [元文档，不传给 Agent]
├── background.json               ← StyleAgent
├── textbox.json                  ← TextAgent, FreedomAgent
├── table.json                    ← TextAgent, FreedomAgent
├── picture.json                  ← TextAgent, FreedomAgent
├── shape.json                    ← ShapeAgent, FreedomAgent
├── shape_catalog.json            ← ShapeAgent, FreedomAgent
├── shared/
│   ├── position.json             ← 所有 Agent（位置/尺寸通用知识）
│   ├── font.json                 ← 所有 Agent（字体通用知识）
│   ├── fill.json                 ← ShapeAgent, ChartAgent, FreedomAgent
│   └── line.json                 ← ShapeAgent, TextAgent, FreedomAgent
└── chart/
    ├── column.json               ← ChartAgent, FreedomAgent
    ├── bar.json                  ← ChartAgent, FreedomAgent
    ├── line.json                 ← ChartAgent, FreedomAgent
    ├── pie.json                  ← ChartAgent, FreedomAgent
    ├── area.json                 ← ChartAgent, FreedomAgent
    ├── scatter.json              ← ChartAgent, FreedomAgent
    ├── radar.json                ← ChartAgent, FreedomAgent
    └── bubble.json               ← ChartAgent, FreedomAgent
```

### 3.2 StyleAgent 指令集

| 指令文件 | 用途 | 必需 |
|----------|------|------|
| `background.json` | 幻灯片背景定义（纯色/渐变/图片） | 必需 |
| `shared/fill.json` | 渐变背景的 gradient_stops 语法 | 需要 |
| `shared/font.json` | 理解 color_scheme.fonts_json 字体结构 | 参考 |
| `shared/position.json` | 理解 slide 尺寸 13.333×7.5 | 参考 |

**工具**（不读指令，直接操作 DB）：

| 工具 | 说明 |
|------|------|
| `list_color_schemes` | 列出所有 active color schemes（含 style_density、decoration） |
| `get_color_scheme(id)` | 读取单个完整定义 |
| `save_color_scheme(name, label, colors, chart_colors, fonts, style_density, decoration)` | 新建或更新 |
| `list_layouts` | 列出 7 种内置 layout 名称 + label |
| `get_layout(name)` | 读取单个 layout 完整 JSON |
| `set_presentation_style(presentation_id, color_scheme_id, layout_mapping)` | [必须调用] 写入风格选择 |

### 3.3 TextAgent 指令集

| 指令文件 | 用途 | 何时读取 |
|----------|------|---------|
| `textbox.json` | 文本框：段落 + run + 字体 | 每页必读 |
| `table.json` | 表格：行列 + 单元格 + 合并 | 需要表格时读取 |
| **`shared/position.json`** | 绝对位置 + parent 相对定位 + slide 尺寸 | 每页必读 |
| **`shared/font.json`** | FontSpec：shadow/glow/kerning/smallcaps | 需要特殊字体时读取 |
| **`shared/line.json`** | textbox 边框：颜色/宽度/虚线 | 需要边框时读取 |
| `picture.json` | 图片元素（SVG icon name+color 模式） | 需要图标时读取 |

**工具**：

| 工具 | 说明 |
|------|------|
| `search_icons(query, top_k)` | 搜索 Tabler 5000+ 图标库 |
| `submit_text_elements(elements: list[dict])` | 提交 textbox/table/picture 元素数组，validate 后存入 |

**search_icons 使用场景**：
- 分条陈述：icon + textbox 为一组，重复 4-5 组（如 `search_icons("growth")` → `chart-line`）
- 三栏/四格布局：每栏顶部 icon 作为视觉标识（如 `search_icons("data")` → `database`）
- section 页：章节 icon 装饰（如 `search_icons("team")` → `users`）

### 3.4 ChartAgent 指令集

| 指令文件 | 用途 | 何时读取 |
|----------|------|---------|
| **`shared/position.json`** | 绝对位置 + parent 相对定位 | 每页必读 |
| `chart/column.json` | 柱形图 (clustered/stacked/stacked_100) | 数据为分类对比时 |
| `chart/bar.json` | 条形图（长标签横向） | 分类标签 >4 字时 |
| `chart/line.json` | 折线图 (line/markers/stacked) | 数据为时间序列时 |
| `chart/pie.json` | 饼图/环形图 (pie/doughnut) | 数据为占比时 |
| `chart/area.json` | 面积图 (area/stacked) | 累积趋势时 |
| `chart/scatter.json` | 散点图 (scatter/lines) | 两个数值变量关系时 |
| `chart/radar.json` | 雷达图 (radar/filled) | 多维度评分对比时 |
| `chart/bubble.json` | 气泡图 (bubble) | 三变量 (x+y+size) 时 |
| **`shared/font.json`** | title_font_size / axis_font_size | 参考 |
| **`shared/fill.json`** | chart_area_fill / plot_area_fill | 参考 |

**工具**：

| 工具 | 说明 |
|------|------|
| `read_chart_instruction(chart_type: str)` | 读取 `chart/{type}.json` 获取字段定义 |
| `submit_chart_element(element: dict)` | 提交单个 chart 元素，validate 后存入 |

**ChartAgent 选择逻辑**（在 prompt 中指定）：

```
数据特征 → chart_type 选择：
  分类对比（看绝对值）           → column_clustered
  分类对比（看总量+组成）         → column_stacked
  分类标签长（>4个汉字）          → bar_clustered
  时间序列趋势                   → line / line_markers
  占比/份额                      → pie / doughnut
  两个数值变量关系               → scatter
  多维度评分（≥3维）             → radar
  三变量（x+y+大小）             → bubble
  累积趋势                       → area

限制：
  - pie/doughnut 仅 1 个 series
  - 超过 6 个分类 → bar (横向)
  - 时间序列 → line/area
```

### 3.5 ShapeAgent 指令集

**Shape 独立为 Agent 的理由**：

- Title 页：需要大面积装饰图形（飘带、几何组合）+ 文字叠加
- Section 页：章节号圆形/菱形 + 分隔线 + 装饰元素
- Ending 页：致谢背景 + 装饰性图形
- Content 页：container 背景（圆角矩形）、标题装饰条（小色块）、页脚线
- 182 种形状，选择空间大，需要专门的 prompt 指导
- 形状上可叠加文字（`text` 字段），适合首页/尾页/节标题的创意排版

| 指令文件 | 用途 | 何时读取 |
|----------|------|---------|
| `shape.json` | 182 种形状 + fill/line/text/rotation | 每页必读 |
| `shape_catalog.json` | 形状中文名 + 分组 | 选形状时参考 |
| **`shared/position.json`** | 绝对位置 | 每页必读 |
| **`shared/fill.json`** | FillStyle：solid/gradient/no_fill/picture | 需要填充时读取 |
| **`shared/line.json`** | LineStyle：color/width/dash | 需要边框时读取 |
| **`shared/font.json`** | 形状内文字样式 | 形状含文字时读取 |

**工具**：

| 工具 | 说明 |
|------|------|
| `submit_shape_elements(elements: list[dict])` | 提交 shape 元素数组，validate 后存入 |

**Shape 在不同页面类型的使用**：

| 页面类型 | 典型 Shape 用途 | shape_type 示例 |
|----------|----------------|-----------------|
| title_slide | 大面积装饰（飘带、几何组合）+ 标题文字叠加 | `up_ribbon`, `rounded_rectangle`, `right_arrow` |
| section | 章节号圆形/六边形 + 分隔线 | `oval`, `hexagon`, `rectangle` (细线) |
| content | 标题装饰条 + container 背景框 + 页脚线 | `rectangle` (小色块), `rounded_rectangle` (容器) |
| ending | 致谢文字背景 + 装饰元素 | `rounded_rectangle`, `heart`, `star_5` |

### 3.6 FreedomAgent 指令集（全部指令）

Freedom 方案中，一个 Agent 获得**所有**指令集，外加 outline slide + layout 定义，一次性生成整页所有元素。

| 类别 | 指令文件 | 备注 |
|------|----------|------|
| 背景 | `background.json` | slide 级背景 |
| 文本 | `textbox.json` | 文本框 |
| 表格 | `table.json` | 表格 |
| 图片 | `picture.json` | SVG icon 搜索嵌入 |
| 形状 | `shape.json` + `shape_catalog.json` | 182 种形状 |
| 图表 | `chart/column.json` ~ `chart/bubble.json` (8个) | 按需读取 |
| 共享 | `shared/position.json` | 位置 |
| 共享 | `shared/font.json` | 字体 |
| 共享 | `shared/fill.json` | 填充 |
| 共享 | `shared/line.json` | 线条 |

**工具**：

| 工具 | 说明 |
|------|------|
| `search_icons(query, top_k)` | 搜索 SVG 图标 |
| `read_instruction(filename)` | 读取任意指令文件 |
| `submit_slide_elements(elements: list[dict])` | 提交整页元素数组，validate 后存入 |

### 3.7 指令集遗漏检查

对照 `instructions/` 目录全部文件：

| 文件 | 是否被覆盖 | 使用者 |
|------|-----------|--------|
| `HOW_TO_READ.md` | N/A（元文档） | — |
| `README.md` | N/A（元文档） | — |
| `background.json` | ✅ | StyleAgent, FreedomAgent |
| `textbox.json` | ✅ | TextAgent, FreedomAgent |
| `table.json` | ✅ | TextAgent, FreedomAgent |
| `picture.json` | ✅ | TextAgent, FreedomAgent |
| `shape.json` | ✅ | ShapeAgent, FreedomAgent |
| `shape_catalog.json` | ✅ | ShapeAgent, FreedomAgent |
| `shared/position.json` | ✅ | 所有 Agent |
| `shared/font.json` | ✅ | 所有 Agent |
| `shared/fill.json` | ✅ | ShapeAgent, ChartAgent, FreedomAgent |
| `shared/line.json` | ✅ | ShapeAgent, TextAgent, FreedomAgent |
| `chart/column.json` | ✅ | ChartAgent, FreedomAgent |
| `chart/bar.json` | ✅ | ChartAgent, FreedomAgent |
| `chart/line.json` | ✅ | ChartAgent, FreedomAgent |
| `chart/pie.json` | ✅ | ChartAgent, FreedomAgent |
| `chart/area.json` | ✅ | ChartAgent, FreedomAgent |
| `chart/scatter.json` | ✅ | ChartAgent, FreedomAgent |
| `chart/radar.json` | ✅ | ChartAgent, FreedomAgent |
| `chart/bubble.json` | ✅ | ChartAgent, FreedomAgent |
| `examples/*` | N/A（参考示例） | — |

**无遗漏**。所有 13 个指令文件 + 4 个 shared 文件均有 Agent 覆盖。

---

## 四、Phase 1 —— Style Definition

### 4.1 Color Scheme 设计

扩展现有 `color_schemes` 表（新增 2 字段）：

```sql
ALTER TABLE color_schemes
  ADD COLUMN style_density VARCHAR(16) NOT NULL DEFAULT 'moderate'
    COMMENT 'minimal|moderate|elaborate —— 控制全局装饰量',
  ADD COLUMN decoration_json JSON
    COMMENT '装饰开关: {title_accent_bar, section_divider_line, corner_bracket, ...}';
```

**Color Scheme JSON 结构**：

```json
{
  "name": "tech_blue",
  "label": "科技蓝",
  "style_density": "moderate",
  "colors": {
    "primary": "1a73e8",
    "accent": "ea4335",
    "text": "202124",
    "text_secondary": "5f6368",
    "bg": "f8f9fa",
    "bg_dark": "1a1a2e",
    "border": "dadce0"
  },
  "chart_colors": ["1a73e8", "ea4335", "34a853", "fbbc04", "ff6d01", "46bdc6"],
  "fonts": {
    "title": {"name": "微软雅黑", "size": 28, "bold": true, "color": "1a73e8"},
    "subtitle": {"name": "微软雅黑", "size": 18, "bold": false, "color": "5f6368"},
    "body": {"name": "微软雅黑", "size": 14, "bold": false, "color": "202124"},
    "caption": {"name": "微软雅黑", "size": 10, "bold": false, "color": "5f6368"}
  },
  "decoration": {
    "section_divider_line": true,
    "title_accent_bar": true,
    "page_number_style": "right_bottom",
    "corner_bracket": false
  }
}
```

**style_density 决定装饰量**：

| density | 每页装饰元素 | SVG 图标 | 说明 |
|---------|-------------|---------|------|
| `minimal` | 0-1 个 | 少量 | 大量留白，仅标题装饰条 + 页脚线 |
| `moderate` | 1-2 个 | 适中 | 标题装饰 + 页脚 + container 背景框 |
| `elaborate` | 2-3 个 | 大量 | 角标 + 渐变背景 + SVG icon + container 双层装饰 |

### 4.2 Layout 定义设计

**7 种 Layout**，存储于 `templates.layouts_json`（复用现有表）：

| layout_name | 用途 | 固定元素 | containers |
|-------------|------|---------|------------|
| `title_slide` | 封面 | title textbox + subtitle textbox + 大面积装饰 shape | 无 |
| `section` | 章节分隔 | section_number shape + title textbox + divider line | 无 |
| `content_bullet` | 单栏内容 | title textbox + body textbox + page_number | 无 |
| `content_two_column` | 两栏 | title textbox + 2 个 container (圆角矩形背景) | left_col, right_col |
| `content_three_column` | 三栏 | title textbox + 3 个 container | col_0, col_1, col_2 |
| `content_grid_2x2` | 2×2 网格 | title textbox + 4 个 container | grid_00, grid_01, grid_10, grid_11 |
| `ending` | 结尾/致谢 | title textbox + subtitle + 装饰 shape | 无 |

**Layout JSON 示例**（content_two_column）：

```json
{
  "name": "content_two_column",
  "label": "标题 + 两栏内容",
  "background": {"type": "solid", "color": "{{bg}}"},
  "fixed_elements": [
    {
      "id": "title",
      "type": "textbox",
      "position": {"left": 0.8, "top": 0.4, "width": 11.7, "height": 0.9},
      "style_ref": "title",
      "placeholder": true
    },
    {
      "id": "page_number",
      "type": "textbox",
      "position": {"left": 11.8, "top": 6.9, "width": 1.0, "height": 0.4},
      "style_ref": "caption",
      "text": "{page_num} / {total_pages}",
      "placeholder": false
    }
  ],
  "decorations": [
    {
      "id": "title_bar",
      "type": "shape",
      "shape_type": "rectangle",
      "position": {"left": 0.8, "top": 0.35, "width": 0.08, "height": 0.6},
      "fill": {"type": "solid", "color": "{{primary}}"},
      "line": null
    },
    {
      "id": "bottom_line",
      "type": "shape",
      "shape_type": "rectangle",
      "position": {"left": 0.8, "top": 6.95, "width": 11.7, "height": 0.015},
      "fill": {"type": "solid", "color": "{{border}}"},
      "line": null
    }
  ],
  "containers": [
    {
      "id": "left_col",
      "label": "左栏",
      "position": {"left": 0.5, "top": 1.6, "width": 5.8, "height": 5.1},
      "background": {"type": "solid", "color": "{{bg}}"},
      "decorations": [
        {
          "id": "left_col_bg",
          "type": "shape",
          "shape_type": "rounded_rectangle",
          "position": {"left": 0, "top": 0, "width": 5.8, "height": 5.1},
          "fill": {"type": "no_fill"},
          "line": {"color": "{{border}}", "width_pt": 0.5}
        }
      ]
    },
    {
      "id": "right_col",
      "label": "右栏",
      "position": {"left": 6.8, "top": 1.6, "width": 5.8, "height": 5.1}
    }
  ]
}
```

**变量插值**：`{{primary}}`、`{{bg}}`、`{{border}}` 等在 Assembly 阶段替换为 color_scheme 对应值。

### 4.3 关于 style_definitions 表

**不需要新建 `style_definitions` 表**。现有 `templates` 表已有 `layouts_json` 字段，足够存储所有 layout 定义。7 种基础 layout 来自 `resources/layouts/` JSON 文件，用户自定义变体通过 `save_layout` 工具更新 `templates.layouts_json`。

### 4.4 tool_choice 强制工具调用

```python
# StyleAgent 最后一步必须调用 set_presentation_style
model_with_forced = model.bind_tools(
    [set_presentation_style],
    tool_choice="set_presentation_style"  # DeepSeek 支持
)
```

LangChain 的 `create_agent` 不原生支持 `tool_choice`，但可在构造 agent 之前对 model 使用 `bind_tools`。`tool_choice="any"` 强制至少调用一个工具，`tool_choice="tool_name"` 强制调用特定工具。与已有的 retry 机制互补——`tool_choice` 从模型层面保证，retry 从逻辑层面兜底。

---

## 五、Phase 2 —— Sub-Agent 方案

### 5.1 Supervisor 逐页调度流程

```
style_done → supervisor → [slide_router] → dispatch agents → collect → next → ... → assembly

每页：
1. supervisor 根据 outline_slide.layout_type 选择对应 layout
2. supervisor 分析 content_json 决定需要哪些 agent：
   - 总是需要 TextAgent（标题 + 正文）
   - has_chart=true 或 content 含数据 → ChartAgent
   - 需要装饰/container 背景 → ShapeAgent（title/section/ending 页）
3. 创建 presentation_slide record
4. 串行或并行调度 sub-agent（每个 sub-agent 是独立 create_agent，message 隔离）
5. 所有 agent 完成后 → slide status=completed

失败处理：
  单个 agent 失败 → status=failed + error_message → retry（最多3次）
  supervisor 重试时只调失败的 agent
```

### 5.2 Slide Router

根据 outline slide 的 layout_type 选择 Layout：

```python
LAYOUT_MAP = {
    "title": "title_slide",
    "section": "section",
    "content": "content_bullet",      # 默认单栏
    "summary": "content_bullet",
    "thanks": "ending",
}
# 如果 content_json.recommended_ppt_format 是 two_column → "content_two_column"
# 如果是 three_column → "content_three_column"
# 如果是 four_grid → "content_grid_2x2"
```

### 5.3 Sub-Agent 共同模式

每个 sub-agent：
1. 独立 `create_agent`（自己的 tools + system_prompt）
2. 接收 `shared/position.json` + 自身领域指令
3. 接收 container bounds 作为相对坐标参考
4. 必须调用 `submit_*` 工具（`bind_tools(tool_choice="any")` 强制）
5. submit 内部调 `validate_elements()` → 合法存 DB，不合法返回错误 → LLM 修正重试

### 5.4 TextAgent 详细设计

```python
tools = [
    search_icons,           # 搜索 SVG 图标
    submit_text_elements,   # 提交 textbox/table/picture 元素
]
```

**输入上下文**：
```
color_scheme.fonts: {title: {size:28, bold:true, color:"1a73e8"}, body: {...}, caption: {...}}
color_scheme.colors: {primary, accent, text, text_secondary, bg, border}
container bounds: {parent_id: {left, top, width, height}}  ← 如分配到 left_col
可用图片素材: []  (暂无)
```

**生成内容**：
- title textbox（使用 style_ref "title"）
- body textbox（使用 style_ref "body"）
- 可选：table 元素（使用 style_ref "body" + header 样式）
- 可选：icon picture 元素（先 search_icons → 选 icon name → picture with name+color）

### 5.5 ChartAgent 详细设计

```python
tools = [
    read_chart_instruction,  # 读取 chart/{type}.json
    submit_chart_element,    # 提交 chart 元素
]
```

**数据提取**：ChartAgent 从 outline slide 的 `content_json.key_data` 提取数值，构造 `ChartData` / `XyChartData` / `BubbleChartData`。

### 5.6 ShapeAgent 详细设计

```python
tools = [
    submit_shape_elements,   # 提交 shape 元素数组
]
```

**ShapeAgent 对不同页面的处理**：

| 页面 | 行为 |
|------|------|
| title_slide | 大面积装饰形状（飘带、几何组合）；标题文字叠在 shape.text 中 |
| section | 章节数字 shape（圆形/六边形）+ 标题装饰条 + 分隔线 |
| content | container 的装饰边框（圆角矩形背景、分隔线） |
| ending | 致谢背景 + 装饰元素 |

**ShapeAgent 与 TextAgent 的协作**：
- title/section/ending 页：ShapeAgent 生成形状 + 文字叠加（创意排版）
- content 页：ShapeAgent 生成 container 背景 shape，TextAgent 在容器内放置文本

---

## 六、Phase 2 —— Freedom 方案

### 6.1 设计理念

一个 Agent 拿到**所有指令集** + outline slide 完整数据 + layout 定义 + container bounds，一次性生成整页所有元素。

### 6.2 FreedomAgent

```python
tools = [
    search_icons,            # SVG 图标搜索
    read_instruction,        # 读取任意指令文件
    submit_slide_elements,   # [必须调用] 提交整页所有元素
]
```

**输入上下文**：

```
# 完整 layout JSON（含 fixed_elements + decorations + containers）
# 完整 outline slide（title + content_json + notes）
# color_scheme（colors + chart_colors + fonts）
# container bounds 字典
# style_density 提示
```

**优势**：一次 LLM 调用完成整页，全局视角协调各元素。  
**劣势**：Prompt 长、token 消耗大、复杂页面可能超出模型能力。

### 6.3 代码隔离

```
agent/ppt/
├── phase2_sub_agent/          # Sub-Agent 方案
│   ├── __init__.py
│   ├── supervisor.py
│   ├── text_agent.py
│   ├── chart_agent.py
│   └── shape_agent.py
│
├── phase2_freedom/            # Freedom 方案（代码隔离）
│   ├── __init__.py
│   ├── supervisor.py
│   └── freedom_agent.py
│
└── graph.py                   # 根据 ppt_mode 路由
```

```python
# graph.py
if state["ppt_mode"] == "sub_agent":
    builder.add_node("phase2", build_sub_agent_phase(db))
else:
    builder.add_node("phase2", build_freedom_phase(db))
```

---

## 七、Relative Positioning（相对位置计算）

### 7.1 Container Bounds 定义

| container_id | 适用布局 | bounds (left, top, width, height) |
|--------------|---------|-----------------------------------|
| `slide` | 所有 | (0, 0, 13.333, 7.5) |
| `left_col` | content_two_column | (0.5, 1.6, 5.8, 5.1) |
| `right_col` | content_two_column | (6.8, 1.6, 5.8, 5.1) |
| `col_0` | content_three_column | (0.3, 1.6, 3.9, 5.1) |
| `col_1` | content_three_column | (4.5, 1.6, 3.9, 5.1) |
| `col_2` | content_three_column | (8.7, 1.6, 3.9, 5.1) |
| `grid_00` | content_grid_2x2 | (0.5, 1.6, 5.8, 2.3) |
| `grid_01` | content_grid_2x2 | (6.8, 1.6, 5.8, 2.3) |
| `grid_10` | content_grid_2x2 | (0.5, 4.1, 5.8, 2.3) |
| `grid_11` | content_grid_2x2 | (6.8, 4.1, 5.8, 2.3) |

### 7.2 相对坐标工作流

```
1. supervisor 根据 slide layout 确定使用的 containers
2. supervisor 将 container 信息写入 sub-agent prompt：
   "你被分配到 parent='left_col' 容器。
    bounds: {left:0, top:0, width:5.8, height:5.1}（相对容器左上角）
    生成元素时 position.parent='left_col'"

3. sub-agent 输出带 parent 字段的 position：
   {"left": 0.2, "top": 0.3, "width": 5.4, "height": 2.0, "parent": "left_col"}

4. Assembly 阶段调用 resolve_position()：
   abs_left = 0.5 + 0.2 = 0.7
   abs_top  = 1.6 + 0.3 = 1.9
```

与现有 `position.json` 指令兼容，无需修改 instruction 文件。

---

## 八、SVG 图标质量修复

### 8.1 问题

Tabler SVG 的 `viewBox="0 0 24 24"` 且 `width="24" height="24"`（像素）。resvg-py 以 300 DPI 渲染时输出仅 24 像素 ≈ 0.08 英寸 ≈ 2mm。python-pptx 拉伸到目标尺寸（如 1 英寸）后模糊。

### 8.2 修复方案

在 `get_colored_svg()` 中移除 SVG 的固定 `width`/`height`，让 viewBox 决定比例。然后在 `_svg_to_png()` 中通过 `resvg_py` 的 width/height 参数指定目标像素尺寸（如 300px → 1 英寸 at 300 DPI）。

**`icon_search.py:get_colored_svg` 修改**：

```python
# 替换 width="24" height="24" 为英寸单位
svg_text = re.sub(r'width="24"', 'width="1in"', svg_text, count=1)
svg_text = re.sub(r'height="24"', 'height="1in"', svg_text, count=1)
```

验证：渲染后 PNG 尺寸 ≥ 200px。

---

## 九、数据库 Seed 脚本

### 9.1 设计

Seed 脚本 `infrastructure/db/seed.py` **仅在表为空时运行**（幂等）：

```python
async def seed(engine):
    async with engine.begin() as conn:
        result = await conn.execute(select(func.count()).select_from(ColorScheme))
        if result.scalar() > 0:
            return  # 已有数据，跳过

        # 导入 color_schemes
        for f in glob.glob("resources/color_schemes/*.json"):
            d = json.load(open(f))
            await conn.execute(insert(ColorScheme).values(
                name=d["name"], label=d["label"],
                colors_json=d["colors"], chart_colors_json=d["chart_colors"],
                fonts_json=d["fonts"],
                style_density=d.get("style_density", "moderate"),
                decoration_json=d.get("decoration", {}),
            ))

        # 导入 layouts 到一个 template
        layouts = {}
        for f in glob.glob("resources/layouts/*.json"):
            d = json.load(open(f))
            layouts[d["name"]] = d

        await conn.execute(insert(Template).values(
            name="default", label="默认模板",
            category="general",
            layouts_json=layouts,
        ))
```

### 9.2 启动流程

```python
# main.py
async def init_db():
    await create_all(engine)          # 建表
    await seed(engine)                # 幂等 seed
```

### 9.3 DB 删除重建测试

```bash
mysql -u root -e "DROP DATABASE IF EXISTS pptgenius; CREATE DATABASE pptgenius;"
# 启动服务 → create_all 建表 → seed 导入
# 验证：color_schemes + templates 表有数据，所有 API 正常
```

---

## 十、Assembly & Rendering

```
Phase 2 完成 → assembly_node:
  1. 遍历 presentation_slides（按 slide_index）
  2. 每页：
     a. 读取 agent_outputs JSON
     b. 从 layout 获取 fixed_elements + decorations
     c. 合并：fixed_elements + decorations + agent 产出的 content elements
     d. resolve_position() 转绝对坐标
     e. 变量插值：{{primary}} → color_scheme.colors.primary
     f. 组装为 SlideSpec
  3. 组装 PPTInstruction
  4. validate_instruction() 全量校验
  5. generate_ppt() 渲染 .pptx
  6. 更新 presentation.file_path + status=completed
```

现有 `ppt_engine/generator.py` 的 `generate_ppt()` 已支持完整 validate + render 流水线，无需改动。

---

## 十一、Coordinator 集成

### 11.1 入口

```python
async def _run_ppt(db, user_id, conversation_id, query, outline,
                    existing_ppt, is_modify):
    state: PPTState = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "query": query,
        "outline_id": outline.id,
        "is_modify": is_modify,
        "presentation_id": existing_ppt.id if existing_ppt else None,
        "color_scheme_id": existing_ppt.color_scheme_id if existing_ppt else None,
        "template_id": existing_ppt.template_id if existing_ppt else None,
        "selected_layouts": {},
        "style_rationale": "",
        "current_slide_index": 0,
        "total_slides": outline.slide_count,
        "ppt_mode": "sub_agent",
        "outline_slides": [],
        "design_rationales": [],
        "file_path": f"output/{outline.title}.pptx",
        "messages": [],
    }
    graph = build_ppt_graph()
    async for event in graph.astream_events(state, config={"configurable": {"db": db}}, version="v2"):
        # SSE 事件处理 ...
```

### 11.2 修改模式路由

```python
if is_modify:
    if any(kw in query for kw in ["配色", "风格", "颜色", "布局"]):
        state["color_scheme_id"] = None  # 触发重新选择
    # 否则跳过 Phase 1，直接 Phase 2
```

---

## 十二、文件结构

```
src/pptgenius/agent/ppt/
├── __init__.py                  # export build_ppt_graph
├── graph.py                     # 外层 StateGraph + mode 路由
├── state.py                     # PPTState TypedDict
├── middleware.py                 # TokenCountingMiddleware（复用）
│
├── phase1_style.py              # StyleAgent: color_scheme + layout 选择
│
├── phase2_sub_agent/            # Sub-Agent 方案
│   ├── __init__.py
│   ├── supervisor.py            # 逐页调度 + slide_router
│   ├── text_agent.py            # TextAgent: textbox + table
│   ├── chart_agent.py           # ChartAgent: chart
│   └── shape_agent.py           # ShapeAgent: decoration shapes
│
├── phase2_freedom/              # Freedom 方案（代码隔离）
│   ├── __init__.py
│   ├── supervisor.py            # 逐页调度（简化）
│   └── freedom_agent.py         # 单 Agent 整页生成
│
├── common/
│   ├── __init__.py
│   ├── tools.py                 # 共享工具: search_icons, read_instruction, submit_*
│   ├── instruction_loader.py    # 指令文件加载 + prompt 注入
│   └── layout_resolver.py       # container bounds 计算 + position 解析
│
├── layout/
│   ├── __init__.py
│   ├── definitions.py           # 7 种 layout Python 常量
│   ├── renderer.py              # layout JSON → SlideSpec（含变量插值）
│   └── seed_data.py             # 硬编码 fallback（seed 失败时使用）
│
└── prompts.py                   # 所有 prompt 构建函数

src/pptgenius/resources/
├── layouts/                     # 7 种 layout JSON
│   ├── title_slide.json
│   ├── section.json
│   ├── content_bullet.json
│   ├── content_two_column.json
│   ├── content_three_column.json
│   ├── content_grid_2x2.json
│   └── ending.json
│
├── color_schemes/               # 预设 color schemes
│   ├── business_blue.json
│   ├── academic_warm.json
│   ├── minimal_dark.json
│   └── creative_vivid.json
│
└── prompts/ppt/
    ├── style_agent_system.txt
    ├── supervisor_system.txt
    ├── text_agent_system.txt
    ├── chart_agent_system.txt
    ├── shape_agent_system.txt
    └── freedom_agent_system.txt
```

---

## 十三、配置扩展

```yaml
# config.yaml 新增
agent:
  ppt:
    mode: "sub_agent"              # "sub_agent" | "freedom"
    max_retries_per_slide: 3
    slide_timeout_seconds: 120
```

---

## 十四、实施顺序

| 优先级 | 任务 | 改动范围 |
|--------|------|---------|
| **P0** | Schema 变更（color_schemes 新增 style_density + decoration_json） | `schema.sql`, `db/models.py` |
| **P0** | 7 种 Layout JSON + 4 套 Color Scheme JSON | `resources/layouts/`, `resources/color_schemes/` |
| **P0** | Seed 脚本 + 幂等逻辑 + DB 删除重建测试 | `db/seed.py`, `engine.py` |
| **P0** | PPTState + graph.py 骨架 + mode 路由 | `agent/ppt/state.py`, `graph.py` |
| **P1** | SVG 质量修复 | `ppt_engine/icon_search.py`, `image_parser.py` |
| **P1** | Phase 1: StyleAgent | `agent/ppt/phase1_style.py`, `prompts.py` |
| **P1** | 公共模块：instruction_loader + tools + layout_resolver | `agent/ppt/common/` |
| **P1** | `shared/*.json` 指令注入机制（`read_instruction` 工具） | `agent/ppt/common/instruction_loader.py` |
| **P2** | Sub-Agent 方案：Supervisor + TextAgent + ChartAgent + ShapeAgent | `agent/ppt/phase2_sub_agent/` |
| **P2** | PPT Prompt 编写（6 个 system prompt） | `resources/prompts/ppt/` |
| **P3** | Freedom 方案：FreedomAgent | `agent/ppt/phase2_freedom/` |
| **P3** | Assembly node（layout 渲染 + 变量插值 + validate + generate） | `agent/ppt/graph.py` |
| **P3** | Coordinator 集成（`_run_ppt` 完整实现 + SSE） | `agent/coordinator.py` |
| **P4** | 修改模式（PPT 修改入口 + 增量重做） | `agent/ppt/graph.py`, `coordinator.py` |
| **P4** | `config.yaml` ppt_mode 切换 | `config.yaml`, `config/models.py` |

---

## 十五、关键设计决策

| 决策 | 理由 |
|------|------|
| Shape 独立 agent | 182 种形状 + 文字叠加 + 首页/尾页/节标题创意排版，与 TextAgent 体系不同 |
| Table 合入 TextAgent | Table 本质是文本排版，共享 font/color 体系 |
| 复用 `templates` 表存 layout | 已有 `layouts_json` 字段，避免冗余 |
| `bind_tools(tool_choice=...)` 强制工具调用 | `create_agent` 不原生支持，但 model 层 `bind_tools` + DeepSeek `tool_choice` 可行 |
| 相对位置：sub-agent 输出相对坐标 + `parent` 字段 | 复用已有 `resolve_position()`，无需改 instruction |
| Sub-agent + Freedom 双方案代码隔离 | 不同目录、不同 graph 节点，后续可删其中一个无副作用 |
| Seed 幂等（仅在表为空时运行） | 重启不重复导入，DB 重建后自动填充 |
| 图片暂不做 | 无图片搜索/素材库，outline prompt 中可用图片列表传 `[]` |
