# stakesign: git & docker modes

### Signing git commits & tags

The `stakesign` tool can sign and verify git commits & tags instead of the default file sha256sum mode. To verify a git signature, just run `stakesign verify 0xSIG_TXN_ID` in your local repository, e.g.

```
$ git clone --branch v1.1.0 https://github.com/mlin/spVCF.git && cd spVCF
$ stakesign verify 0x248d9fac23ab037111c4bffdf25dd09f9dbdf1c34c6114365f0bdbe50294c483
```

This checks whether the transaction signs the working tree HEAD; or specify `--git R` to check a different local revision R.

To prepare signature payloads for commits or tags,

```
$ stakesign prepare --stake 0.42 --git R [R ...]
```

Where R is `HEAD` to sign the current working tree, or a commit digest, tag, or anything else understood by `git rev-parse`. You can cover multiple commits and tags in one signature. As with sha256sum mode, send the prepared hex string in an Ethereum transaction and share the transaction ID as the signature.

**git signature security:** the signatures cover git commit digests, tag names, and (for annotated tags) tag object digests; these are assumed to be correct in the local repository as read by [pygit2](https://github.com/libgit2/pygit2). If your repository doesn't use [git's new SHA-256 object format](https://github.blog/2020-10-19-git-2-29-released/), the tool accepts older SHA-1 digests with warnings during both signing and verification. [Practical risks from SHA-1](https://git-scm.com/docs/hash-function-transition/) are low, as git now (since mid-2017) includes mitigations for known vulnerabilities; therefore, we've kept the signature approach simple, knowing that SHA-256 mode is on the way. Example [payload from the signature used above](https://etherscan.io/tx/0x248d9fac23ab037111c4bffdf25dd09f9dbdf1c34c6114365f0bdbe50294c483):

```json
{"stakesign":"git","stakeAd":{"ETH":1.0}}
{"commit":"8851a121e5198d74eba19387628711d305d54e33","tag":"v1.0.0","tagObject":"5cfd7b363843ea6c208673b2b535a69327f2a62f"}
{"commit":"05ddde6842b9a59a01b490b1926ae19cb8c679bf","tag":"v1.1.0","tagObject":"0b3568bd20328ffe998a4f4b4e29e5e30418ce87"}
{"commit":"46e1bcbbb467594aed9b9d4c11822da6b0abead5","tag":"20201226"}
{"commit":"5bb4229a1626895166ba03c5b6c14f3a96352dd1"}
```

### Signing Docker images

To verify Docker image(s) you've pulled locally, e.g.

```
$ docker pull quay.io/mlin/glnexus:v1.2.5 && docker pull quay.io/mlin/glnexus:v1.2.6
$ stakesign verify 0xd071c0e8fbcbcab8b92f9098c5250d7e1c003f222c94fe0729669bae02ae3acf
```

This reports all local images covered by the signature; specify `--docker I` to focus on one local image (I = ID, digest, or tag).

To prepare signature payloads for local image(s),

```
$ stakesign prepare --stake 0.42 --docker I [I ...]
```

As with sha256sum mode, send the prepared hex string in an Ethereum transaction and share the transaction ID as the signature. The signature for each image covers its *image ID*, which is a [SHA-256 digest based on the image's configuration and filesystem](https://windsock.io/explaining-docker-image-ids/). Given the signed image ID, the tool trusts your local Docker daemon to [verify it's consistent with the pulled image content](https://github.com/moby/moby/blob/9f72510b699379abbcb756f92ffa8a2d440d3be9/distribution/pull_v2.go#L896-L915).

Beware that the *image ID* differs from the *Repo Digest* used to pull from a registry; they're easy to confuse because they both use SHA-256 hex digests (even Docker's own docs & tools don't always distinguish them clearly). The same *image ID* may have multiple *Repo Digests*, if pushed to different registries or pushed to the same registry after deleting an earlier copy. The stakesign signature includes repo digests and tags known at the time of signing, but only the image ID is 1:1 with the image content.
