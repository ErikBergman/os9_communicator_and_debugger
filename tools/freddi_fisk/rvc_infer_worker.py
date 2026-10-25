#!/usr/bin/env python3
"""Finish an offline RVC job without macOS OpenMP native-exit deadlocks."""

import os
import sys
import traceback

# PyTorch and FAISS ship different OpenMP runtimes on this Mac. Keep their
# worker pools single-threaded for these short, interactive conversions.
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"


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
