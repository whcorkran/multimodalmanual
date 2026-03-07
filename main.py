"""Example usage of the manual_preprocessor pipeline."""

import json
import sys
from pathlib import Path

from manual_preprocessor import preprocess_manual


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python main.py <path-to-manual.pdf>       # process a local file")
        print('  python main.py "Bosch drill manual"        # search and download')
        sys.exit(1)

    source = sys.argv[1]
    product_name = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Processing: {source}")
    result = preprocess_manual(source, product_name=product_name)

    output = result.to_dict()
    output_path = Path("output.json")
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    print(f"\nProduct: {result.product_name}")
    print(f"Pages parsed: {len(result.pages)}")
    print(f"Steps extracted: {len(result.steps)}")
    print(f"Objects found: {result.objects}")
    print(f"\nOutput written to {output_path}")

    # Print first few steps as preview
    for step in result.steps[:5]:
        print(f"\n  Step {step.step_id}: {step.action} -> {step.target_object}")
        if step.tool:
            print(f"    Tool: {step.tool}")
        if step.parameters:
            print(f"    Params: {step.parameters}")
        print(f"    Raw: {step.raw_text[:80]}...")


if __name__ == "__main__":
    main()
