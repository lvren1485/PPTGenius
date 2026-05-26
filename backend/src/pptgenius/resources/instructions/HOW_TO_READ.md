# 指令文件阅读指南

本目录下的 `.json` 文件是 PPT 指令集说明书。每个 agent 根据这些说明书生成符合 schema 的 JSON。


## 符号约定

每个 instruction 文件使用以下符号描述字段的类型和取值范围：

### 基础类型

| 写法 | 含义 | JSON 示例 |
|------|------|----------|
| `string` | 文本 | `"hello"` |
| `int` | 整数 | `14` |
| `float` | 小数 | `1.5` |
| `bool` | 布尔 | `true` / `false` |

### 复合类型

| 写法 | 含义 | JSON 示例 |
|------|------|----------|
| `string[]` | **字符串数组** | `["Q1","Q2","Q3"]` |
| `float[]` | **数字数组** | `[120, 145, 138]` |
| `hex[]` | **颜色数组** (不含#) | `["1a73e8","ea4335"]` |
| `[{name, values}]` | **对象数组** | `[{"name":"A","values":[1,2]}]` |
| `{key: value}` | **对象** | `{"left":1.0,"top":2.0}` |

### 可选/联合

| 写法 | 含义 | 示例说明 |
|------|------|---------|
| `string\|null` | 字符串**或**不填 | `null` 表示"继承默认值/不设置" |
| `hex\|'none'\|null` | 颜色值**或**显式"透明"**或**不填 | `"none"` = 明确不要填充 |
| `'A'\|'B'\|'C'` | **只能是**这些值之一 | `"left"` `"center"` `"right"` |
| `float >=0` | 必须 ≥ 0 | `0` `1.5` 均可, `-1` 非法 |
| `float >0` | 必须 > 0 | `1` `0.5` 均可, `0` 非法 |
| `int 0-8` | 范围限制 | 缩进层级只能是 0,1,2,...,8 |

### 标准值枚举

| 写法 | 可用值 |
|------|-------|
| `alignment` | `"left"` `"center"` `"right"` `"justify"` |
| `legend_position` | `"bottom"` `"right"` `"left"` `"top"` |
| `data_label_position` | `"outside_end"` `"inside_end"` `"center"` `"inside_base"` |
| `fill_type` | `"solid"` `"gradient"` `"no_fill"` `"picture"` |
| `dash` | `"solid"` `"dash"` `"dot"` `"dash_dot"` |
| `fit` | `"aspect"` (等比缩放) `"stretch"` (拉伸填充) `"crop"` (裁切) |

## 每个 instruction JSON 的结构

每个指令文件都有一个固定结构：

```json
{
  "type": "chart",         ← 元素类型标识符
  "chart_type": "...",     ← 子类型 (仅 chart 有)
  "description": "...",    ← 一句话说明这个元素是干什么的
  "fields": { ... },       ← 字段定义 (最核心的部分)
  "note": "..."            ← 可选, 额外注意事项
}
```

### 如何阅读 `fields`

`fields` 是一个对象, 每个 key 由你填入 JSON。value 是一个描述字符串, 说明该字段的类型和含义。

翻译示例:
```
"title": "string|null, 图表标题"
        └─────┬─────┘  └──┬──┘
           类型约束      中文说明

意思是: 你输出的 JSON 里要写 →  "title": "你的标题"
        或者不填这个字段 → 不写 title 键
```

翻译示例2:
```
"series_colors": "hex[]|null, 按系列顺序 e.g. ['1a73e8','ea4335']"
                 └──┬──┘└┬┘  └──────┬──────┘  └────────┬────────┘
                 颜色数组 可选    中文说明         具体示例

意思是: 你输出 →  "series_colors": ["1a73e8","ea4335"]
        或者 → 不写这个字段
        数组中每个元素是6位hex颜色(不要#号)
```

### Markers (标记字段)

指令文件中以下 key 是**标记/说明字段**, 不是你要输出的 JSON 字段:

| 标记 | 作用 |
|------|------|
| `description` | 一句话说明这个指令文件描述的是什么 |
| `note` | 重要注意事项, 必须遵守 |
| `fields` | 包裹所有字段定义的容器，你的输出是fields中定义的字段 |
| `example` | 示例 JSON 片段, 展示正确写法 |
| `same_fields_as` | 表示本文件字段定义与另一个文件相同 |

### 选择指南

| 你有的数据 | 选 chart_type |
|-----------|-------------|
| 分类对比, 看绝对值 | `column_clustered` |
| 分类对比, 看总量 + 组成 | `column_stacked` |
| 分类对比, 只看比例 | `column_stacked_100` |
| 分类标签很长(>4字) | `bar_clustered` (横向) |
| 时间序列趋势 | `line` 或 `line_markers` |
| 占比/份额 | `pie` |
| 占比+中间可放总数值 | `doughnut` |
| 累积趋势 | `area` |
| 两个数值变量的关系 | `scatter` |
| 多维度评分对比 | `radar` |
| 三维数据(X值+Y值+大小) | `bubble` |

**限制**: pie/doughnut 图表只能有 1 个 series (只能画一组数据)

## 完整 JSON 结构层次

最终输出的完整 PPT Instruction JSON 是这样的:

```json
{
  "meta": {
    "slide_width": 13.333,
    "slide_height": 7.5,
    "language": "zh"
  },
  "slides": [                           ← 幻灯片数组
    {
      "layout": "blank",                ← 布局名
      "background": { ... },            ← 背景 (可选, 见 background.json)
      "notes": "这是演讲者备注",         ← 写入 PPT 备注 (可选, 存 outline 内容)
      "elements": [                     ← 元素数组
        {                               ← 元素1 (textbox)
          "type": "textbox",
          "position": { "left": 0.8, "top": 0.4, "width": 11.7, "height": 0.9 },
          "content": [...]
        },
        {                               ← 元素2 (chart)
          "type": "chart",
          "chart_type": "column_clustered",
          "position": { ... },
          "data": { ... },
          "style": { ... }
        }
      ]
    },
    {                                   ← 第二页幻灯片
      "layout": "blank",
      "elements": [...]
    }
  ]
}
```

在一些任务中，可能会只要求生成 `elements` 数组中的元素 JSON，而不需要生成完整的幻灯片结构。无论如何，元素 JSON 的字段和格式必须严格遵守上述 instruction 文件中的定义。

## 字段值填写顺序

当你生成一个 element JSON 时, 按这个顺序填写:

1. 先写 `type` — 确定元素类型
2. 再写 `position` — 位置/尺寸 (见 shared/position.json)
3. 填写元素特有的字段 (content/data/cells/text 等)
4. 最后填 `style`/`fill`/`line` — 样式是可选的, 不填=用默认样式

## 常见错误

| 错误 | 正确写法 |
|------|---------|
| `"color": "#1a73e8"` | `"color": "1a73e8"` (不要 # 号) |
| `"chart_type": "column"` | `"chart_type": "column_clustered"` (必须精确匹配) |
| `"series": [1,2,3]` | `"series": [{"name":"A","values":[1,2,3]}]` (series 是对象数组) |
| `"values": [120]` 只有1个值 | values长度必须= categories 长度 |
| pie 用了 2 个 series | pie 只能用 1 个 series |
| `"position": {"x":1,"y":2}` | `"position": {"left":1,"top":2,"width":8,"height":5}` |
