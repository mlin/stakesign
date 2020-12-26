import json
import os
import sys
import argparse
import subprocess
import shutil
import tempfile
import math
from datetime import datetime, timedelta
import dateutil
import dateutil.tz
import dateutil.parser
import web3
from web3.datastructures import AttributeDict


DEFAULT_STAKE_FLOOR_ETH = 0.1


def get_sig(w3, txid):
    "Query blockchain for signature transaction details"
    tx = w3.eth.getTransaction(txid)
    txr = w3.eth.getTransactionReceipt(txid)
    blk = w3.eth.getBlock(tx.blockNumber)

    signer = txr["from"]
    assert tx["from"] == signer

    return AttributeDict(
        {
            "id": txid,
            "timestamp": datetime.utcfromtimestamp(blk.timestamp),
            "block": tx.blockNumber,
            "signer": signer,
            "input": tx.input,
        }
    )


def decode_sig_input(w3, sig):
    "Decode signature input data to header dict & body bytes"
    assert isinstance(sig.input, str) and sig.input.startswith("0x")
    buf = w3.toBytes(hexstr=sig.input)
    pos = buf.find(b"\n")
    pos = pos if pos >= 0 else len(pos)
    try:
        hdr = json.loads(buf[:pos])
        assert isinstance(hdr, dict)
        assert "stakesign" in hdr and isinstance(hdr["stakesign"], str)
    except:
        raise ValueError(
            "Transaction input isn't consistent with stakesign format; check transaction ID"
        ) from None
    bod = buf[(pos + 1) :]
    return (hdr, bod)


def check_sig_expire(header, utcnow):
    assert isinstance(utcnow, datetime)
    expire = None
    if "expire" in header:
        try:
            assert isinstance(header["expire"], str)
            expire = (
                dateutil.parser.isoparse(header["expire"])
                .astimezone(dateutil.tz.tzutc())
                .replace(tzinfo=None)
            )
        except:
            raise ValueError(
                "Transaction header.expire has invalid value (expected ISO 8601)"
            ) from None
    return AttributeDict(
        {
            "unexpired": expire and expire > utcnow,
            "expire_utc": expire,
            "now_utc": utcnow,
        }
    )


def check_sig_stake(w3, sig, header, stake_floor_wei, ignore_ad=False):
    "Check whether the signing address has sufficient current ETH balance"
    assert isinstance(header, dict)
    assert isinstance(stake_floor_wei, int)

    signer_wei = w3.eth.getBalance(sig.signer)
    assert isinstance(signer_wei, int)

    required_wei = stake_floor_wei
    required_wei_source = "--stake"
    if not ignore_ad and "stakeAd" in header:
        stake_ad = header["stakeAd"]
        if not isinstance(stake_ad, dict):
            raise ValueError("Transaction header.stakeAd has invalid value")
        if "ETH" in stake_ad:
            stake_ad = stake_ad["ETH"]
            if not (isinstance(stake_ad, float) and math.isfinite(stake_ad)):
                raise ValueError("Transaction header.stakeAd has invalid ETH value")
            stake_ad = w3.toWei(stake_ad, "ether")
            if stake_ad > required_wei:
                required_wei = stake_ad
                required_wei_source = "stakeAd"
        else:
            print(color("[WARN] Transaction header.stakeAd doesn't specify ETH value", ANSI.BHYEL))

    return AttributeDict(
        {
            "enough": signer_wei >= required_wei,
            "signer_wei": signer_wei,
            "required_wei": required_wei,
            "required_wei_source": required_wei_source,
        }
    )


def verify_sha256sum(header, body, exe, ignore_missing=False, no_strict=False):
    "run given sha256sum executable to verify signature body"
    assert header["stakesign"] == "sha256sum"
    assert isinstance(body, bytes)

    cmd = [exe, "--check"]
    if not no_strict:
        cmd.append("--strict")
    if ignore_missing:
        cmd.append("--ignore-missing")

    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(body)
        tmp.flush()
        cmd.append(tmp.name)
        res = subprocess.run(cmd, check=False)

    return res.returncode == 0


def cli_subparser(subparsers):
    parser = subparsers.add_parser(
        "verify",
        help="verify existing signature(s)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("signature", help="signature Transaction ID (0x...)")
    parser.add_argument(
        "--stake",
        metavar="0.1",
        dest="stake_floor_eth",
        type=float,
        default=DEFAULT_STAKE_FLOOR_ETH,
        help="minimum acceptable current ETH balance for signer address",
    )
    parser.add_argument(
        "--ignore-ad",
        action="store_true",
        help="use --stake value even if less than signature's stakeAd",
    )
    parser.add_argument(
        "--ignore-missing",
        action="store_true",
        help="pass --ignore-missing to sha256sum, if applicable",
    )
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="do not pass --strict to sha256sum (use only if yours doesn't provide this option)",
    )
    parser.add_argument(
        "--expired-ok",
        action="store_true",
        help="proceed even if signature's stated expiration date has passed",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="display transaction input UTF-8 payload after success",
    )
    return parser


def cli(args):  # pylint: disable=R0912
    provider_msg = "(from environment WEB3_PROVIDER_URI)"
    if "WEB3_PROVIDER_URI" not in os.environ:
        os.environ["WEB3_PROVIDER_URI"] = "https://cloudflare-eth.com"
        provider_msg = "(to override, set environment WEB3_PROVIDER_URI)"

    print("\t".join(("Trusting ETH gateway:", os.environ["WEB3_PROVIDER_URI"], provider_msg)))
    from web3.auto import w3

    # get transaction info
    if not args.signature.startswith("0x"):
        bail("Transaction ID should start with 0x")
    try:
        sig = get_sig(w3, args.signature)
    except web3.exceptions.TransactionNotFound:
        bail("Transaction and/or receipt not found on Ethereum network")

    utcnow = datetime.utcnow().replace(tzinfo=None)
    sig_age = utcnow - sig.timestamp
    print_tsv("         Transaction:", sig.id)
    print_tsv("    Signer's address:", sig.signer)
    print_tsv(
        " Signature timestamp:",
        f"{sig.timestamp}Z",
        yellow(f"({sig_age} ago)", sig_age < timedelta(days=3)),
    )

    # decode signature, check expiration date
    header, body = decode_sig_input(w3, sig)
    exinfo = check_sig_expire(header, utcnow)
    if exinfo.expire_utc is not None:
        print_tsv(
            "Signature expiration:",
            f"{exinfo.expire_utc}Z",
            f"{color('🗹', ANSI.BHGRN) if exinfo.unexpired else color('✗', ANSI.BHRED)}",
        )
        if not (args.expired_ok or exinfo.unexpired):
            bail("Signature's stated expiration date has passed")

    # check stake
    vs = check_sig_stake(
        w3,
        sig,
        header,
        w3.toWei(args.stake_floor_eth, "ether"),
        ignore_ad=args.ignore_ad,
    )
    print_tsv(
        "Signer's balance now:",
        f"{w3.fromWei(vs.signer_wei, 'ether')}",
        f"{'≥' if vs.enough else '<'} {w3.fromWei(vs.required_wei, 'ether')} ETH from {vs.required_wei_source}",
        f"{color('🗹', ANSI.BHGRN) if vs.enough else color('✗', ANSI.BHRED)}",
    )
    if not vs.enough:
        msg = "Signer's address holds insufficient ETH balance, possibly indicating revocation or compromise!"
        if vs.required_wei_source == "--stake":
            msg += f"\n        If you're certain this address is trustworthy, rerun with --stake {w3.fromWei(vs.signer_wei, 'ether')}"
        bail(msg)

    # verify, per mode
    mode = header["stakesign"]
    if mode == "sha256sum":
        sha256sum_exe = shutil.which("sha256sum")
        if not sha256sum_exe:
            bail(
                "`sha256sum` utility unavailable; ensure coreutils is installed and PATH is configured"
            )
        print_tsv("  Trusting local exe:", sha256sum_exe)
        print()
        if not verify_sha256sum(
            header,
            body,
            sha256sum_exe,
            ignore_missing=args.ignore_missing,
            no_strict=args.no_strict,
        ):
            bail("sha256sum verification failed!")
    else:
        bail(
            "Signing mode not one of {sha256sum}. A newer version of this utility might support the necessary mode."
        )

    print_tsv("\n" + color("🗹", ANSI.BHGRN), "Success")

    if math.fabs(args.stake_floor_eth - DEFAULT_STAKE_FLOOR_ETH) < (DEFAULT_STAKE_FLOOR_ETH / 1000):
        print(
            color(
                f"[WARN] Ensure the signer's current {w3.fromWei(vs.signer_wei, 'ether')} ETH stake evinces their ongoing interest in securing it.\n"
                + f"       Consider setting --stake above the default {DEFAULT_STAKE_FLOOR_ETH} ETH depending on the publisher.",
                ANSI.BHYEL,
            )
        )

    if args.verbose:
        print()
        print(w3.toBytes(hexstr=sig.input).decode("utf-8").rstrip("\n"))


def print_tsv(*args, **kwargs):
    print("\t".join(str(arg) for arg in args), **kwargs)


def bail(msg):
    msg = "[ERROR] " + msg
    if sys.stderr.isatty() and "NO_COLOR" not in os.environ:
        print(ANSI.BHRED + msg + ANSI.RESET, file=sys.stderr)
    else:
        print(msg, file=sys.stderr)
    sys.exit(1)


def color(msg, col):
    if sys.stdout.isatty() and "NO_COLOR" not in os.environ:
        return col + msg + ANSI.RESET
    return msg


def yellow(msg, only_if=True):
    return color(msg, ANSI.BHYEL) if only_if else msg


class ANSI:
    # https://gist.github.com/RabaDabaDoba/145049536f815903c79944599c6f952a
    # https://espterm.github.io/docs/VT100%20escape%20codes.html
    RESET = "\x1b[0m"
    BHRED = "\x1b[1;91m"
    BHYEL = "\x1b[1;93m"
    BHGRN = "\x1b[1;92m"
