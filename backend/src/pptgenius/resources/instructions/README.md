# PPT 指令集 v1

LLM 输出的 PPT 元素 JSON 规范。

## 顶层结构

```json
{
  "meta": {
    "slide_width": 13.333, "slide_height": 7.5,
    "language": "zh"
  },
  "slides": [
    { "layout": "blank", "background": {...}, "notes": "...", "elements": [...] }
  ]
}
```

## 元素指令

| 指令文件 | type | 说明 |
|---------|------|------|
| [textbox.json](textbox.json) | `textbox` | 文本框（段落+多run文本+字体效果） |
| [table.json](table.json) | `table` | 表格（表头/斑马条纹/合并单元格） |
| [picture.json](picture.json) | `picture` | 图片嵌入（SVG自动转PNG 300DPI） |
| [shape.json](shape.json) | `shape` | 自选图形（182种, 见 shape_catalog.json） |
| [background.json](background.json) | (slide级) | 幻灯片背景（纯色/渐变/图片） |

## 图表指令（按类型分）

| 指令文件 | chart_type | 数据模型 | 说明 |
|---------|-----------|---------|------|
| [chart/column.json](chart/column.json) | `column_clustered/stacked/stacked_100` | ChartData | 柱形图 |
| [chart/bar.json](chart/bar.json) | `bar_clustered/stacked/stacked_100` | ChartData | 条形图（横向） |
| [chart/line.json](chart/line.json) | `line/line_markers/stacked/stacked_100` | ChartData | 折线图 |
| [chart/pie.json](chart/pie.json) | `pie/exploded/doughnut/exploded` | ChartData | 饼图/环形图 |
| [chart/area.json](chart/area.json) | `area/stacked/stacked_100` | ChartData | 面积图 |
| [chart/scatter.json](chart/scatter.json) | `scatter/scatter_lines/no_markers` | XyChartData | 散点图 |
| [chart/radar.json](chart/radar.json) | `radar/filled/markers` | ChartData | 雷达图 |
| [chart/bubble.json](chart/bubble.json) | `bubble` | BubbleChartData | 气泡图 |

## 共享 schema

| 文件 | 内容 |
|------|------|
| [shared/position.json](shared/position.json) | 位置/尺寸 + 相对定位(parent) |
| [shared/font.json](shared/font.json) | 字体(含阴影/发光/删除线/小型大写) |
| [shared/fill.json](shared/fill.json) | 填充(纯色/渐变/透明/图片) |
| [shared/line.json](shared/line.json) | 线条(颜色/宽度/虚线) |

## Prompt 构建指南

### 1. Chart Agent Workflow

chart agent 的工作流程:

1. **选图类型** — 根据数据特征选择 chart_type
2. **读取指令文件** — 读 `chart/{type}.json` 获取完整 field 定义
3. **生成 JSON** — 按 schema 输出单页 element JSON

Prompt 示例结构:
```
你是一个PPT图表生成器。根据以下数据选择最合适的图表类型, 然后读取对应的指令文件生成JSON。

可选类型:
  - column: 柱形图(分类对比) → chart/column.json
  - bar: 条形图(长标签) → chart/bar.json
  - line: 折线图(趋势) → chart/line.json
  - pie: 饼图(占比) → chart/pie.json
  - scatter: 散点图(相关性) → chart/scatter.json
  - radar: 雷达图(多维度) → chart/radar.json
  - bubble: 气泡图(三变量) → chart/bubble.json

规则:
  - 数据是 [分类→数值] 对 → column/bar/line/pie
  - 数据是 [数值→数值] 对 → scatter
  - 数据是 [数值→数值→大小] 三元组 → bubble
  - pie/doughnut 仅支持 1 个 series
  - 超过 6 个分类 → 用 bar (横向) 避免标签重叠
  - 时间序列 → 用 line/area

输出格式:
{
  "type": "chart",
  "chart_type": "column_clustered",
  "position": { "left": 1.5, "top": 1.5, "width": 10.0, "height": 5.5 },
  "title": "图表标题",
  "data": { ... },
  "style": { ... }
}
```

### 2. Table Agent Workflow

从结构化数据生成表格 JSON:
- 检查行/列数 (cols = len(headers), rows = len(data) + 1)
- col_widths 按内容长度估算 (中文约2字符=1英寸)
- 表头行设置 header 字段
- 数字列右对齐, 文字列左对齐

### 3. Layout Agent Workflow

layout agent 输出 SlideSpec (不含 elements):
```json
{
  "layout": "blank",
  "background": { "type": "solid", "color": "e8f0fe" },
  "notes": "本页内容说明"
}
```

### 4. Text Agent Workflow

从大纲生成逐页文本 element:
- 标题 → textbox + size:28 + bold
- 正文 → textbox + size:14 + color:333333
- 要点列表 → textbox + 多 paragraph + level 缩进
- 关键数字 → font.bold + color 强调色

### 5. 元素坐标规范

16:9 幻灯片 (13.333×7.5 英寸):
```
封面标题: { left: 1.0, top: 2.5, width: 11.3, height: 1.2 }
页面标题: { left: 0.8, top: 0.4, width: 11.7, height: 0.9 }
图表区:   { left: 0.8, top: 1.6, width: 8.5, height: 5.0 }
侧边栏:   { left: 9.8, top: 1.6, width: 3.0, height: 5.0 }
表格区:   { left: 1.0, top: 1.5, width: 11.0, height: 5.5 }
全宽文本: { left: 1.0, top: 1.5, width: 11.3, height: 5.5 }
```

相对位置 (parent 字段):
```
parent_bounds:
  slide:      { left: 0,     top: 0,    width: 13.333, height: 7.5 }
  left_col:   { left: 0.5,   top: 1.2,  width: 5.8,    height: 5.8 }
  right_col:  { left: 6.8,   top: 1.2,  width: 5.8,    height: 5.8 }
```

### 6. 颜色约定

| 用途 | 推荐色 | hex |
|------|-------|-----|
| 主色 | blue | 1a73e8 |
| 强调 | red | ea4335 |
| 成功 | green | 34a853 |
| 警告 | yellow | fbbc04 |
| 文字 | dark | 202124 |
| 次要文字 | gray | 5f6368 |
| 背景 | light | f8f9fa |
| 边框 | border | dadce0 |

## 示例

| 文件 | 说明 |
|------|------|
| [examples/chart_column.json](examples/chart_column.json) | 柱形图 (ChartData) |
| [examples/chart_scatter.json](examples/chart_scatter.json) | 散点图 (XyChartData) |
| [examples/chart_bubble.json](examples/chart_bubble.json) | 气泡图 (BubbleChartData) |
| [examples/table.json](examples/table.json) | 表格 |
| [examples/shape.json](examples/shape.json) | 形状 |

完整测试: `src/tests/test_ppt_engine/test_all_elements.json`
