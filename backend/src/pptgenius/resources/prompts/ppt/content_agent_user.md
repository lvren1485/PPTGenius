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

假如outline中的内容装不下，挑选其中最重要，最契合主题的内容进行展示，或者对内容进行适当的精简和概括。
如果outline中要求添加图片、数据，但没有给出，则留出占位符即可。

请按以下步骤设计该页的完整视觉方案：
1. **submit_plan** — 划分页面区域（3-6 个 part），每个 part 描述设计意图
2. **submit_background** — 设置背景
3. 对每个 part：**submit_element**(part="xxx") ×N → **check_parts**(part="xxx") 检查 → **check_parts**(part="xxx", complete=true) 标记
4. **check_parts()** — 确认所有 part 均为 complete
**如果 plan 中已有内容（修改模式），基于已有 plan 修改或追加 part，不要完全覆盖。**
