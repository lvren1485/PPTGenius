"""Chart generation for embedding in slides."""

from pathlib import Path
from ..config import config


def generate_chart_image(chart_type: str, data: dict, title: str = "") -> str:
    """Generate a chart image and return its path.

    Args:
        chart_type: bar, line, pie, scatter, histogram.
        data: Dict with chart data (labels, values, x, y, etc.).
        title: Optional chart title.

    Returns:
        Path to the generated PNG image.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5))

    if chart_type == "bar":
        ax.bar(data.get("labels", []), data.get("values", []))
    elif chart_type == "line":
        ax.plot(data.get("labels", []), data.get("values", []), marker="o")
    elif chart_type == "pie":
        ax.pie(data.get("values", []), labels=data.get("labels", []), autopct="%1.1f%%")
    elif chart_type == "scatter":
        ax.scatter(data.get("x", []), data.get("y", []))
    elif chart_type == "histogram":
        ax.hist(data.get("values", []), bins=data.get("bins", 10))

    if title:
        ax.set_title(title)

    image_path = config.OUTPUT_DIR / f"chart_{title.replace(' ', '_')[:20]}.png"
    plt.tight_layout()
    plt.savefig(str(image_path), dpi=150)
    plt.close()
    return str(image_path)
