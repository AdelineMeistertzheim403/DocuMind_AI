"""P4 B1 OCI Comparator v2: offline, read-only, single uncompressed layer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
import time


CHUNK = 1024 * 1024
SMALL = 16 * CHUNK
MAX_ENTRIES = 100000
HEX = r"[0-9a-f]{64}"
REFERENCES = {
    "archive": "ffec209c1b5eb3a8861e60585266c18069896adf05c8fe8f98c558d682351c2d",
    "config": "bbe90dab376fcd41b3495cad1264c017323ed68ed0915c601ea5fd229cbf6abd",
    "layer": "7b1b9ae269d164c3b88d386714f2def703acb15812a6d6f813c10064f57c766e",
    "sums": "a37f1847df7c7212c2d1b004e5ab3b0d654323a8ab2d425e20d89c551279527f",
    "metadata": "64863f4ebc2aaddb717d83147e623e37942716728736afa40f5bd39d1083db36",
    "files": 9771,
    "directories": 564,
}
LIMITS = [
    "Comparison is against authenticated historical inventories, not the live rootfs.",
    "Source sizes, timestamps, xattrs, ACLs, capabilities and hardlink topology are not inventoried.",
    "TAR timestamps, PAX attributes and hardlink headers are recorded, not silently equated.",
    "No signature, runtime, ABI, configuration hardening or production qualification.",
    "Only one Linux amd64 image with one uncompressed, non-whiteout layer is supported.",
    "Missing root directory header leaves its layer metadata unmeasured.",
    "Historical comparator code hash and return code remain unknown.",
]


class Invalid(ValueError):
    pass


class Incomplete(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Invalid(message)


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True,
                       allow_nan=False) + "\n").encode("ascii")


def json_object(data):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              Invalid("Nonfinite JSON value")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise Invalid("Invalid UTF-8 JSON") from error


def safe_path(name, directory=False):
    need(isinstance(name, str) and len(name) <= 4096 and name,
         "Empty or oversized path")
    need(all(32 <= ord(c) < 127 for c in name) and "\\" not in name
         and ":" not in name, "Ambiguous/non-ASCII path: " + repr(name))
    if name.startswith("./"):
        name = name[2:]
    if directory and name.endswith("/"):
        name = name[:-1]
    if name == ".":
        need(directory, "Root is not a directory")
        return name
    need(name and not name.startswith("/") and
         all(p not in ("", ".", "..") for p in name.split("/")),
         "Unsafe path: " + repr(name))
    need(not any(p.startswith(".wh.") for p in name.split("/")),
         "Whiteout is unsupported")
    return name


def open_input(path):
    path = Path(os.path.abspath(path))
    for parent in [*reversed(path.parents), path]:
        need(not parent.is_symlink(), "Symlink input component: " + str(parent))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise Invalid("Input must be a regular file")
    return os.fdopen(fd, "rb")


def fingerprint(stream):
    value = os.fstat(stream.fileno())
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns)


def digest_stream(stream):
    h = hashlib.sha256()
    while True:
        data = stream.read(CHUNK)
        if not data:
            return h.hexdigest()
        h.update(data)


def digest(path):
    with open_input(path) as stream:
        return digest_stream(stream)


def authenticated_bytes(path, expected, measurements=None, label=None):
    with open_input(path) as stream:
        before = fingerprint(stream)
        data = stream.read(SMALL + 1)
        need(len(data) <= SMALL, "Oversized inventory/manifest")
        observed = hashlib.sha256(data).hexdigest()
        if measurements is not None:
            measurements[label] = observed
        need(observed == expected, "Inventory/manifest SHA-256 mismatch")
        need(before == fingerprint(stream), "Input changed while reading")
        return data


def inventories(sums_path, metadata_path, refs, measurements=None):
    # Both byte strings are authenticated before either parser is used.
    sums = authenticated_bytes(sums_path, refs["sums"], measurements, "sums")
    metadata = authenticated_bytes(metadata_path, refs["metadata"], measurements, "metadata")
    rows, hashes = {}, {}
    for data in (sums, metadata):
        need(data.endswith(b"\n") and b"\r" not in data, "Inventory line ending ambiguity")
    try:
        for line in metadata.decode("ascii").splitlines():
            match = re.fullmatch(r"([fd]) ([0-7]{3,4}) ([0-9]+):([0-9]+) (.+)", line)
            if not match:
                raise Incomplete("Unknown metadata format/type")
            kind, mode, uid, gid, original = match.groups()
            name = safe_path(original, kind == "d")
            need(name not in rows, "Duplicate metadata path")
            rows[name] = {"type": "file" if kind == "f" else "directory",
                          "mode": int(mode, 8), "uid": int(uid), "gid": int(gid)}
        for line in sums.decode("ascii").splitlines():
            match = re.fullmatch("(" + HEX + r")  (.+)", line)
            if not match:
                raise Incomplete("Unknown SHA256SUMS format")
            value, original = match.groups()
            name = safe_path(original)
            need(name not in hashes, "Duplicate hash inventory path")
            hashes[name] = value
    except UnicodeError as error:
        raise Incomplete("Non-ASCII inventory unsupported") from error
    need(rows.get(".", {}).get("type") == "directory", "Missing inventoried root directory")
    need(set(hashes) == {n for n, r in rows.items() if r["type"] == "file"},
         "Hash inventory and metadata regular path sets differ")
    need(len(hashes) == refs["files"] and
         sum(r["type"] == "directory" for r in rows.values()) == refs["directories"],
         "Unexpected anchored inventory counts")
    for name in rows:
        if name != ".":
            parent = name.rpartition("/")[0] or "."
            need(rows.get(parent, {}).get("type") == "directory", "Invalid inventory parent")
    return rows, hashes


class HashReader:
    def __init__(self, stream):
        self.stream = stream
        self.hash = hashlib.sha256()
        self.size = 0

    def read(self, size):
        data = self.stream.read(size)
        self.hash.update(data)
        self.size += len(data)
        return data


class Slice:
    def __init__(self, stream, size):
        self.stream, self.remaining = stream, size

    def read(self, size):
        size = min(size, self.remaining)
        data = self.stream.read(size)
        need(len(data) == size, "Truncated TAR payload")
        self.remaining -= len(data)
        return data


def read_exact(stream, size):
    data = stream.read(size)
    need(len(data) == size, "Truncated TAR")
    return data


def pax_values(data):
    result = {}
    while data:
        match = re.match(rb"([1-9][0-9]*) ", data)
        need(match is not None, "Malformed PAX record")
        size = int(match.group(1))
        need(match.end() < size <= len(data) and data[size - 1:size] == b"\n",
             "Invalid PAX length")
        record = data[match.end():size - 1]
        need(b"=" in record, "Invalid PAX key/value")
        key, value = record.split(b"=", 1)
        try:
            key, value = key.decode("ascii"), value.decode("utf-8")
        except UnicodeError as error:
            raise Invalid("Invalid PAX encoding") from error
        need(key not in result and "\0" not in value, "Duplicate/invalid PAX attribute")
        if key not in ("path", "linkpath", "mtime", "atime", "ctime"):
            raise Incomplete("Uncontrolled PAX attribute: " + key)
        if key in ("mtime", "atime", "ctime"):
            need(re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value), "Invalid PAX timestamp")
        result[key] = value
        data = data[size:]
    return result


class TarStream:
    """Account for every physical header, payload, padding and trailer byte."""
    def __init__(self, stream):
        self.stream = stream
        self.headers = 0
        self.extensions = []
        self.entries = 0
        self.trailer_bytes = 0

    def members(self):
        pending = {}
        while True:
            raw = read_exact(self.stream, 512)
            if raw == b"\0" * 512:
                need(not pending, "Orphan TAR extension")
                need(read_exact(self.stream, 512) == b"\0" * 512, "Missing TAR end marker")
                self.trailer_bytes = 1024
                while True:
                    data = self.stream.read(CHUNK)
                    if not data:
                        break
                    need(not data.strip(b"\0"), "Nonzero data after TAR end marker")
                    self.trailer_bytes += len(data)
                need(self.trailer_bytes % 512 == 0, "Unaligned TAR trailer")
                return
            self.headers += 1
            need(self.headers <= MAX_ENTRIES, "TAR header limit exceeded")
            try:
                item = tarfile.TarInfo.frombuf(raw, "utf-8", "strict")
            except (tarfile.HeaderError, UnicodeError, ValueError) as error:
                raise Invalid("Invalid TAR header/checksum") from error
            need(item.size >= 0 and item.uid >= 0 and item.gid >= 0
                 and 0 <= item.mode <= 0o7777, "Invalid TAR numeric metadata")
            body = Slice(self.stream, item.size)
            if item.type in (tarfile.XHDTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK):
                if not (item.name == "././@LongLink" and item.type in
                        (tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK)) and not (
                        item.name == "././@PaxHeader" and item.type == tarfile.XHDTYPE):
                    safe_path(item.name)
                need(item.size <= SMALL, "Oversized TAR extension")
                data = body.read(item.size)
                if item.type == tarfile.XHDTYPE:
                    values = pax_values(data)
                else:
                    need(data.endswith(b"\0") and b"\0" not in data[:-1],
                         "Ambiguous GNU long path")
                    values = {"path" if item.type == tarfile.GNUTYPE_LONGNAME else "linkpath":
                              data[:-1].decode("utf-8")}
                need(not set(values).intersection(pending), "Conflicting TAR extensions")
                pending.update(values)
                self.extensions.append({"header": self.headers, "kind": item.type.decode("ascii"),
                                        "name": item.name, "payload_sha256": hashlib.sha256(data).hexdigest(),
                                        "attributes": values})
            elif item.type == tarfile.XGLTYPE:
                raise Incomplete("Global PAX headers unsupported")
            else:
                need(item.type in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE,
                                   tarfile.SYMTYPE, tarfile.LNKTYPE),
                     "Special/sparse/unknown TAR file refused")
                # Even overridden header paths must not contain traversal.
                safe_path(item.name, item.isdir())
                if item.issym() or item.islnk():
                    if item.linkname:
                        safe_path(item.linkname)
                else:
                    need(not item.linkname and "linkpath" not in pending,
                         "Link target on a nonlink entry")
                need(not item.devmajor and not item.devminor, "Device metadata on ordinary entry")
                if "path" in pending:
                    item.name = pending["path"]
                if "linkpath" in pending:
                    item.linkname = pending["linkpath"]
                item.pax_headers = dict(pending)
                pending.clear()
                need(item.isfile() or item.size == 0, "Payload on a nonregular TAR entry")
                self.entries += 1
                yield item, body
            while body.remaining:
                body.read(min(CHUNK, body.remaining))
            padding = read_exact(self.stream, (-item.size) % 512)
            need(not padding.strip(b"\0"), "Nonzero TAR payload padding")

    def coverage(self):
        return {"physical_headers": self.headers, "logical_entries": self.entries,
                "extension_headers": self.extensions, "trailer_bytes": self.trailer_bytes,
                "all_bytes_accounted": True}


def outer_pass(stream, refs, selected=None):
    stream.seek(0)
    reader = HashReader(stream)
    archive = TarStream(reader)
    entries, small, selected_rows, selected_coverage = {}, {}, None, None
    buffered = 0
    for item, body in archive.members():
        name = safe_path(item.name, item.isdir())
        need(name not in entries, "Duplicate outer TAR path")
        need(item.isfile() or item.isdir(), "Nonregular outer archive entry")
        row = {"type": "file" if item.isfile() else "directory", "size": item.size}
        if item.isfile():
            hbody = HashReader(body)
            if name == selected:
                selected_rows, selected_coverage = layer_inventory(hbody)
            elif item.size <= SMALL:
                prefix = hbody.read(min(512, item.size))
                candidate = (name.endswith(".json") or name.endswith("/json")
                             or name.endswith("/VERSION")
                             or name in ("repositories", "oci-layout", "index.json", "manifest.json")
                             or name.startswith("blobs/sha256/") and
                             prefix.lstrip().startswith(b"{"))
                if candidate:
                    buffered += item.size
                    if buffered > 64 * CHUNK:
                        raise Incomplete("JSON metadata memory bound exceeded")
                    small[name] = prefix + hbody.read(item.size - len(prefix))
                else:
                    while hbody.read(CHUNK):
                        pass
            else:
                while hbody.read(CHUNK):
                    pass
            row["sha256"] = hbody.hash.hexdigest()
            need(hbody.size == item.size, "Incomplete outer payload consumption")
            if re.fullmatch(r"blobs/sha256/" + HEX, name):
                need(row["sha256"] == name.rsplit("/", 1)[1], "OCI blob pathname digest mismatch")
        entries[name] = row
    need(reader.hash.hexdigest() == refs["archive"], "Archive changed / SHA-256 mismatch")
    for name in entries:
        if name != ".":
            parent = name.rpartition("/")[0]
            while parent:
                need(parent not in entries or entries[parent]["type"] == "directory",
                     "Outer TAR path has nondirectory ancestor")
                parent = parent.rpartition("/")[0]
    return entries, small, archive.coverage(), selected_rows, selected_coverage


def docker_binding(entries, small, refs):
    need("manifest.json" in small, "Docker manifest.json missing")
    manifests = json_object(small["manifest.json"])
    need(isinstance(manifests, list) and len(manifests) == 1, "Expected exactly one Docker image")
    manifest = manifests[0]
    need(isinstance(manifest, dict) and set(manifest).issubset(
        {"Config", "RepoTags", "Layers", "LayerSources"}) and
        {"Config", "Layers"}.issubset(manifest), "Ambiguous Docker manifest")
    sources = manifest.get("LayerSources")
    need(sources is None or isinstance(sources, dict), "Invalid LayerSources")
    tags = manifest.get("RepoTags")
    need(tags is None or isinstance(tags, list) and all(isinstance(t, str) for t in tags)
         and len(tags) == len(set(tags)), "Invalid RepoTags")
    layers = manifest["Layers"]
    need(isinstance(layers, list), "Invalid Layers")
    if len(layers) != 1:
        raise Incomplete("Only one layer is supported")
    config_name = safe_path(manifest["Config"])
    layer_name = safe_path(layers[0])
    need(len({"manifest.json", config_name, layer_name}) == 3, "Aliased image members")
    need(config_name in small and entries[config_name].get("sha256") == refs["config"],
         "Config missing or exact image ID mismatch")
    need(layer_name in entries and entries[layer_name].get("sha256") == refs["layer"],
         "Layer missing or exact uncompressed layer SHA-256 mismatch")
    if sources:
        layer_digest = "sha256:" + entries[layer_name]["sha256"]
        need(set(sources) == {layer_digest}, "Unrecognized/additional LayerSources layer key")
        source = sources[layer_digest]
        need(isinstance(source, dict) and set(source) == {"digest", "mediaType", "size"},
             "Missing/unrecognized LayerSources descriptor fields")
        need(source["digest"] == layer_digest, "LayerSources digest mismatch")
        need(source["mediaType"] == "application/vnd.oci.image.layer.v1.tar",
             "LayerSources mediaType mismatch")
        need(type(source["size"]) is int and source["size"] >= 0
             and source["size"] == entries[layer_name]["size"], "LayerSources size mismatch")
    config = json_object(small[config_name])
    need(isinstance(config, dict) and config.get("os") == "linux"
         and config.get("architecture") == "amd64", "Wrong config OS/architecture")
    rootfs = config.get("rootfs")
    need(isinstance(rootfs, dict) and rootfs.get("type") == "layers"
         and rootfs.get("diff_ids") == ["sha256:" + refs["layer"]],
         "Config rootfs diff_ids binding mismatch")
    claimed = {"manifest.json", config_name, layer_name}
    ancillary = {}
    oci_manifests = []
    # Docker-save may include OCI metadata alongside its Docker manifest.
    def descriptor(desc, stack):
        if len(stack) > 8:
            raise Incomplete("OCI descriptor nesting bound exceeded")
        need(isinstance(desc, dict) and isinstance(desc.get("digest"), str)
             and re.fullmatch("sha256:" + HEX, desc["digest"]), "Invalid OCI descriptor")
        name = "blobs/sha256/" + desc["digest"][7:]
        need(name in entries and entries[name].get("sha256") == desc["digest"][7:]
             and type(desc.get("size")) is int and desc["size"] == entries[name]["size"],
             "OCI descriptor size/digest mismatch")
        need(name not in stack, "Cyclic OCI descriptor graph")
        claimed.add(name)
        media = desc.get("mediaType")
        if media in ("application/vnd.oci.image.index.v1+json",
                     "application/vnd.docker.distribution.manifest.list.v2+json"):
            obj = json_object(small[name])
            need(obj.get("schemaVersion") == 2 and isinstance(obj.get("manifests"), list)
                 and len(obj["manifests"]) == 1, "Unsupported OCI index")
            descriptor(obj["manifests"][0], stack | {name})
        elif media in ("application/vnd.oci.image.manifest.v1+json",
                       "application/vnd.docker.distribution.manifest.v2+json"):
            oci_manifests.append(name)
            obj = json_object(small[name])
            need(obj.get("schemaVersion") == 2 and isinstance(obj.get("layers"), list)
                 and len(obj["layers"]) == 1, "Unsupported OCI manifest")
            need(obj.get("config", {}).get("digest") == "sha256:" + refs["config"]
                 and obj["layers"][0].get("digest") == "sha256:" + refs["layer"],
                 "OCI manifest not bound to expected image")
            descriptor(obj["config"], stack | {name})
            descriptor(obj["layers"][0], stack | {name})
        elif media not in ("application/vnd.oci.image.config.v1+json",
                           "application/vnd.docker.container.image.v1+json",
                           "application/vnd.oci.image.layer.v1.tar",
                           "application/vnd.docker.image.rootfs.diff.tar"):
            raise Incomplete("Unsupported OCI media type: " + str(media))
        elif media in ("application/vnd.oci.image.config.v1+json",
                       "application/vnd.docker.container.image.v1+json"):
            need(desc["digest"] == "sha256:" + refs["config"], "Wrong OCI config leaf")
        else:
            need(desc["digest"] == "sha256:" + refs["layer"], "Wrong OCI layer leaf")
    if "index.json" in small or "oci-layout" in small:
        need("index.json" in small and "oci-layout" in small, "Incomplete OCI layout")
        need(json_object(small["oci-layout"]) == {"imageLayoutVersion": "1.0.0"},
             "Unknown OCI layout version")
        index = json_object(small["index.json"])
        need(isinstance(index, dict) and index.get("schemaVersion") == 2
             and isinstance(index.get("manifests"), list) and len(index["manifests"]) == 1,
             "Invalid OCI index")
        descriptor(index["manifests"][0], set())
        need(len(oci_manifests) == 1, "OCI index must bind exactly one image manifest")
        claimed.update(("index.json", "oci-layout"))
    if "repositories" in small:
        repositories = json_object(small["repositories"])
        need(isinstance(repositories, dict), "Invalid Docker repositories")
        for repo, values in repositories.items():
            need(isinstance(values, dict), "Invalid repository tag map")
            for tag, value in values.items():
                need(repo + ":" + tag in (tags or []) and isinstance(value, str)
                     and layer_name == value + "/layer.tar", "Repository/tag layer binding mismatch")
        claimed.add("repositories")
    legacy_parent = layer_name.rpartition("/")[0]
    for suffix in ("VERSION", "json"):
        name = legacy_parent + "/" + suffix
        if name in entries:
            need(name in small or entries[name]["size"] <= SMALL, "Oversized legacy metadata")
            if suffix == "VERSION":
                need(small[name] in (b"1.0", b"1.0\n"), "Unsupported legacy VERSION")
                ancillary[name] = "legacy VERSION 1.0"
            else:
                need(isinstance(json_object(small[name]), dict), "Invalid legacy layer JSON")
                ancillary[name] = "legacy layer JSON, no additional identity claim"
            claimed.add(name)
    extra = sorted(n for n, r in entries.items() if r["type"] == "file" and n not in claimed)
    need(not extra, "Unclaimed outer regular entries: " + repr(extra))
    parents = {"."}
    for name in claimed:
        parent = name.rpartition("/")[0]
        while parent:
            parents.add(parent)
            parent = parent.rpartition("/")[0]
    need(not any(r["type"] == "directory" and n not in parents for n, r in entries.items()),
         "Unclaimed outer directory")
    return layer_name, {"config_path": config_name, "layer_path": layer_name,
                        "layer_sources_present": "LayerSources" in manifest,
                        "layer_sources": sources,
                        "repo_tags": tags, "claimed_regular_paths": sorted(claimed),
                        "ancillary": ancillary, "config_sha256": refs["config"],
                        "layer_diff_id": "sha256:" + refs["layer"],
                        "manifest_sha256": entries["manifest.json"]["sha256"]}


def layer_inventory(stream):
    archive = TarStream(stream)
    rows = {}
    for item, body in archive.members():
        name = safe_path(item.name, item.isdir())
        need(name not in rows, "Duplicate layer path")
        row = {"type": "file" if item.isfile() else "directory" if item.isdir()
               else "symlink" if item.issym() else "hardlink",
               "mode": item.mode, "uid": item.uid, "gid": item.gid,
               "size": item.size, "mtime": str(item.mtime), "uname": item.uname,
               "gname": item.gname, "pax": item.pax_headers}
        if item.isfile():
            row["sha256"] = digest_stream(body)
        if item.issym() or item.islnk():
            row["target"] = safe_path(item.linkname)
        rows[name] = row
    for name, row in rows.items():
        parent = name.rpartition("/")[0]
        while parent:
            need(parent not in rows or rows[parent]["type"] == "directory",
                 "Layer path has nondirectory ancestor")
            parent = parent.rpartition("/")[0]
        if row["type"] == "hardlink":
            target, seen = row["target"], {name}
            while target in rows and rows[target]["type"] == "hardlink":
                need(target not in seen, "Cyclic hardlink")
                seen.add(target)
                target = rows[target]["target"]
            need(target in rows and rows[target]["type"] == "file", "Invalid hardlink target")
            row["resolved_sha256"] = rows[target]["sha256"]
    return rows, archive.coverage()


def compare_rows(expected, hashes, actual):
    diffs = {key: [] for key in ("missing_regular", "missing_nonroot_directories",
                                "extra_entries", "content", "type", "permissions",
                                "uid_gid", "links")}
    missing = set(expected) - set(actual)
    diffs["missing_regular"] = sorted(n for n in missing if expected[n]["type"] == "file")
    diffs["missing_nonroot_directories"] = sorted(n for n in missing if n != "."
                                                and expected[n]["type"] == "directory")
    diffs["extra_entries"] = sorted(set(actual) - set(expected))
    for name in sorted(set(expected) & set(actual)):
        source, layer = expected[name], actual[name]
        if source["type"] != layer["type"]:
            diffs["type"].append({"path": name, "expected": source["type"], "actual": layer["type"]})
        if name in hashes and layer["type"] in ("file", "hardlink"):
            value = layer.get("sha256", layer.get("resolved_sha256"))
            if hashes[name] != value:
                diffs["content"].append({"path": name, "expected": hashes[name], "actual": value})
        if source["mode"] != layer["mode"]:
            diffs["permissions"].append({"path": name, "expected": format(source["mode"], "04o"),
                                         "actual": format(layer["mode"], "04o")})
        if (source["uid"], source["gid"]) != (layer["uid"], layer["gid"]):
            diffs["uid_gid"].append({"path": name, "expected": [source["uid"], source["gid"]],
                                    "actual": [layer["uid"], layer["gid"]]})
    diffs["links"] = [{"path": n, "type": r["type"], "target": r["target"]}
                      for n, r in sorted(actual.items()) if r["type"] in ("hardlink", "symlink")]
    root_missing = "." in missing
    regular_equal = (set(hashes) == {n for n, r in actual.items() if r["type"] == "file"}
                     and not diffs["content"] and not any(
                         r["path"] in hashes for r in diffs["type"]))
    differences = root_missing or any(diffs.values())
    return {
        "differences": diffs, "difference_counts": {k: len(v) for k, v in diffs.items()},
        "root_directory": {"absent_from_layer": root_missing,
                           "not_a_missing_regular_file": True,
                           "metadata_comparison_complete": not root_missing},
        "regular_contents_equal": regular_equal,
        "all_controlled_metadata_equal": not differences,
        "complete_metadata_equality_established": False,
        "counts": {"expected_regular_paths": len(hashes),
                   "expected_entries": len(expected), "layer_entries": len(actual),
                   "regular_paths_hashed": sum(r["type"] == "file" for r in actual.values()),
                   "matched_regular_paths": sum(n in actual and actual[n]["type"] == "file"
                                                for n in hashes)},
        "layer_entries": actual,
    }, 10 if differences else 0


def evaluate(archive_path, sums_path, metadata_path, refs=None):
    refs = dict(REFERENCES if refs is None else refs)
    report = {"schema": "p4-b1-oci-comparator-v2", "decision": "REVIEW_ONLY_BLOCKED",
              "formal_b1_contents_closed": False, "go": {"production": False, "runtime": False,
                                                        "c5": False},
              "methodological_limits": LIMITS, "expected_anchors": refs,
              "uncontrolled_attributes": {
                  "timestamps": "TAR/PAX recorded; source timestamps unavailable",
                  "source_sizes": "TAR sizes recorded; source sizes unavailable",
                  "hardlink_topology": "TAR links recorded; source inode topology unavailable",
                  "uname_gname": "TAR recorded; only numeric source IDs available",
                  "xattrs_acls_capabilities": "Not inventoried; unsupported TAR attributes stop control"},
              "observed_sha256": {}, "status": "ERROR", "returncode": 20, "checks": {},
              "historical_comparator": {"returncode": None, "code_sha256": None}}
    try:
        expected, hashes = inventories(sums_path, metadata_path, refs, report["observed_sha256"])
        report["checks"]["inventories_authenticated_and_path_sets_valid"] = True
        with open_input(archive_path) as stream:
            before = fingerprint(stream)
            report["observed_sha256"]["archive"] = digest_stream(stream)
            need(report["observed_sha256"]["archive"] == refs["archive"], "Exact archive SHA-256 mismatch")
            report["checks"]["archive_authenticated"] = True
            entries, small, coverage, _, _ = outer_pass(stream, refs)
            report["outer_entries"] = entries
            report["outer_coverage"] = coverage
            report["observed_sha256"]["outer_regular_entries"] = {
                n: r["sha256"] for n, r in sorted(entries.items()) if r["type"] == "file"}
            layer_name, binding = docker_binding(entries, small, refs)
            report["image_binding"] = binding
            report["checks"]["docker_config_layer_binding_verified"] = True
            again, _, coverage2, rows, layer_coverage = outer_pass(stream, refs, layer_name)
            need(again == entries and coverage2 == coverage, "Outer archive changed between passes")
            need(before == fingerprint(stream), "Archive changed during comparison")
            report["checks"]["all_passes_same_archive_bytes"] = True
            report["layer_coverage"] = layer_coverage
            result, code = compare_rows(expected, hashes, rows)
            report.update(result)
            report.update(returncode=code, status="TECHNICAL_SUCCESS_WITH_LIMITS" if code == 0
                          else "DIFFERENCES_OBSERVED")
    except Incomplete as error:
        report.update(returncode=30, status="CONTROL_INCOMPLETE", error=str(error))
    except (Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        report.update(returncode=20, status="ERROR", error=type(error).__name__ + ": " + str(error))
    return report


def verify_release(root, anchor):
    need(re.fullmatch(HEX, anchor), "Invalid external release anchor")
    raw = authenticated_bytes(root / "SHA256SUMS", anchor)
    expected = {}
    for line in raw.decode("ascii").splitlines():
        match = re.fullmatch("(" + HEX + r")  (.+)", line)
        need(match is not None, "Invalid release manifest")
        value, name = match.groups()
        name = safe_path(name)
        need(name not in expected and name != "SHA256SUMS", "Duplicate/self release entry")
        expected[name] = value
    actual = set()
    for path in root.rglob("*"):
        need(not path.is_symlink(), "Symlink in release")
        if path.is_file() and path.name != "SHA256SUMS":
            actual.add(path.relative_to(root).as_posix())
        else:
            need(path.is_dir() or path == root / "SHA256SUMS", "Special release entry")
    need(actual == set(expected), "Release file coverage mismatch")
    need("comparator.py" in expected and "test_comparator.py" in expected, "Unsealed comparator/tests")
    for name, value in expected.items():
        need(digest(root / name) == value, "Release SHA mismatch: " + name)
    return expected


def new_directory(path):
    path = Path(os.path.abspath(path))
    for parent in path.parents:
        need(not parent.is_symlink(), "Symlink evidence parent")
    need(path.parent.is_dir() and not path.exists() and not path.is_symlink(),
         "Evidence directory must be new with existing parent")
    path.mkdir(mode=0o700)
    return path


def write_new(path, data):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sums", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--release-anchor", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = None
    try:
        for path in (args.archive, args.sums, args.metadata, args.out):
            need(path.is_absolute(), "Absolute input/output paths required")
        root = Path(__file__).absolute().parent
        out_abs = Path(os.path.abspath(args.out))
        for source in (args.archive, args.sums, args.metadata, root / "SHA256SUMS"):
            need(out_abs not in Path(os.path.abspath(source)).parents,
                 "Evidence directory cannot contain an input")
            source_parent = Path(os.path.abspath(source)).parent
            need(source_parent != out_abs and source_parent not in out_abs.parents,
                 "Evidence directory must be outside input directories")
        need(root != out_abs and root not in out_abs.parents, "Evidence must be outside release")
        out = new_directory(args.out)
        start = {"argv": sys.orig_argv, "parameters": {
                    k: str(v) for k, v in vars(args).items()}, "cwd": os.getcwd(),
                 "python": sys.version, "python_executable": sys.executable,
                 "start_ns": time.time_ns(),
                 "comparator_sha256_observed": digest(root / "comparator.py"),
                 "complete": False, "returncode": None}
        write_new(out / "started.json", encode(start))
        need(sys.version_info[:2] == (3, 11), "Python 3.11 required; no installation permitted")
        sealed = verify_release(root, args.release_anchor)
        report = evaluate(args.archive, args.sums, args.metadata)
        report["comparator_sha256"] = sealed["comparator.py"]
        report["release_manifest_sha256"] = args.release_anchor
    except Exception as error:
        report = {"status": "ERROR", "decision": "REVIEW_ONLY_BLOCKED",
                  "formal_b1_contents_closed": False,
                  "go": {"production": False, "runtime": False, "c5": False},
                  "returncode": 20, "error": type(error).__name__ + ": " + str(error)}
    code = report["returncode"]
    stdout = encode({"status": report["status"], "returncode": code,
                     "decision": "REVIEW_ONLY_BLOCKED"})
    stderr = (report.get("error", "") + ("\n" if "error" in report else "")).encode("utf-8")
    if out is not None:
        write_new(out / "report.json", encode(report))
        write_new(out / "stdout", stdout)
        write_new(out / "stderr", stderr)
        receipt = dict(start, complete=True, returncode=code, end_ns=time.time_ns(),
                       sha256={name: digest(out / name) for name in
                               ("started.json", "report.json", "stdout", "stderr")})
        write_new(out / "receipt.json", encode(receipt))
        names = ("started.json", "report.json", "stdout", "stderr", "receipt.json")
        write_new(out / "SHA256SUMS", "".join(
            digest(out / n) + "  " + n + "\n" for n in names).encode("ascii"))
        write_new(out / "evidence-anchor.json", encode({
            "sha256sums": digest(out / "SHA256SUMS"), "decision": "REVIEW_ONLY_BLOCKED",
            "external_authentication_required": True}))
    sys.stdout.buffer.write(stdout)
    sys.stderr.buffer.write(stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
