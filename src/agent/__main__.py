import sys
import argparse

from . import __app_name__, __version__
from .config import config


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

    # TODO: Route to orchestrator in later commits
    print(f"{__app_name__} v{__version__}")
    print(f"Topic: {args.topic}")
    print(f"Session ID: {args.session_id or '(will be generated)'}")
    print("Orchestrator not yet implemented — this is a stub.")


if __name__ == "__main__":
    main()
