import argparse

from . import __app_name__, __version__
from .config import config
from .agents.orchestrator import Orchestrator


def main():
    """Entry point for the pptgenius CLI."""
    parser = argparse.ArgumentParser(
        prog=__app_name__,
        description="AI-powered PPT generation agent",
    )
    parser.add_argument(
        "topic",
        type=str,
        help="Topic for the presentation",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Session ID for multi-turn conversations (auto-generated if omitted)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for generated PPT (default: ./output)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()

    # Ensure directories exist
    config.ensure_dirs()

    # Override output dir if specified
    if args.output_dir:
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Run orchestrator
    orchestrator = Orchestrator()
    result = orchestrator.run(
        topic=args.topic,
        session_id=args.session_id,
    )

    if result.get("error"):
        print(f"Error: {result['error']}")
        exit(1)

    print(f"\nDone! Session: {result['session_id']}")
    print(f"Report: {result.get('report_path', 'N/A')}")


if __name__ == "__main__":
    main()
