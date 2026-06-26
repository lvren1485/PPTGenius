## Slide 信息
标题: {slide_title}
页面类型: {slide_layout_type}
推荐格式: {recommended_format}
has_chart: {has_chart}
has_image: {has_image}

## outline content_json
核心要点: {main_points}
{detailed_content_block}{key_data_block}{visual_note_block}
{existing_content_section}
{color_scheme_section}
{template_section}
{neighbor_section}
{status_section}
{plan_section}
## 画布尺寸
16:9 宽屏 = 13.333 × 7.5 inch。坐标系: 左上角为原点 (0,0)，left 从左到右增大，top 从上到下增大。

## 画布网格参考
竖向 6 列 × 横向 4 行，可作为元素对齐参照：
```
竖线 x = 0 | 2.22 | 4.44 | 6.67 | 8.89 | 11.11 | 13.33
横线 y = 0 | 1.88 | 3.75 | 5.63 | 7.5
```

## 常用区域坐标
| 区域 | left | top | width | height |
|------|------|-----|-------|--------|
| 页面标题 | 0.8 | 0.3 | 11.7 | 0.9 |
| 正文区(全宽) | 1.0 | 1.5 | 11.3 | 4.5 |
| 左栏 | 0.8 | 1.6 | 5.5 | 5.0 |
| 右栏 | 7.0 | 1.6 | 5.5 | 5.0 |
| 图表区(全宽) | 0.8 | 1.8 | 11.7 | 4.5 |
| 底部备注 | 0.8 | 6.5 | 11.7 | 0.5 |

假如outline中的内容装不下，挑选其中最重要，最契合主题的内容进行展示，或者对内容进行适当的精简和概括。
如果outline中要求添加图片、数据，但没有给出，则留出占位符即可。

请按以下步骤设计该页的完整视觉方案：
1. **submit_plan** — 划分页面区域（3-6 个 part），每个 part 描述设计意图
2. **submit_background** — 设置背景
3. 对每个 part：**submit_element**(part="xxx") ×N → **check_parts**(part="xxx") 检查 → **check_parts**(part="xxx", complete=true) 标记
4. **check_parts()** — 确认所有 part 均为 complete
**如果 plan 中已有内容（修改模式），基于已有 plan 修改或追加 part，不要完全覆盖。**
