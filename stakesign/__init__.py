import os
import sys
from argparse import ArgumentParser, Action
import importlib_metadata
from . import verify, prepare


def main():
    parser = ArgumentParser("stakesign")
    parser.add_argument(
        "--version",
        nargs=0,
        action=PipVersionAction,
        help="show package version information",
    )

    subparsers = parser.add_subparsers()
    subparsers.required = True
    subparsers.dest = "command"
    verify.cli_subparser(subparsers)
    prepare.cli_subparser(subparsers)

    replace_COLUMNS = os.environ.get("COLUMNS", None)
    os.environ["COLUMNS"] = "120"  # make help descriptions wider
    args = parser.parse_args(sys.argv[1:])
    if replace_COLUMNS is not None:
        os.environ["COLUMNS"] = replace_COLUMNS
    else:
        del os.environ["COLUMNS"]

    stakesign_version = "(version unknown)"
    try:
        stakesign_version = "v" + importlib_metadata.version("stakesign")
    except importlib_metadata.PackageNotFoundError:
        pass
    print(
        f"[NOTICE] stakesign {stakesign_version} is a prototype; don't trust in high-risk environments"
    )

    if args.command == "verify":
        verify.cli(args)
    elif args.command == "prepare":
        prepare.cli(args)
    else:
        assert False


class PipVersionAction(Action):
    def __call__(self, parser, namespace, values, option_string=None):
        from web3.auto import w3  # pylint: disable=C0415

        print(f"web3 v{w3.api}")
        try:
            print(f"stakesign v{importlib_metadata.version('stakesign')}")
        except importlib_metadata.PackageNotFoundError:
            print("stakesign version unknown")
        sys.exit(0)
