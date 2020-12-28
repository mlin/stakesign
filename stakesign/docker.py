import json
import docker

DEFAULT_HOST = "unix://var/run/docker.sock"
# {"Id": "", "aka": {"RepoTags": [], "RepoDigests": []}}


class ErrorMessage(Exception):
    pass


def error_if(cond, msg):
    if cond:
        raise ErrorMessage(msg) from None


def prepare(docker_host, images):
    client = docker.DockerClient(docker_host, version="auto")
    images_idx = images_handle_index(client)

    results = []
    warnings = []
    for handle in images:
        hits = None
        for handle2 in (handle, handle + ":latest", "sha256:" + handle):
            if hits is None:
                hits = images_idx.get(handle2)
        error_if(not hits, "No such image: " + handle)
        error_if(len(hits) > 1, "Ambiguous image: " + handle)
        image_id = next(iter(hits))
        image_attrs = client.images.get(image_id).attrs
        res = {"imageId": image_id}
        if image_attrs.get("RepoTags"):
            res["akaRepoTags"] = image_attrs["RepoTags"]
        if image_attrs.get("RepoDigests"):
            res["akaRepoDigests"] = image_attrs["RepoDigests"]
        results.append(res)

    return (
        "\n".join(json.dumps(res, separators=(",", ":")) for res in results).encode() + b"\n"
    ), warnings


def verify(
    docker_host, sigbody, handle_to_verify=None, ignore_missing=False
):  # pylint: disable=R0912,R0914,R0915
    client = docker.DockerClient(docker_host, version="auto")
    local_images_index = images_handle_index(client)
    image_to_verify = None
    if handle_to_verify:
        image_to_verify = local_images_index.get(handle_to_verify)
        error_if(not image_to_verify, "No such local image: " + handle_to_verify)
        image_to_verify = client.images.get(next(iter(image_to_verify)))

    verified = []
    warnings = set()
    lines = [line for line in sigbody.split(b"\n") if line]
    for line in lines:
        try:
            sig_elt = json.loads(line.decode())
            assert isinstance(sig_elt.get("imageId"), str)
        except:
            error_if(True, "Invalid signature syntax")

        # First, check that if the signature includes tags, those tags don't point to a different
        # local image (exception: warning for :latest)
        signed_tags = []
        if "akaRepoTags" in sig_elt:
            assert isinstance(sig_elt["akaRepoTags"], list)
            signed_tags.extend(sig_elt["akaRepoTags"])
        if "akaRepoDigests" in sig_elt:
            assert isinstance(sig_elt["akaRepoDigests"], list)
            signed_tags.extend(sig_elt["akaRepoDigests"])
        for signed_handle in signed_tags:
            assert isinstance(signed_handle, str)
            error_if(
                len(local_images_index.get(signed_handle, set())) > 1,
                f"The local image tag '{signed_handle}' is ambiguous",
            )
            if (
                signed_handle in local_images_index
                and next(iter(local_images_index[signed_handle])) != sig_elt["imageId"]
            ):
                if signed_handle.endswith(":latest"):
                    warnings.add(
                        f"The local default image tag '{signed_handle}' refers to a different image ID than was signed; be sure to use the full ID or digest to get the correct image."
                    )
                else:
                    error_if(
                        True,
                        f"The local image tag '{signed_handle}' refers to a different image ID than was signed",
                    )

        if image_to_verify:
            if image_to_verify.id != sig_elt["imageId"]:
                continue
            local_image = image_to_verify
        else:
            local_image = local_images_index.get(sig_elt["imageId"])
            error_if(
                not (ignore_missing or local_image),
                "Signed image missing locally"
                + (
                    "; try --ignore-missing if OK for some but not all to be missing"
                    if len(lines) > 1
                    else ""
                ),
            )
            if local_image:
                assert len(local_image) == 1
                local_image = client.images.get(next(iter(local_image)))
            else:
                warnings.add("The transaction signs one or more images that are missing locally")
                continue

        local_tags = []
        if local_image.attrs.get("RepoTags"):
            local_tags.extend(local_image.attrs["RepoTags"])
        if local_image.attrs.get("RepoDigests"):
            local_tags.extend(local_image.attrs["RepoDigests"])
        common_tags = set(local_tags).intersection(set(signed_tags))

        aka_msg = ""
        if common_tags:
            aka_msg = ", aka: " + " ".join(sorted(common_tags))
        elif signed_tags and local_tags:
            warnings.add(
                f"Image ID = {local_image.id} was signed, but under different tag(s) than it's known by locally; double-check it's the intended image if selecting by tag."
            )
        verified.append("Verified image ID = " + local_image.id + aka_msg)

    error_if(not verified, "No image verified")
    return verified, warnings


def images_handle_index(client):
    # omnibus index of docker image IDs by ID, short ID, RepoTags, RepoDigests
    ans = {}
    for image in client.images.list():
        attrs = image.attrs
        assert image.id == attrs["Id"]
        ans.setdefault(image.id, set()).add(image.id)
        ans.setdefault(image.id[:12], set()).add(image.id)
        ans.setdefault(image.short_id, set()).add(image.id)
        for tag in attrs.get("RepoTags", []):
            ans.setdefault(tag, set()).add(image.id)
        for dig in attrs.get("RepoDigests", []):
            ans.setdefault(dig, set()).add(image.id)
    return ans
