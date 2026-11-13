#!/usr/bin/env python3
"""Traffic driver for SLO Lab.

Sends synthetic traffic at the sample service for a short run, so
the dashboard panels and burn rates move in seconds instead of
hours. Most requests go to /work, a few go to /, and an optional
error rate is applied through the /chaos endpoint for the length
of the run, then reset to zero.

Examples:
  python3 scripts/drive.py
  python3 scripts/drive.py --seconds 60 --rate 30
  python3 scripts/drive.py --seconds 45 --error-rate 0.4
"""

import argparse
import time
import urllib.request


def call(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except Exception:
        return 0


def main():
    parser = argparse.ArgumentParser(description="Drive synthetic traffic at the SLO Lab sample service.")
    parser.add_argument("--base", default="http://localhost:3080", help="base URL of the app (default http://localhost:3080)")
    parser.add_argument("--seconds", type=float, default=30, help="how long to run (default 30)")
    parser.add_argument("--rate", type=float, default=20, help="requests per second (default 20)")
    parser.add_argument("--error-rate", type=float, default=0.0, help="failure probability for /work during the run (default 0)")
    args = parser.parse_args()

    if args.error_rate > 0:
        call(args.base, f"/chaos?error_rate={args.error_rate}")
        print(f"chaos set: /work error_rate={args.error_rate}")

    counts = {}
    total = int(args.seconds * args.rate)
    interval = 1.0 / args.rate
    started = time.time()
    try:
        for i in range(total):
            # About one request in eight goes to the hello endpoint,
            # the rest do work.
            path = "/" if i % 8 == 7 else "/work"
            tick = time.time()
            status = call(args.base, path)
            counts[status] = counts.get(status, 0) + 1
            # Pace against the request time so the run lasts about
            # as long as asked, instead of interval plus latency.
            time.sleep(max(0.0, interval - (time.time() - tick)))
    finally:
        if args.error_rate > 0:
            call(args.base, "/chaos?error_rate=0")
            print("chaos reset: error_rate=0")

    elapsed = time.time() - started
    print(f"sent {sum(counts.values())} requests in {elapsed:.1f}s, by status: {counts}")


if __name__ == "__main__":
    main()
