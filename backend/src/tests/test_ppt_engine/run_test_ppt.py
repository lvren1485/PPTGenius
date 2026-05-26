"""Quick test script to generate test PPT."""
import asyncio, json, sys, os

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(backend_dir, "src"))

from pptgenius.infrastructure.ppt_engine.generator import generate_ppt


async def main():
    test_json = os.path.join(os.path.dirname(__file__), "test_all_elements.json")
    output = os.path.join(backend_dir, "data", "test_output", "test_output.pptx")

    print("Loading:", test_json)
    with open(test_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("Generating PPT...")
    result = await generate_ppt(data, output, backend_dir)

    if result["ok"]:
        print(f"Done: {result}")
    else:
        print("FAILED:")
        for err in result["errors"]:
            print(f"  {err['path']}: {err['error']}")


if __name__ == "__main__":
    asyncio.run(main())
