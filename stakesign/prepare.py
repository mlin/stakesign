import json
import sys
import argparse
import subprocess
import shutil
from datetime import datetime, timedelta
import dateutil
import dateutil.parser
import dateutil.tz
import web3
from .verify import print_tsv, bail, color, ANSI


def prepare_sha256sum(files, sha256sum_exe):
    "run sha256sum on files; prepare input body for signing transaction as bytes"
    # tee sha256sum stdout in realtime, to provide feedback whilst processing multiple large files
    proc = subprocess.Popen([sha256sum_exe] + files, stdout=subprocess.PIPE)
    sha256sum_stdout = []
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        sha256sum_stdout.append(line)  # includes newline
        sys.stdout.flush()
        sys.stdout.buffer.write(line)
    proc.wait()
    if proc.returncode != 0:
        raise Exception("sha256sum failed")

    return b"".join(sha256sum_stdout)


def cli_subparser(subparsers):
    parser = subparsers.add_parser(
        "prepare",
        help="prepare data for signature",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("FILE", nargs="+", help="filenames (or other object identifiers)")
    parser.add_argument(
        "--stake",
        metavar="0.1",
        dest="stake_ad",
        type=float,
        default=None,
        help="ETH stake to advertise/advise",
    )
    parser.add_argument(
        "--expire",
        metavar=f"'{datetime.utcnow()}Z'",
        default=None,
        help="declare signature expires at ISO 8601 date & time",
    )
    parser.add_argument(
        "--expire-days",
        metavar="N",
        type=int,
        default=None,
        help="declare signature expires N days from now",
    )
    return parser


def cli(args):
    if args.expire and args.expire_days:
        bail("set one of --expire-days and --expire")
    if args.stake_ad is None:
        print(
            color(
                "[WARN] Are you sure you don't want to set the advisory --stake? The signature's validity will be totally up to each verifier's defaults.",
                ANSI.BHYEL,
            )
        )

    expire_utc = None
    if args.expire:
        expire_utc = dateutil.parser.isoparse(args.expire).astimezone(dateutil.tz.tzutc())
    if args.expire_days is not None:
        expire_utc = datetime.utcnow() + timedelta(days=args.expire_days)
    if expire_utc is not None:
        expire_utc = expire_utc.replace(tzinfo=None)

    sha256sum_exe = shutil.which("sha256sum")
    if not sha256sum_exe:
        bail(
            "`sha256sum` utility unavailable; ensure coreutils is installed and PATH is configured"
        )
    print_tsv("Trusting local exe:", sha256sum_exe)
    print()

    header = {"stakesign": "sha256sum"}
    if isinstance(expire_utc, datetime):
        header["expire"] = f"{expire_utc}Z"
    if isinstance(args.stake_ad, float):
        header["stakeAd"] = {"ETH": args.stake_ad}
    header = json.dumps(header, separators=(",", ":")) + "\n"
    sys.stdout.write(header)  # for payload preview

    try:
        body = prepare_sha256sum(args.FILE, sha256sum_exe)
    except:
        bail("`sha256sum` utility failed")

    print("\n-- Transaction input data for signing (one long line):\n")

    print(web3.Web3.toHex(header.encode() + body))
    print()
