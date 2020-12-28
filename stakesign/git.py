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
    elif dirty(repo):
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


def verify(repo, revision, sigbody, ignore_missing=False):  # pylint: disable=R0912,R0915
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
    elif dirty(repo):
        warnings.add(
            "Working tree is dirty; signature applies to clean commit HEAD = " + head_commit
        )

    verified = None
    all_sha256 = len(commit_to_verify) == 64

    # Look for signature of commit_to_verify
    # Warning about warning messages: sigbody comes off the blockchain, so we shouldn't include
    # anything from it in warning messages without validation (in case it is malicious)
    lines = [line for line in sigbody.split(b"\n") if line]
    for line in lines:  # pylint: disable=R1702
        try:
            sig_elt = json.loads(line.decode())
            assert isinstance(sig_elt.get("commit"), str)
        except:
            error_if(True, "Invalid signature syntax")
        if not repo.get(sig_elt["commit"]):
            error_if(
                not ignore_missing,
                (
                    "Signed commit missing from local repository"
                    if len(lines) <= 1
                    else "Signed commit(s) missing from local repository; try --ignore-missing if OK for some but not all to be present"
                ),
            )
            warnings.add("One or more signed commit(s) missing from local repository")
        # If the signature includes tags, make sure they don't refer to commits other than the
        # signed ones. There are several cases to deal with here as the signed & local tags could
        # each be either lightweight or annotated.
        local_tag = None
        if "tag" in sig_elt:
            assert isinstance(sig_elt["tag"], str)
            assert "tagObject" not in sig_elt or isinstance(sig_elt["tagObject"], str)
            try:
                local_tag = repo.revparse_ext(sig_elt["tag"])
            except KeyError:
                error_if(
                    not ignore_missing,
                    "Signed tag(s) missing from local repository; try --ignore-missing if this is OK",
                )
                warnings.add("One or more signed tag(s) missing from local repository")
                local_tag = (None, None)
            if isinstance(local_tag[0], Commit):  # local lightweight tag
                assert isinstance(local_tag[1], Reference)
                error_if(
                    not local_tag[1].name.startswith("refs/tags/"),
                    "The signed tag refers locally to something else: " + local_tag[1].name,
                )
                error_if(
                    local_tag[0].hex != sig_elt["commit"],
                    f"The local tag '{local_tag[1].shorthand}' refers to a different commit than the signed tag",
                )
                if "tagObject" in sig_elt:
                    warnings.add(
                        f"The local tag '{local_tag[1].shorthand}' is lightweight, while the signed tag was annotated"
                    )
            elif isinstance(local_tag[0], Tag):  # local annotated tag
                if "tagObject" in sig_elt:
                    error_if(
                        sig_elt["tagObject"] != local_tag[0].hex,
                        f"The local tag '{local_tag[0].name}' = {local_tag[0].hex} differs from the signed tag in annotations (although they share the same name and commit reference)",
                    )
                else:
                    error_if(
                        local_tag[0].target.hex != sig_elt["commit"],
                        f"The local annotated tag '{local_tag[0].name}' = {local_tag[0].hex} refers to a different commit than the signed tag",
                    )
                    warnings.add(
                        f"The local tag '{local_tag[1].shorthand}' is annotated, while the signed tag was lightweight"
                    )
                all_sha256 = all_sha256 and len(local_tag[0].hex) == 64
            elif local_tag[0] is not None:
                assert False
        # At last...check whether sig_elt signs the desired commit
        if sig_elt["commit"] == commit_to_verify:
            if local_tag and local_tag[1]:
                verified = f"Verified: local revision {revision} = signed tag {local_tag[1].shorthand} (commit {commit_to_verify})"
            elif verified is None:
                verified = f"Verified: local revision {revision} = signed commit {commit_to_verify}"

    error_if(not verified, f"Signature doesn't apply to {revision} ({commit_to_verify})")
    if not all_sha256:
        warnings.add(
            "Signature pertains to git SHA-1 digest(s); review git SHA-1 security risks and consider adopting git SHA-256 mode"
        )
    return verified, warnings


def dirty(repo):
    for v in repo.status().values():
        if v & (1 << 14):  # GIT_STATUS_IGNORED
            continue
        return True
    return False
