#!/usr/bin/env python3
"""Small path helpers shared by the Steam mapping boundary."""

import argparse
import os
import sys


def relative_path(base, target):
    """Return a Steam-compatible slash-separated path from base to target."""
    return os.path.relpath(os.path.abspath(target), os.path.abspath(base)).replace(
        os.sep, "/"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("relative",))
    parser.add_argument("base")
    parser.add_argument("target")
    args = parser.parse_args()
    if args.operation == "relative":
        print(relative_path(args.base, args.target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
