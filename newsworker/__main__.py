#!/usr/bin/env python
"""The main entry point.

"""
import sys


def main():
    try:
        from .core import cli

        exit_status = cli()
        sys.exit(exit_status if exit_status is not None else 0)
    except KeyboardInterrupt:
        print("\nCtrl-C pressed. Aborting")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
