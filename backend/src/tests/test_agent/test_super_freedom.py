"""Super-freedom pipeline test — load sample JSON, validate, generate PPTX."""
import asyncio, sys, os, json
sys.path.insert(0, 'src')

from pptgenius.infrastructure.ppt_engine.generator import generate_ppt

RESOURCES = os.path.join(os.path.dirname(__file__), '..', 'resources')
OUTPUT_DIR = 'data/test_output'

def test_load_and_generate():
    """Load super_freedom sample JSON, generate PPTX, verify output."""
    json_path = os.path.join(RESOURCES, 'super_freedom_sample.json')
    with open(json_path, encoding='utf-8') as f:
        slides = json.load(f)

    assert len(slides) == 3, f"Expected 3 slides, got {len(slides)}"
    total_elements = sum(len(s['elements']) for s in slides)
    assert total_elements >= 20, f"Expected >=20 elements, got {total_elements}"

    # Verify font sizes >= 14pt
    for si, slide in enumerate(slides):
        for ei, el in enumerate(slide.get('elements', [])):
            if el.get('type') == 'textbox':
                for para in el.get('content', []):
                    p = para.get('paragraph', para)
                    for run in p.get('runs', []):
                        font_size = run.get('font', {}).get('size')
                        if font_size is not None:
                            assert font_size >= 14, \
                                f"S{si+1} elem[{ei}] font size {font_size} < 14pt"

    # Verify SVG icons <= 0.79 inch
    for si, slide in enumerate(slides):
        for ei, el in enumerate(slide.get('elements', [])):
            if el.get('type') == 'picture' and 'name' in el:
                w = el['position'].get('width', 0)
                h = el['position'].get('height', 0) or 0
                assert w <= 0.79 and (h is None or h <= 0.79), \
                    f"S{si+1} elem[{ei}] icon size {w}x{h} exceeds 2cm limit"

    print(f"JSON validation PASSED: {len(slides)} slides, {total_elements} elements")

    # Generate PPTX
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, 'super_freedom_sample.pptx')

    instruction = {
        'meta': {'slide_width': 13.333, 'slide_height': 7.5, 'language': 'zh'},
        'slides': [
            {'layout': 'blank', 'background': s['background'],
             'notes': s['notes'], 'elements': s['elements']}
            for s in slides
        ],
    }

    async def run():
        result = await generate_ppt(instruction, out_path)
        assert result['ok'], f"PPTX generation failed: {result.get('errors', [])[:3]}"
        assert result['file_size'] > 10000, f"File too small: {result['file_size']} bytes"
        assert result['slide_count'] == 3
        print(f"PPTX generation PASSED: {result['file_size']/1024:.1f} KB, {result['slide_count']} slides")

    asyncio.run(run())


if __name__ == '__main__':
    test_load_and_generate()
