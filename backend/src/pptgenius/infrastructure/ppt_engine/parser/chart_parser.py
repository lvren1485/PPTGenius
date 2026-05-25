"""Chart element renderer."""

from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import (
    XL_CHART_TYPE,
    XL_LEGEND_POSITION,
    XL_LABEL_POSITION,
)

from .base import ChartElement
from .styles import set_chart_area_fill, set_plot_area_fill


CHART_TYPE_MAP = {
    "column_clustered": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "column_stacked": XL_CHART_TYPE.COLUMN_STACKED,
    "column_stacked_100": XL_CHART_TYPE.COLUMN_STACKED_100,
    "bar_clustered": XL_CHART_TYPE.BAR_CLUSTERED,
    "bar_stacked": XL_CHART_TYPE.BAR_STACKED,
    "bar_stacked_100": XL_CHART_TYPE.BAR_STACKED_100,
    "line": XL_CHART_TYPE.LINE,
    "line_markers": XL_CHART_TYPE.LINE_MARKERS,
    "line_stacked": XL_CHART_TYPE.LINE_STACKED,
    "line_stacked_100": XL_CHART_TYPE.LINE_STACKED_100,
    "pie": XL_CHART_TYPE.PIE,
    "pie_exploded": XL_CHART_TYPE.PIE_EXPLODED,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
    "doughnut_exploded": XL_CHART_TYPE.DOUGHNUT_EXPLODED,
    "area": XL_CHART_TYPE.AREA,
    "area_stacked": XL_CHART_TYPE.AREA_STACKED,
    "area_stacked_100": XL_CHART_TYPE.AREA_STACKED_100,
    "scatter": XL_CHART_TYPE.XY_SCATTER,
    "scatter_lines": XL_CHART_TYPE.XY_SCATTER_LINES,
    "scatter_lines_no_markers": XL_CHART_TYPE.XY_SCATTER_LINES_NO_MARKERS,
    "radar": XL_CHART_TYPE.RADAR,
    "radar_filled": XL_CHART_TYPE.RADAR_FILLED,
    "radar_markers": XL_CHART_TYPE.RADAR_MARKERS,
    "bubble": XL_CHART_TYPE.BUBBLE,
}

LEGEND_POSITION_MAP = {
    "bottom": XL_LEGEND_POSITION.BOTTOM,
    "right": XL_LEGEND_POSITION.RIGHT,
    "left": XL_LEGEND_POSITION.LEFT,
    "top": XL_LEGEND_POSITION.TOP,
}

LABEL_POSITION_MAP = {
    "outside_end": XL_LABEL_POSITION.OUTSIDE_END,
    "inside_end": XL_LABEL_POSITION.INSIDE_END,
    "center": XL_LABEL_POSITION.CENTER,
    "inside_base": XL_LABEL_POSITION.INSIDE_BASE,
    "best_fit": XL_LABEL_POSITION.BEST_FIT,
}


def render_chart(slide, el: ChartElement) -> None:
    """Render a native chart element onto a slide."""
    left = Inches(el.position.left)
    top = Inches(el.position.top)
    width = Inches(el.position.width)
    height = Inches(el.position.height)
    chart_type = CHART_TYPE_MAP[el.chart_type]

    chart_data = CategoryChartData()
    chart_data.categories = el.data.categories
    for s in el.data.series:
        chart_data.add_series(s.name, s.values)

    graphic_frame = slide.shapes.add_chart(
        chart_type, left, top, width, height, chart_data
    )
    chart = graphic_frame.chart

    # Title
    if el.title:
        chart.has_title = True
        chart.chart_title.text_frame.paragraphs[0].text = el.title

    # Style
    style = el.style
    if style:
        if style.has_legend:
            chart.has_legend = True
            if style.legend_position:
                chart.legend.position = LEGEND_POSITION_MAP.get(
                    style.legend_position, XL_LEGEND_POSITION.BOTTOM
                )
            chart.legend.include_in_layout = False

        if style.has_data_labels and chart.plots:
            plot = chart.plots[0]
            plot.has_data_labels = True
            if style.data_label_position:
                plot.data_labels.position = LABEL_POSITION_MAP.get(
                    style.data_label_position, XL_LABEL_POSITION.OUTSIDE_END
                )

        if style.series_colors:
            for i, c in enumerate(style.series_colors):
                if i < len(chart.series):
                    chart.series[i].format.fill.solid()
                    chart.series[i].format.fill.fore_color.rgb = RGBColor.from_string(c)

        # Chart area / plot area
        if style.chart_area_fill:
            if style.chart_area_fill == "none":
                set_chart_area_fill(chart, no_fill=True)
            else:
                set_chart_area_fill(chart, color_hex=style.chart_area_fill)
        if style.plot_area_fill:
            if style.plot_area_fill == "none":
                set_plot_area_fill(chart, no_fill=True)
            else:
                set_plot_area_fill(chart, color_hex=style.plot_area_fill)

        if style.title_font_size:
            chart.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(
                style.title_font_size
            )
        if style.axis_font_size:
            if hasattr(chart, "category_axis"):
                chart.category_axis.tick_labels.font.size = Pt(style.axis_font_size)
            if hasattr(chart, "value_axis"):
                chart.value_axis.tick_labels.font.size = Pt(style.axis_font_size)
