# PPT 指令集 v1

LLM 输出格式。单个 slide 的 JSON，由 supervisor 拼装为完整指令。

## 元素指令类型

| type | 文件 |
|------|------|
| `textbox` | [textbox.json](textbox.json) |
| `chart` | 见下方子类型 |
| `table` | [table.json](table.json) |
| `picture` | [picture.json](picture.json) |
| `shape` | [shape.json](shape.json) |

## 图表子类型

| chart_type | 文件 | 说明 |
|-----------|------|------|
| `column_*` | [chart/column.json](chart/column.json) | 柱形图（簇状/堆积/百分比堆积） |
| `bar_*` | [chart/bar.json](chart/bar.json) | 条形图 |
| `line_*` | [chart/line.json](chart/line.json) | 折线图 |
| `pie` / `doughnut` | [chart/pie.json](chart/pie.json) | 饼图 / 环形图 |
| `area_*` | [chart/area.json](chart/area.json) | 面积图 |
| `scatter` | [chart/scatter.json](chart/scatter.json) | 散点图 |
| `radar` | [chart/radar.json](chart/radar.json) | 雷达图 |
| `bubble` | [chart/bubble.json](chart/bubble.json) | 气泡图 |

## 共享 schema

| 文件 | 说明 |
|------|------|
| [shared/position.json](shared/position.json) | 位置/尺寸 |
| [shared/font.json](shared/font.json) | 字体 |
| [shared/fill.json](shared/fill.json) | 填充（纯色/渐变/透明） |
| [shared/line.json](shared/line.json) | 线条（颜色/宽度/虚线） |

## 示例

| 文件 | 说明 |
|------|------|
| [examples/chart_column.json](examples/chart_column.json) | 柱形图示例 |
| [examples/table.json](examples/table.json) | 表格示例 |
| [examples/shape.json](examples/shape.json) | 形状示例 |
