#!/bin/bash

set -o pipefail
export LC_ALL=C

cd "$(dirname "$0")/.."
REPO="$(pwd)"
export BASH_TAP_ROOT="${REPO}/test/bash-tap"
source "${REPO}/test/bash-tap/bash-tap-bootstrap"
export PYTHONPATH="${REPO}:${PYTHONPATH}"
stakesign="python3 -m stakesign"

export TMPDIR=$(mktemp -d -t stakesign-test-XXXXXX)
cd "$TMPDIR"

plan tests 15

###################################################################################################
# stakesign verify
###################################################################################################

cp "${REPO}/LICENSE" .
$stakesign verify 0xd071c0e8fbcbcab8b92f9098c5250d7e1c003f222c94fe0729669bae02ae3acf
is "$?" 0 "verify LICENSE"

WEB3_PROVIDER_URI=https://main-rpc.linkpool.io/ $stakesign verify 0xd071c0e8fbcbcab8b92f9098c5250d7e1c003f222c94fe0729669bae02ae3acf | tee stdout.log
is "$?" 0 "WEB3_PROVIDER_URI override succeeded"
grep --silent linkpool stdout.log
is "$?" 0 "WEB3_PROVIDER_URI override effective"

$stakesign verify 0xd071c0e8fbcbcab8b92f9098c5250d7e1c003f222c94fe0729669bae02ae3acf --stake 99 2> >(tee stderr.log >&2)
is "$?" 1 "reject higher stake"
grep --silent "insufficient ETH balance" stderr.log
is "$?" 0 "reject higher stake reason"

echo 42 >> LICENSE
$stakesign verify 0xd071c0e8fbcbcab8b92f9098c5250d7e1c003f222c94fe0729669bae02ae3acf 2> >(tee stderr.log >&2)
is "$?" 1 "reject tampered LICENSE"
grep --silent "sha256sum verification failed" stderr.log
is "$?" 0 "reject tampered LICENSE reason"

rm LICENSE
$stakesign verify 0xd071c0e8fbcbcab8b92f9098c5250d7e1c003f222c94fe0729669bae02ae3acf | tee stdout.log
is "$?" 1 "reject missing LICENSE"
grep --silent "LICENSE: FAILED" stdout.log
is "$?" 0 "reject tampered LICENSE reason"

$stakesign verify 0xd071c0e8fbcbcab8b92f9098c5250d7e1c003f222c94fe0729669bae02ae3acf --ignore-missing 2> >(tee stderr.log >&2)
is "$?" 1 "sha256sum --ignore-missing fails if no file was verified"
grep --silent "no file was verified" stderr.log
is "$?" 0 "'no file was verified' message"

###################################################################################################
# stakesign prepare
###################################################################################################

cp "${REPO}/LICENSE" .
$stakesign prepare LICENSE | tee stdout.log
is "$?" "0" "prepare LICENSE"
grep --silent "0x7b227374616b657369676e223a2273686132353673756d227d0a3266393161366633336634663264373265643463643663333633663165373263646464373236623464333563326166333533353666323536613534653735613020204c4943454e53450a" stdout.log
is "$?" "0" "prepare LICENSE correctly"

$stakesign prepare LICENSE --stake 99.00 --expire '2038-01-19 03:14:08+00' | tee stdout.log
is "$?" "0" "prepare LICENSE with options"
grep --silent "0x7b227374616b657369676e223a2273686132353673756d222c22657870697265223a22323033382d30312d31392030333a31343a30385a222c227374616b654164223a7b22455448223a39392e307d7d0a3266393161366633336634663264373265643463643663333633663165373263646464373236623464333563326166333533353666323536613534653735613020204c4943454e53450a" stdout.log
is "$?" "0" "prepare LICENSE with options correctly"

###################################################################################################
# cleanup
###################################################################################################

if (( KEEP_TMPDIR == 1 )); then
    echo "KEEP_TMPDIR ${TMPDIR}"
else
    rm -rf "$TMPDIR"
fi
