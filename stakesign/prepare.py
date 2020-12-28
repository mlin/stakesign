import sys
import json
import argparse
import platform
import subprocess
import shutil
from datetime import datetime, timedelta
import dateutil
import dateutil.parser
import dateutil.tz
import web3
from .verify import print_tsv, bail, yellow, color, ANSI


def prepare_sha256sum(files, sha256sum_exe, cwd=None, tee=False):
    "run sha256sum on files; prepare input body for signing transaction as bytes"
    # tee sha256sum stdout in realtime, to provide feedback whilst processing multiple large files
    proc = subprocess.Popen([sha256sum_exe] + files, stdout=subprocess.PIPE, cwd=cwd)
    sha256sum_stdout = []
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        sha256sum_stdout.append(line)  # includes newline
        if tee:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
    proc.wait()
    sys.stdout.flush()
    if proc.returncode != 0:
        raise Exception("sha256sum failed")

    return b"".join(sha256sum_stdout)


def cli_subparser(subparsers):
    parser = subparsers.add_parser(
        "prepare",
        help="prepare data for signature",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("FILE", nargs="+", help="filenames or other object identifiers")
    parser.add_argument(
        "--git",
        action="store_true",
        help="identifiers are git commits or tags in the current repository",
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="identifiers pertain to docker images from the local dockerd",
    )
    parser.add_argument(
        "--stake",
        metavar="0.1",
        dest="stake_ad",
        type=float,
        help="ETH stake to advertise/advise",
    )
    parser.add_argument(
        "--expire",
        metavar=f"'{datetime.utcnow()}Z'",
        help="declare signature expires at ISO 8601 date & time",
    )
    parser.add_argument(
        "--expire-days",
        metavar="N",
        type=int,
        help="declare signature expires N days from now",
    )
    parser.add_argument(
        "--chdir", "-C", metavar="DIR", type=str, help="change working directory to DIR"
    )
    return parser


def cli(args):  # pylint: disable=R0912,R0915
    if args.expire and args.expire_days:
        bail("set at most one of --expire-days and --expire")
    if args.docker and args.git:
        bail("set at most one of --git and --docker")
    if args.stake_ad is None:
        print(
            yellow(
                "[WARN] Are you sure you don't want to set the advisory --stake? This will leave it to verifiers to apply a default threshold.",
            )
        )

    expire_utc = None
    if args.expire:
        expire_utc = dateutil.parser.isoparse(args.expire).astimezone(dateutil.tz.tzutc())
    if args.expire_days is not None:
        expire_utc = datetime.utcnow() + timedelta(days=args.expire_days)
    if expire_utc is not None:
        expire_utc = expire_utc.replace(tzinfo=None)

    header = {"stakesign": "sha256sum"}
    if args.git:
        header["stakesign"] = "git"
    if args.docker:
        header["stakesign"] = "docker"
    if isinstance(expire_utc, datetime):
        header["expire"] = f"{expire_utc}Z"
    if isinstance(args.stake_ad, float):
        header["stakeAd"] = {"ETH": args.stake_ad}
    header = json.dumps(header, separators=(",", ":")) + "\n"

    if args.git:
        from .git import repository, prepare, ErrorMessage  # pylint: disable=C0415

        repo_dir, repo = repository(args.chdir)
        print_tsv("Trusting git repo:", repo_dir)

        try:
            body, warnings = prepare(repo, args.FILE)
        except ErrorMessage as err:
            bail(err.args[0])
        for warnmsg in warnings:
            print(yellow("[WARN] " + warnmsg))
        sys.stdout.flush()
        sys.stdout.buffer.write(header.encode())  # for payload preview
        sys.stdout.buffer.write(body)
    elif args.docker:
        from .docker import DEFAULT_HOST, prepare, ErrorMessage  # pylint: disable=C0415

        print_tsv("Trusting dockerd:", DEFAULT_HOST)
        try:
            body, warnings = prepare(DEFAULT_HOST, args.FILE)
        except ErrorMessage as err:
            bail(err.args[0])
        for warnmsg in warnings:
            print(yellow("[WARN] " + warnmsg))
        sys.stdout.flush()
        sys.stdout.buffer.write(header.encode())  # for payload preview
        sys.stdout.buffer.write(body)
    else:  # default sha256sum mode
        sha256sum_exe = shutil.which("sha256sum")
        if not sha256sum_exe:
            msg = "`sha256sum` utility unavailable; ensure coreutils is installed and PATH is configured"
            if platform.system() == "Darwin":
                msg += "\nOn macOS try: brew install coreutils"
            bail(msg)
        print_tsv("Trusting local exe:", sha256sum_exe)
        print()

        sys.stdout.write(header)  # for payload preview
        try:
            body = prepare_sha256sum(args.FILE, sha256sum_exe, cwd=args.chdir, tee=True)
        except:
            bail("`sha256sum` utility failed")

    print("\n-- Transaction input data for signing (one long line):\n")

    print(color(web3.Web3.toHex(header.encode() + body), ANSI.BOLD))
    print()
