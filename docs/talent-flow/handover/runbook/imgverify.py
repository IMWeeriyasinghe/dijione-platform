"""imgverify.py REPO_DIR SERVICE DIGEST COMMIT
Downloads the image's layers that hold /app and compares every file two-way with
the git tree of COMMIT (apps/SERVICE and the packages the Dockerfile copies).
Only build-generated egg-info files may exist in the image alone. Exit 1 otherwise."""
import hashlib, io, json, subprocess, sys, tarfile, urllib.request

repo, svc, digest, commit = sys.argv[1:5]
REG, NAME = "crdijionenonprod.azurecr.io", f"dijione/{svc}"
refresh = subprocess.run("az acr login -n crdijionenonprod --expose-token --query accessToken -o tsv",
                         shell=True, capture_output=True, text=True).stdout.strip()
req = urllib.request.Request(f"https://{REG}/oauth2/token", data=f"grant_type=refresh_token&service={REG}&scope=repository:{NAME}:pull&refresh_token={refresh}".encode())
tok = json.load(urllib.request.urlopen(req))["access_token"]
H = {"Authorization": "Bearer " + tok}
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


_registry = urllib.request.build_opener(_NoRedirect)


def get(p, a=None):
    """Registry call with the token; a blob redirect to storage is followed without it."""
    try:
        return _registry.open(urllib.request.Request(f"https://{REG}/v2/{NAME}/{p}", headers={**H, **({"Accept": a} if a else {})}))
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            return urllib.request.urlopen(e.headers["Location"])
        raise
manifest = json.load(get(f"manifests/{digest}", "application/vnd.docker.distribution.manifest.v2+json"))
assert manifest.get("config"), "not a single-platform v2 manifest"
files = {}
for layer in manifest["layers"]:
    if layer["size"] > 20_000_000:
        continue  # base OS and dependency layers
    with tarfile.open(fileobj=io.BytesIO(get(f"blobs/{layer['digest']}").read()), mode="r:gz") as t:
        for m in t.getmembers():
            if m.isfile() and m.name.startswith("app/") and not m.name.split("/")[-1].startswith(".wh."):
                files[m.name[4:]] = t.extractfile(m).read()
blob = lambda b: hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()
tree = {}
for line in subprocess.run(["git", "-C", repo, "ls-tree", "-r", commit, f"apps/{svc}", "packages/auth-client-py", "packages/mail-client-py"],
                           capture_output=True, text=True, check=True).stdout.splitlines():
    meta, path = line.split("\t")
    tree[path] = meta.split()[2]
differ = [p for p in files if p in tree and blob(files[p]) != tree[p]]
image_only = [p for p in files if p not in tree and ".egg-info/" not in p]
git_only = [p for p in tree if p not in files]
ok = bool(files) and not differ and not image_only and not git_only
print("IMGVERIFY " + json.dumps({"ok": ok, "service": svc, "digest": digest, "commit": commit, "image_files": len(files),
                                  "identical": len(files) - len(differ) - len(image_only), "differ": differ[:10],
                                  "image_only": image_only[:10], "git_only": git_only[:10]}))
sys.exit(0 if ok else 1)
