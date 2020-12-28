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

plan tests 31

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
# git
###################################################################################################

$stakesign prepare --git HEAD 2> >(tee stderr.log >&2)
is "$?" "1" "not git"
grep --silent "Not in git repository" stderr.log
is "$?" "0" "not git message"
git init
git config user.email "aphacker@mit.edu"
git config user.name "Alyssa P. Hacker"
git add LICENSE
git commit -m 'stakesign test'
git tag some-lightweight-tag
git tag -a -m 'stakesign test' some-annotated-tag

commit_prefix=$(echo `git rev-parse HEAD` | cut -c1-10)
$stakesign prepare --git --stake 0.66 HEAD "$commit_prefix" some-lightweight-tag some-annotated-tag | tee stdout.log
is "$?" "0" "succeed git refs"
grep --silent "$(git rev-parse HEAD)" stdout.log && grep --silent '"tag":"some-lightweight-tag"' stdout.log && grep --silent '"tag":"some-annotated-tag","tagObject":"' stdout.log
is "$?" "0" "resolve git refs"

git clone https://github.com/mlin/spVCF.git
git -C spVCF config user.email "aphacker@mit.edu"
git -C spVCF config user.name "Alyssa P. Hacker"
git -C spVCF checkout -b wip 5bb4229a162689516
$stakesign verify -C spVCF 0x248d9fac23ab037111c4bffdf25dd09f9dbdf1c34c6114365f0bdbe50294c483
is "$?" "0" "verify signed HEAD"
git -C spVCF checkout -b wip2 4ad2c2955c4ee2598
$stakesign verify -C spVCF 0x248d9fac23ab037111c4bffdf25dd09f9dbdf1c34c6114365f0bdbe50294c483 2> >(tee stderr.log >&2)
is "$?" "1" "reject unsigned HEAD"
grep --silent "Signature doesn't apply" stderr.log
is "$?" "0" "reject unsigned HEAD for correct reason"
git -C spVCF checkout 20201226
$stakesign verify -C spVCF 0x248d9fac23ab037111c4bffdf25dd09f9dbdf1c34c6114365f0bdbe50294c483
is "$?" "0" "verify lightweight tag"
git -C spVCF tag -d 20201226
$stakesign verify -C spVCF 0x248d9fac23ab037111c4bffdf25dd09f9dbdf1c34c6114365f0bdbe50294c483
is "$?" "0" "verify lightweight tag missing from local"
git -C spVCF tag 20201226 v1.1.0
$stakesign verify -C spVCF 0x248d9fac23ab037111c4bffdf25dd09f9dbdf1c34c6114365f0bdbe50294c483 2> >(tee stderr.log >&2)
is "$?" "1" "reject local tag referring to wrong commit"
grep --silent "refers to a different commit" stderr.log
is "$?" "0" "reject local tag for correct reason"
$stakesign verify -C spVCF 0x248d9fac23ab037111c4bffdf25dd09f9dbdf1c34c6114365f0bdbe50294c483 --git v1.0.0 | tee stdout.log
is "$?" "0" "verify annotated tag"
grep --silent 8851a121e5198d74eba19387628711d305d54e33 stdout.log
is "$?" "0" "verify annotated tag 2"
git -C spVCF checkout v1.0.0
git -C spVCF tag -d v1.0.0
$stakesign verify -C spVCF 0x248d9fac23ab037111c4bffdf25dd09f9dbdf1c34c6114365f0bdbe50294c483
is "$?" "0" "verify annotated tag missing from local"
git -C spVCF tag -a v1.0.0 8851a121e5198d74eba19387628711d305d54e33 -m 'gotcha'
$stakesign verify -C spVCF 0x248d9fac23ab037111c4bffdf25dd09f9dbdf1c34c6114365f0bdbe50294c483 2> >(tee stderr.log >&2)
is "$?" "1" "reject tag with right commit but different annotations"
grep --silent "differs from the signed tag in annotations" stderr.log
is "$?" "0" "reject local annotated tag for correct reason"

###################################################################################################
# cleanup
###################################################################################################

if (( KEEP_TMPDIR == 1 )); then
    echo "KEEP_TMPDIR ${TMPDIR}"
else
    rm -rf "$TMPDIR"
fi
