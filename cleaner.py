#!/usr/bin/env python3
"""Main entry point for the Gmail Cleaner cron job."""

import sys
import argparse
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import validate_config, DRY_RUN
from src.database import Database
from src.gmail_client import GmailClient
from src.rules_engine import RulesEngine
from src.email_report import send_report


def main():
    parser = argparse.ArgumentParser(description="Gmail Cleaner Bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making any changes"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test Gmail connection only"
    )
    args = parser.parse_args()

    # Validate config
    errors = validate_config()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    # Initialize components
    db = Database()
    gmail = GmailClient()

    # Test connection if requested
    if args.test:
        success, message = gmail.test_connection()
        print(message)
        sys.exit(0 if success else 1)

    # Override DRY_RUN if specified via CLI
    if args.dry_run:
        import src.config
        src.config.DRY_RUN = True
        print("Running in DRY RUN mode - no changes will be made")

    # Run the cleaner
    start_time = time.time()
    engine = RulesEngine(db, gmail)
    stats = engine.run_all_rules()
    duration_seconds = time.time() - start_time

    # Format duration
    minutes, seconds = divmod(int(duration_seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        duration_str = f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        duration_str = f"{minutes}m {seconds}s"
    else:
        duration_str = f"{seconds}s"

    # Print summary
    print(f"\nCleanup Summary:")
    print(f"  Rules processed: {stats['rules_processed']}")
    print(f"  Messages matched: {stats['matched']}")
    print(f"  Actions successful: {stats['success']}")
    print(f"  Actions failed: {stats['failed']}")
    print(f"  Duration: {duration_str}")

    # Send email report
    if send_report(stats, duration=duration_str):
        print("  Email report sent")


if __name__ == "__main__":
    main()
