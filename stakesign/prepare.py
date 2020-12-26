import sys
import json
import argparse
import subprocess
import shutil
from datetime import datetime, timedelta
import dateutil
import dateutil.parser
import dateutil.tz
import web3
from .verify import print_tsv, bail, yellow


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
            sys.stdout.flush()
            sys.stdout.buffer.write(line)
    proc.wait()
    sys.stdout.flush()
    if proc.returncode != 0:
        raise Exception("sha256sum failed")

    return b"".join(sha256sum_stdout)


def prepare_git(objects, cwd=None):
    from pygit2 import Repository, Commit, Reference, Tag  # pylint: disable=E0611,C0415
    from pathlib import Path  # pylint: disable=C0415

    # find containing git repo
    cwd = Path(cwd) if cwd else Path.cwd()
    while not (cwd / ".git").is_dir():
        cwd = (cwd / "..").resolve()
        assert cwd != Path(cwd.anchor), "Not in git repository"
    repo = Repository(cwd / ".git")

    results = []
    all_sha256 = True
    for obj_id in objects:
        try:
            obj, ref = repo.revparse_ext(obj_id)
        except KeyError:
            assert False, "Failed to git rev-parse " + obj_id
        assert isinstance(obj, (Commit, Tag))
        assert not ref or isinstance(ref, Reference), "expected Reference, not " + str(ref)
        result = {}
        if isinstance(obj, Commit):
            result["commit"] = obj.hex
            all_sha256 = all_sha256 and len(obj.hex) == 64
            if ref and ref.name.startswith("refs/tags/"):  # lightweight tag
                result["tag"] = ref.name[10:]
        elif isinstance(obj, Tag):  # annotated tag
            result["commit"] = obj.target.hex
            result["tag"] = obj.name
            result["tagObject"] = obj.hex
            all_sha256 = all_sha256 and len(obj.target.hex) == 64 and len(obj.hex) == 64
        else:
            assert False, "expected Commit/Tag, not " + str(obj)
        results.append(result)

    return (
        "\n".join(json.dumps(res, separators=(",", ":")) for res in results).encode() + b"\n"
    ), all_sha256


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


def cli(args):  # pylint: disable=R0912
    if args.expire and args.expire_days:
        bail("set one of --expire-days and --expire")
    if args.stake_ad is None:
        print(
            yellow(
                "[WARN] Are you sure you don't want to set the advisory --stake? The signature's validity will be totally up to each verifier's defaults.",
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
    if isinstance(expire_utc, datetime):
        header["expire"] = f"{expire_utc}Z"
    if isinstance(args.stake_ad, float):
        header["stakeAd"] = {"ETH": args.stake_ad}
    header = json.dumps(header, separators=(",", ":")) + "\n"

    if args.git:
        try:
            body, all_sha256 = prepare_git(args.FILE, cwd=args.chdir)
        except AssertionError as err:
            bail(err.args[0])
        if not all_sha256:
            print(
                yellow(
                    "[WARN] Preparing to sign git SHA-1 digests; review git SHA-1 security risks and consider `git init --object-format=sha256`"
                )
            )
        sys.stdout.write(header)  # for payload preview
        sys.stdout.buffer.write(body)
        sys.stdout.flush()
    else:  # default sha256sum mode
        sha256sum_exe = shutil.which("sha256sum")
        if not sha256sum_exe:
            bail(
                "`sha256sum` utility unavailable; ensure coreutils is installed and PATH is configured"
            )
        print_tsv("Trusting local exe:", sha256sum_exe)
        print()

        sys.stdout.write(header)  # for payload preview
        try:
            body = prepare_sha256sum(args.FILE, sha256sum_exe, cwd=args.chdir, tee=True)
        except:
            bail("`sha256sum` utility failed")

    print("\n-- Transaction input data for signing (one long line):\n")

    print(web3.Web3.toHex(header.encode() + body))
    print()
