#!/bin/bash

set -o pipefail
export LC_ALL=C

cd "$(dirname "$0")/.."
REPO="$(pwd)"
export BASH_TAP_ROOT="${REPO}/test/bash-tap"
source "${REPO}/test/bash-tap/bash-tap-bootstrap"
export PYTHONPATH="${REPO}:${PYTHONPATH}"
stakesign="python3 -m stakesign"

export TMPDIR=$(mktemp -d -t stakesign-docker-test-XXXXXX)
cd "$TMPDIR"

plan tests 11

###################################################################################################
# stakesign docker image signing (separate from cli.t because GitHub Actions macOS doesn't docker)
###################################################################################################

docker rmi -f quay.io/mlin/glnexus:v1.2.5 
docker rmi -f quay.io/mlin/glnexus:v1.2.6
docker rmi -f stakesign_test_tag
$stakesign verify 0x406017fc96f8de18256429a5907de528b6fefebd9a4898b5b37a519300b2e1d7 --stake 1.0 --ignore-missing
is "$?" "1" "fail with nothing to verify"

docker pull quay.io/mlin/glnexus:v1.2.5
is "$?" "0" "pull image 1"

$stakesign verify 0x406017fc96f8de18256429a5907de528b6fefebd9a4898b5b37a519300b2e1d7 --stake 1.0 --ignore-missing
is "$?" "0" "verify image 1"

$stakesign verify 0x406017fc96f8de18256429a5907de528b6fefebd9a4898b5b37a519300b2e1d7 --stake 1.0
is "$?" "1" "fail with only image 1 to verify"

docker pull quay.io/mlin/glnexus:v1.2.6
is "$?" "0" "pull image 2"
$stakesign verify 0x406017fc96f8de18256429a5907de528b6fefebd9a4898b5b37a519300b2e1d7 --stake 1.0
is "$?" "0" "verify images 1&2"

docker tag quay.io/mlin/glnexus:v1.2.6 stakesign_test_tag
docker rmi quay.io/mlin/glnexus:v1.2.6
$stakesign verify 0x406017fc96f8de18256429a5907de528b6fefebd9a4898b5b37a519300b2e1d7 --stake 1.0 --docker quay.io/mlin/glnexus:v1.2.5
is "$?" "0" "verify image 1 only"

$stakesign verify 0x406017fc96f8de18256429a5907de528b6fefebd9a4898b5b37a519300b2e1d7 --stake 1.0 | tee stdout.log
is "$?" 0 "verify image with different local tag"
grep --silent "under different tag" stdout.log
is "$?" 0 "verify image with different local tag but complain"
docker rmi stakesign_test_tag

docker tag quay.io/mlin/glnexus:v1.2.5 quay.io/mlin/glnexus:v1.2.6

$stakesign verify 0x406017fc96f8de18256429a5907de528b6fefebd9a4898b5b37a519300b2e1d7 --stake 1.0 --ignore-missing 2> >(tee stderr.log >&2)
is "$?" 1 "reject tag referring to wrong image"
grep --silent "refers to a different image" stderr.log
is "$?" 0 "reject tag referring to wrong image for correct reason"
