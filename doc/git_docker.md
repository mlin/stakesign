# Signing git commits & tags with stakesign

The `stakesign` tool can sign and verify git commits & tags instead of the default file sha256sum mode. To verify a git signature, just run `stakesign verify 0xSIG_TXN_ID` in your local repository, e.g.

```
$ git clone --branch v1.1.0 https://github.com/mlin/spVCF.git && cd spVCF
$ stakesign verify 0x248d9fac23ab037111c4bffdf25dd09f9dbdf1c34c6114365f0bdbe50294c483
```

This checks whether the transaction signs the working tree HEAD; or specify `--git-revision R` to check a different local revision R.

To prepare signature payloads for commits or tags,

```
$ stakesign prepare --stake 0.42 --git R [R ...]
```

Where R is `HEAD` to sign the current working tree, or a commit digest, tag, or anything else understood by `git rev-parse`. You can cover multiple commits and tags in one signature. As with sha256sum mode, send the prepared hex string in an Etherum transaction and share the transaction ID.

The signatures apply to git commit digests. If your repository doesn't use [git's new SHA-256 object format](https://github.blog/2020-10-19-git-2-29-released/), the tool accepts older SHA-1 digests with warnings during signing and verification. [Practical risks from SHA-1](https://git-scm.com/docs/hash-function-transition/) are small, as git now (since mid-2017) includes mitigations for known vulnerabilities; therefore, we've kept the signature approach simple, knowing SHA-256 mode is on the way.
