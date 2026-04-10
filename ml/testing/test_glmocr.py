import argparse
import sys
from pathlib import Path

from glmocr import GlmOcr, parse


def main():
    parser = argparse.ArgumentParser(
        description="Parse an image using glmocr and output the result."
    )
    parser.add_argument(
        "image",
        help="Path to the input PNG/image file.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to save results to (optional).",
    )
    parser.add_argument(
        "--cpu-layout",
        action="store_true",
        help="Place the layout model on CPU instead of GPU.",
    )
    args = parser.parse_args()

    image_path = args.image
    if not Path(image_path).exists():
        print(f"Error: file not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    layout_device = "cpu" if args.cpu_layout else None

    kwargs = {}
    if layout_device:
        kwargs["layout_device"] = layout_device

    with GlmOcr(**kwargs) as ocr:
        result = ocr.parse(image_path)
        print(result.json_result)

        if args.output_dir:
            result.save(output_dir=args.output_dir)
            print(f"Results saved to: {args.output_dir}")


if __name__ == "__main__":
    main()
