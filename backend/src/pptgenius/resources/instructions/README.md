# PPT 指令集 v1

LLM 输出格式。chart agent 先选图类型，再读对应指令文件生成 JSON。

## 元素指令

| type | 文件 | 说明 |
|------|------|------|
| `textbox` | [textbox.json](textbox.json) | 文本框 |
| `chart` | [chart/](chart/) | 图表（8种子类型） |
| `table` | [table.json](table.json) | 表格 |
| `picture` | [picture.json](picture.json) | 图片 |
| `shape` | [shape.json](shape.json) | 自选图形 |

## 图表子类型

| chart_type | 指令文件 | 数据模型 | 说明 |
|-----------|---------|---------|------|
| `column_*` | [chart/column.json](chart/column.json) | ChartData | 柱形图（簇状/堆积/百分比堆积） |
| `bar_*` | [chart/bar.json](chart/bar.json) | ChartData | 条形图（横向） |
| `line_*` | [chart/line.json](chart/line.json) | ChartData | 折线图 |
| `pie` / `doughnut` | [chart/pie.json](chart/pie.json) | ChartData | 饼图/环形图（仅1个series） |
| `area_*` | [chart/area.json](chart/area.json) | ChartData | 面积图 |
| `scatter` | [chart/scatter.json](chart/scatter.json) | XyChartData | 散点图（需 points 格式） |
| `radar` | [chart/radar.json](chart/radar.json) | ChartData | 雷达图 |
| `bubble` | [chart/bubble.json](chart/bubble.json) | BubbleChartData | 气泡图（需 points+size） |

## 共享 schema

| 文件 | 说明 |
|------|------|
| [shared/position.json](shared/position.json) | 位置/尺寸，支持 relative 相对定位 |
| [shared/font.json](shared/font.json) | 字体 + 阴影/发光效果 |
| [shared/fill.json](shared/fill.json) | 填充（纯色/渐变/透明/图片） |
| [shared/line.json](shared/line.json) | 线条（颜色/宽度/虚线） |

## 示例

| 文件 | 说明 |
|------|------|
| [examples/chart_column.json](examples/chart_column.json) | 柱形图（ChartData） |
| [examples/chart_scatter.json](examples/chart_scatter.json) | 散点图（XyChartData） |
| [examples/table.json](examples/table.json) | 表格 |
| [examples/shape.json](examples/shape.json) | 形状 |
