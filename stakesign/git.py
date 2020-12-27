import json
from pathlib import Path
from pygit2 import Repository, Commit, Reference, Tag  # pylint: disable=E0611


class ErrorMessage(Exception):
    pass


def error_if(cond, msg):
    if cond:
        raise ErrorMessage(msg) from None


def repository(cwd=None):
    # find containing git repo
    cwd = (Path(cwd) if cwd else Path.cwd()).resolve()
    while not (cwd / ".git").is_dir():
        cwd = (cwd / "..").resolve()
        error_if(cwd == Path(cwd.anchor), "Not in git repository")
    return str(cwd), Repository(cwd / ".git")


def prepare(repo, revisions):
    results = []
    warnings = []
    all_sha256 = True
    for revision in revisions:
        try:
            obj, ref = repo.revparse_ext(revision)
        except KeyError:
            error_if(True, f"Failed to `git rev-parse {revision}`")
        assert isinstance(obj, (Commit, Tag))
        assert not ref or isinstance(ref, Reference)
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
            assert False
        results.append(result)

    head_commit = repo.revparse_ext("HEAD")[0].hex
    if head_commit not in (res["commit"] for res in results):
        warnings.append(
            f"The revisions to sign don't include the current working tree HEAD = {head_commit}"
        )
    elif repo.status():
        warnings.append(
            "Working tree is dirty; signature will apply to clean commit HEAD = " + head_commit
        )

    if not all_sha256:
        warnings.append(
            "Preparing signature for git SHA-1 digest; review git SHA-1 security risks and consider adopting git SHA-256 mode"
        )
    return (
        "\n".join(json.dumps(res, separators=(",", ":")) for res in results).encode() + b"\n"
    ), warnings


def verify(repo, revision, sigbody):  # pylint: disable=R0912,R0915
    """
    Verify that signature body includes a valid signature of revision.
    """
    # resolve revision to commit hash
    try:
        obj_to_verify, _ = repo.revparse_ext(revision)
    except KeyError:
        error_if(True, f"Failed to `git rev-parse {revision}`")
    if isinstance(obj_to_verify, Commit):
        commit_to_verify = obj_to_verify.hex
    elif isinstance(obj_to_verify, Tag):
        commit_to_verify = obj_to_verify.target.hex
    else:
        assert False

    # check status of current checkout
    warnings = set()
    head_commit = repo.revparse_ext("HEAD")[0].hex
    if head_commit != commit_to_verify:
        warnings.add(
            f"Verified revision{revision} = {commit_to_verify} is not the working tree HEAD = {head_commit}"
        )
    elif repo.status():
        warnings.add(
            "Working tree is dirty; signature applies to clean commit HEAD = " + head_commit
        )

    verified = None
    all_sha256 = len(commit_to_verify) == 64

    # Look for signature of commit_to_verify
    # Warning about warning messages: sigbody comes off the blockchain, so we shouldn't include
    # anything from it in warning messages without validation (in case it is malicious)
    for line in sigbody.split(b"\n"):  # pylint: disable=R1702
        if not line:
            continue
        try:
            sig_elt = json.loads(line.decode())
            assert "commit" in sig_elt
        except:
            error_if(True, "Invalid signature syntax")
        if sig_elt["commit"] == commit_to_verify:
            if verified is None:
                verified = f"Verified: local revision {revision} = signed commit {commit_to_verify}"
            if "tag" in sig_elt:
                local_tag = None
                try:
                    local_tag = repo.revparse_ext(sig_elt["tag"])
                except KeyError:
                    warnings.add(
                        "The signature named a tag for this commit, but the tag is absent locally"
                    )
                    continue
                # Several cases to deal with here, as signed & local tags could each be either
                # lightweight or annotated
                if isinstance(local_tag[0], Commit):  # local lightweight tag
                    assert isinstance(local_tag[1], Reference)
                    error_if(
                        not local_tag[1].name.startswith("refs/tags/"),
                        "The signed tag refers locally to something else: " + local_tag[1].name,
                    )
                    error_if(
                        local_tag[0].hex != commit_to_verify,
                        f"The tag '{local_tag[1].shorthand}' refers locally to a different commit than the signed tag.",
                    )
                    if "tagObject" in sig_elt:
                        warnings.add(
                            f"The local tag '{local_tag[1].shorthand}' is lightweight, while the signed tag was annotated"
                        )
                    verified = f"Verified: local revision {revision} = signed tag {local_tag[1].shorthand} (commit {commit_to_verify})"
                elif isinstance(local_tag[0], Tag):  # local annotated tag
                    if "tagObject" in sig_elt:
                        error_if(
                            sig_elt["tagObject"] != local_tag[0].hex,
                            f"The local tag '{local_tag[0].name}' = {local_tag[0].hex} differs from the signed tag in annotations (although they share the same name and commit reference)",
                        )
                    else:
                        error_if(
                            local_tag[0].target.hex != commit_to_verify,
                            f"The local annotated tag '{local_tag[0].name}' = {local_tag[0].hex} refers to a different commit than the tag that was signed.",
                        )
                        warnings.add(
                            f"The local tag '{local_tag[1].shorthand}' is annotated, while the signed tag was lightweight"
                        )
                    verified = f"Verified: local revision {revision} = signed tag {local_tag[1].shorthand} (commit {commit_to_verify})"
                    all_sha256 = all_sha256 and len(local_tag[0].hex) == 64
                else:
                    assert False

    error_if(not verified, f"Signature doesn't apply to {revision} ({commit_to_verify})")
    if not all_sha256:
        warnings.add(
            "Signature pertains to git SHA-1 digest; review git SHA-1 security risks and consider adopting git SHA-256 mode"
        )
    return verified, warnings
