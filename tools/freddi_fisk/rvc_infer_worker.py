#!/usr/bin/env python3
"""Finish an offline RVC job without macOS OpenMP native-exit deadlocks."""

import os
import sys
import traceback


def main():
    status = 1
    try:
        from infer.cli import main as infer
        status = infer()
    except KeyboardInterrupt:
        status = 130
    except Exception:
        traceback.print_exc()
    # RVC has closed the audio output before infer() returns. Preserve its real
    # exit status and logs; skip only native library destructors on macOS.
    sys.stdout.flush()
    sys.stderr.flush()
    if sys.platform == "darwin":
        os._exit(status)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
