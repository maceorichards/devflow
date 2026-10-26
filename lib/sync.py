#!/usr/bin/env python3
"""devflow sync: build managed skills from vendor sources + patches + owned skills,
install them into the selected providers' skills folders, and keep the devflow
section in their instructions files and the git ignore lines in place.

Usage (via ../sync.sh):
  sync.sh                 rebuild everything at the locked vendor commits
  sync.sh --dry-run       show what would change, write nothing
  sync.sh --update        pull vendors, show upstream changes, rebuild, re-lock
  sync.sh providers <a,b>   choose providers (claude, codex, gemini, cursor), then sync
  sync.sh providers <a,b> --dry-run   preview that choice, write nothing
  sync.sh edit <skill>    prepare .patch-work/<skill>/{a,b} to change a patch (edit b/)
  sync.sh save <skill>    write patches/<skill>.patch from .patch-work/<skill>
"""
import filecmp
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "manifest.json")
LOCK = os.path.join(ROOT, "vendor.lock")
LOCAL = os.path.join(ROOT, "devflow.local.json")
MD_START = "<!-- devflow:start"
MD_END = "<!-- devflow:end -->"


def sh(args, cwd=None, check=True):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed:\n{r.stdout}{r.stderr}")
    return r


def load():
    with open(MANIFEST) as f:
        man = json.load(f)
    lock = {}
    if os.path.exists(LOCK):
        with open(LOCK) as f:
            lock = json.load(f)
    return man, lock


def vendor_dir(man, src):
    return os.path.join(ROOT, man["vendors"][src]["dir"])


def ensure_vendor(man, src, sha=None):
    d = vendor_dir(man, src)
    if not os.path.isdir(os.path.join(d, ".git")):
        print(f"cloning {src} …")
        sh(["git", "clone", "-q", man["vendors"][src]["url"], d])
    if sha:
        cur = sh(["git", "rev-parse", "HEAD"], cwd=d).stdout.strip()
        if cur != sha:
            sh(["git", "fetch", "-q", "origin"], cwd=d, check=False)
            sh(["git", "checkout", "-q", sha], cwd=d)
    return sh(["git", "rev-parse", "HEAD"], cwd=d).stdout.strip()


def write_atomic(path, text, newline=None):
    """Write via a temp file in the same folder + os.replace, so a crash never leaves half a
    file. A symlink keeps pointing where it did: the file it points to is replaced."""
    path = os.path.realpath(path)
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=f".{os.path.basename(path)}.")
    try:
        with os.fdopen(fd, "w", newline=newline) as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


# --------------------------------------------------------------------- frontmatter
def set_frontmatter(path, skill):
    with open(path) as f:
        txt = f.read()
    m = re.match(r"---\n(.*?)\n---\n", txt, re.S)
    if not m:
        raise RuntimeError(f"{path}: no frontmatter")
    lines = [l for l in m.group(1).split("\n") if not l.startswith("disable-model-invocation:")]
    out = []
    for l in lines:
        if l.startswith("name:"):
            l = f"name: {skill['name']}"
        elif l.startswith("description:") and skill.get("description"):
            l = "description: " + json.dumps(skill["description"])
        out.append(l)
    if skill["tier"] == "slash":
        out.append("disable-model-invocation: true")
    new = "---\n" + "\n".join(out) + "\n---\n" + txt[m.end():]
    with open(path, "w") as f:
        f.write(new)


# --------------------------------------------------------------------- codex policy
def set_codex_policy(stage, skill):
    path = os.path.join(stage, "agents", "openai.yaml")
    lines = []
    if os.path.exists(path):
        with open(path) as f:
            lines = f.read().split("\n")
    # drop any top-level policy: block (that line and its indented children)
    kept, skipping = [], False
    for l in lines:
        if l.startswith("policy:"):
            skipping = True
        elif skipping and (l.startswith((" ", "\t")) or not l.strip()):
            continue
        else:
            skipping = False
            kept.append(l)
    text = "\n".join(kept).strip("\n")
    if skill["tier"] == "slash":
        text = (text + "\n" if text else "") + "policy:\n  allow_implicit_invocation: false"
    if not text:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text + "\n")


# --------------------------------------------------------------------- build
def build_skill(man, skill, stage_root):
    """Return (staged_dir, error_or_None)."""
    stage = os.path.join(stage_root, skill["name"])
    if skill["source"] == "owned":
        src = os.path.join(ROOT, skill["path"])
    else:
        src = os.path.join(vendor_dir(man, skill["source"]), skill["path"])
    if not os.path.isdir(src):
        return stage, f"source missing: {src}"
    shutil.copytree(src, stage)
    if skill.get("patch"):
        patch = os.path.join(ROOT, skill["patch"])
        r = sh(["git", "apply", "--whitespace=nowarn", "-p1", patch], cwd=stage, check=False)
        if r.returncode != 0:
            return stage, f"patch failed: {skill['patch']}\n{r.stderr.strip()}"
    # Text rewrites on every .md and .yaml file, after the patch: the vendor's prefix is
    # stripped, then the manifest's "rewrite" map (e.g. renamed skills) applies.
    subs = []
    prefix = man.get("strip_prefix", {}).get(skill["source"])
    if prefix:
        subs.append((prefix, ""))
    subs += list(man.get("rewrite", {}).items())
    if subs:
        for dp, _, files in os.walk(stage):
            for fn in files:
                if fn.endswith((".md", ".yaml")):
                    p = os.path.join(dp, fn)
                    with open(p) as f:
                        t = f.read()
                    new = t
                    for old, rep in subs:
                        new = new.replace(old, rep)
                    if new != t:
                        with open(p, "w") as f:
                            f.write(new)
    set_frontmatter(os.path.join(stage, "SKILL.md"), skill)
    set_codex_policy(stage, skill)
    return stage, None


def dirs_equal(a, b, ignore=()):
    cmp = filecmp.dircmp(a, b, ignore=list(ignore))
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    # shallow=False content check
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(dirs_equal(os.path.join(a, d), os.path.join(b, d), ignore) for d in cmp.common_dirs)


def install(man, skill, stage, lock, dry, dest_root):
    dest = os.path.join(dest_root, skill["name"])
    marker = man["marker"]
    if os.path.exists(dest) and not os.path.exists(os.path.join(dest, marker)):
        return "SKIP (exists, not managed by devflow)"
    if os.path.exists(dest) and dirs_equal(stage, dest, ignore=[marker]):
        return "unchanged"
    action = "update" if os.path.exists(dest) else "install"
    if dry:
        return f"would {action}"
    os.makedirs(dest_root, exist_ok=True)
    with open(os.path.join(stage, marker), "w") as f:
        src = skill["source"]
        f.write(json.dumps({"source": src, "path": skill["path"],
                            "commit": lock.get(src, "owned"), "tier": skill["tier"]}) + "\n")
    tmp = dest + ".devflow-new"
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    shutil.copytree(stage, tmp)
    if os.path.exists(dest):
        old = dest + ".devflow-old"
        os.rename(dest, old)
        os.rename(tmp, dest)
        shutil.rmtree(old)
    else:
        os.rename(tmp, dest)
    return action + "d" if action.endswith("e") else action + "ed"


def managed_dirs(man, root):
    if not os.path.isdir(root):
        return []
    return [d for d in sorted(os.listdir(root))
            if os.path.isdir(os.path.join(root, d)) and not os.path.islink(os.path.join(root, d))
            and os.path.exists(os.path.join(root, d, man["marker"]))]


def remove_managed(root, d, why, dry, failures):
    if not dry:
        try:
            shutil.rmtree(os.path.join(root, d))
        except OSError as e:
            failures.append((d, f"could not remove: {e}"))
            return f"FAIL      {d}: could not remove: {e}"
    return f"{'would remove' if dry else 'removed'} {d} ({why})"


def prune(man, dest_root, dry, failures):
    names = {s["name"] for s in man["skills"]}
    return [remove_managed(dest_root, d, "no longer in manifest", dry, failures)
            for d in managed_dirs(man, dest_root) if d not in names]


def cleanup_dirs(man, keep):
    out = []
    for p in man["providers"]:
        if p["skills_dir"] not in keep and p["skills_dir"] not in out:
            out.append(p["skills_dir"])
    return out


def folder_id(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_dev, st.st_ino)


def cleanup(man, tilde_dir, install_ids, dry, failures):
    root = os.path.expanduser(tilde_dir)
    if folder_id(root) in install_ids:
        return ["SKIP (same folder as an install folder)"]
    return [remove_managed(root, d, "provider not selected", dry, failures)
            for d in managed_dirs(man, root)]


# --------------------------------------------------------------------- global config
def tilde(path):
    """`~/...` for a path under HOME (or `~` itself), the path unchanged otherwise."""
    home = os.path.expanduser("~").rstrip(os.sep)
    if home and (path == home or path.startswith(home + os.sep)):
        return "~" + path[len(home):]
    return path


def clone_path():
    """This clone's root as the section header and ignore comment name it."""
    return tilde(ROOT)


def git_ignore_target():
    """The file git reads global excludes from (#37): `core.excludesFile` from the global git
    config, else `$XDG_CONFIG_HOME/git/ignore`, else `~/.config/git/ignore`. ValueError (with
    the reason) when the config can't be read or the value is relative (#37: warn, never break)."""
    try:
        r = subprocess.run(["git", "config", "--global", "--type=path", "--get", "core.excludesFile"],
                           capture_output=True, text=True)
    except OSError as e:
        raise ValueError(f"could not read core.excludesFile ({e})")
    if r.returncode not in (0, 1):
        lines = r.stderr.strip().splitlines()
        raise ValueError(f"could not read core.excludesFile ({lines[0] if lines else 'git exited ' + str(r.returncode)})")
    value = r.stdout.strip() if r.returncode == 0 else ""
    if value:
        if not os.path.isabs(value):
            raise ValueError(f"core.excludesFile is relative ({value})")
        return value
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return os.path.join(xdg, "git", "ignore")
    return os.path.expanduser("~/.config/git/ignore")


def section_bounds(cur):
    """(a, b) for exactly one well-ordered section, None for no markers; ValueError otherwise."""
    starts, ends = cur.count(MD_START), cur.count(MD_END)
    if not starts and not ends:
        return None
    if starts != 1 or ends != 1 or cur.index(MD_END) < cur.index(MD_START):
        raise ValueError("malformed devflow markers")
    return cur.index(MD_START), cur.index(MD_END) + len(MD_END)


def markers_skip(tilde_path):
    return f"SKIP {tilde_path}: devflow markers incomplete, left untouched"


def unreadable_skip(tilde_path):
    return f"SKIP {tilde_path}: unreadable, left untouched"


def sync_instructions(tilde_path, dry):
    path = os.path.expanduser(tilde_path)
    with open(os.path.join(ROOT, "global", "claude-md-section.md")) as f:
        section = f.read().replace("{{clone}}", clone_path()).strip() + "\n"
    cur = ""
    if os.path.exists(path):
        try:
            with open(path, newline="") as f:
                cur = f.read()
        except (UnicodeDecodeError, OSError):
            return unreadable_skip(tilde_path)
    try:
        bounds = section_bounds(cur)
    except ValueError:
        return markers_skip(tilde_path)
    if bounds:
        a, b = bounds
        new = cur[:a] + section.rstrip("\n") + cur[b:]
    else:
        new = (cur.rstrip("\n") + "\n\n" if cur.strip() else "") + section
    if new == cur:
        return f"{tilde_path} devflow section unchanged"
    if not dry:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_atomic(path, new, newline="")
    return f"{'would update' if dry else 'updated'} {tilde_path} devflow section"


def remove_instructions(tilde_path, dry):
    path = os.path.expanduser(tilde_path)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, newline="") as f:
            cur = f.read()
    except (UnicodeDecodeError, OSError):
        return unreadable_skip(tilde_path)
    try:
        bounds = section_bounds(cur)
    except ValueError:
        return markers_skip(tilde_path)
    if bounds is None:
        return None
    a, b = bounds
    if not cur[b:].strip():
        new = cur[:a].rstrip("\n") + "\n" if cur[:a].strip() else ""
    else:
        if cur[b:b + 1] == "\n":
            b += 1
        new = cur[:a] + cur[b:]
    if not dry:
        write_atomic(path, new, newline="")
    return f"{'would remove' if dry else 'removed'} {tilde_path} devflow section"


def sync_git_ignore(dry):
    with open(os.path.join(ROOT, "global", "git-ignore-lines")) as f:
        want = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    manual = "add these lines yourself: " + ", ".join(want)
    try:
        target = git_ignore_target()
    except ValueError as e:
        return f"WARN git ignore: {e}; {manual}"
    shown = tilde(target)
    missing = want  # nothing is known to be present until the file has been read
    try:
        cur = open(target).read() if os.path.exists(target) else ""
        have = {l.strip() for l in cur.splitlines()}
        missing = [l for l in want if l not in have]
        if not missing:
            return f"git ignore lines present in {shown}"
        if not dry:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "a") as f:
                if cur and not cur.endswith("\n"):
                    f.write("\n")
                if "# devflow" not in cur:
                    f.write(f"# devflow (managed by {clone_path()})\n")
                f.write("\n".join(missing) + "\n")
    except OSError as e:
        return (f"WARN git ignore: could not write {shown} ({e.strerror or e}); "
                f"add these lines yourself: {', '.join(missing)}")
    return f"{'would add' if dry else 'added'} to git ignore {shown}: {', '.join(missing)}"


# --------------------------------------------------------------------- commands
def validate_providers(man, names):
    known = [p["name"] for p in man["providers"]]
    if not names:
        sys.exit(f"choose at least one provider (known: {', '.join(known)})")
    out = []
    for n in names:
        if n not in known:
            sys.exit(f"unknown provider: {n} (known: {', '.join(known)})")
        if n not in out:
            out.append(n)
    return out


def selected_providers(man):
    if not os.path.exists(LOCAL):
        return ["claude"]
    try:
        with open(LOCAL) as f:
            names = json.load(f)["providers"]
    except (OSError, ValueError, KeyError, TypeError):
        names = None
    if not isinstance(names, list):
        sys.exit('devflow.local.json: expected {"providers": [...]}')
    return validate_providers(man, names)


def install_dirs(man, selected):
    chosen = [p for p in man["providers"] if p["name"] in selected]
    out = []
    for p in chosen:
        covered = any(q is not p and q["skills_dir"] in p["also_reads"] for q in chosen)
        if not covered and p["skills_dir"] not in out:
            out.append(p["skills_dir"])
    return out


def apply_all(man, lock, dry=False, only_sources=None, selected=None):
    if selected is None:
        selected = selected_providers(man)
    dirs = install_dirs(man, selected)
    print("providers: " + ", ".join(selected))
    for src in man["vendors"]:
        lock[src] = ensure_vendor(man, src, lock.get(src))
    stage_root = tempfile.mkdtemp(prefix="devflow-stage-")
    failures = []
    try:
        built = []
        for skill in man["skills"]:
            if only_sources and skill["source"] not in only_sources:
                continue
            stage, err = build_skill(man, skill, stage_root)
            if err:
                failures.append((skill["name"], err))
            else:
                built.append((skill, stage))
        for i, d in enumerate(dirs):
            print(d)
            if i == 0:
                for name, err in failures:
                    print(f"  FAIL      {name}: {err}")
            for skill, stage in built:
                status = install(man, skill, stage, lock, dry, os.path.expanduser(d))
                print(f"  {status:<10} {skill['name']}  [{skill['tier']}]")
            for line in prune(man, os.path.expanduser(d), dry, failures):
                print("  " + line)
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
    install_ids = {folder_id(os.path.expanduser(d)) for d in dirs} - {None}
    for d in cleanup_dirs(man, dirs):
        lines = cleanup(man, d, install_ids, dry, failures)
        if lines:
            print(d)
            for line in lines:
                print("  " + line)
    print("instructions")
    mine = [p["instructions"] for p in man["providers"] if p["name"] in selected and p["instructions"]]
    for p in man["providers"]:
        f = p["instructions"]
        if not f:
            continue
        if p["name"] in selected:
            status = sync_instructions(f, dry)
        else:
            # never strip a file that is (a link to) a selected provider's file
            fid = folder_id(os.path.expanduser(f))
            same = next((m for m in mine if fid and folder_id(os.path.expanduser(m)) == fid), None)
            if same:
                status = f"SKIP {f}: same file as {same}, left untouched"
            else:
                status = remove_instructions(f, dry)
        if status:
            print("  " + status)
    status = sync_git_ignore(dry)
    print(status if status.startswith("WARN") else "  " + status)  # #37: a WARN starts its line
    for p in man["providers"]:
        if p["name"] in selected and not p["instructions"]:
            print(f"note: {p['name']} reads no instructions file: paste global/claude-md-section.md "
                  "into its rules settings (Cursor: Customize → Rules).")
    return failures


def set_providers(man, lock, csv, dry):
    names = validate_providers(man, [n.strip() for n in csv.split(",") if n.strip()])
    if dry:
        return apply_all(man, lock, dry=True, selected=names)
    write_atomic(LOCAL, json.dumps({"providers": names}, indent=2) + "\n")
    fails = apply_all(man, lock, selected=names)
    save_lock(lock)
    return fails


def update(man, lock):
    selected = selected_providers(man)
    stage_root = tempfile.mkdtemp(prefix="devflow-update-")
    try:
        for src in man["vendors"]:
            old = ensure_vendor(man, src, lock.get(src))
            d = vendor_dir(man, src)
            sh(["git", "fetch", "-q", "origin"], cwd=d)
            new = sh(["git", "rev-parse", "origin/HEAD"], cwd=d, check=False).stdout.strip()
            if not new:
                sh(["git", "remote", "set-head", "origin", "-a"], cwd=d)
                new = sh(["git", "rev-parse", "origin/HEAD"], cwd=d).stdout.strip()
            if new == old:
                print(f"{src}: up to date ({old[:8]})")
                continue
            print(f"{src}: {old[:8]} → {new[:8]}")
            sh(["git", "checkout", "-q", new], cwd=d)
            fails = []
            for skill in man["skills"]:
                if skill["source"] != src:
                    continue
                log = sh(["git", "log", "--oneline", f"{old}..{new}", "--", skill["path"]], cwd=d).stdout.strip()
                if log:
                    print(f"  upstream changes in {skill['name']}:\n    " + log.replace("\n", "\n    "))
                _, err = build_skill(man, skill, os.path.join(stage_root, src))
                if err:
                    fails.append((skill["name"], err))
            if fails:
                print(f"  {src}: {len(fails)} patch(es) no longer apply — keeping lock at {old[:8]}:")
                for n, e in fails:
                    print(f"    {n}: {e}")
                print(f"  Re-port with: sync.sh edit <skill>  (then edit .patch-work/<skill>/b, sync.sh save <skill>)")
                print(f"  Upstream diff: git -C {man['vendors'][src]['dir']} diff {old[:8]} {new[:8]} -- <path>")
                sh(["git", "checkout", "-q", old], cwd=d)
            else:
                lock[src] = new
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
    failures = apply_all(man, lock, selected=selected)
    save_lock(lock)
    return failures


def save_lock(lock):
    with open(LOCK, "w") as f:
        json.dump(lock, f, indent=2)
        f.write("\n")


def find_skill(man, name):
    for s in man["skills"]:
        if s["name"] == name:
            return s
    sys.exit(f"unknown skill: {name}")


def edit(man, lock, name):
    skill = find_skill(man, name)
    if skill["source"] == "owned":
        sys.exit(f"{name} is owned: edit {skill['path']} directly")
    ensure_vendor(man, skill["source"], lock.get(skill["source"]))
    work = os.path.join(ROOT, ".patch-work", name)
    if os.path.exists(work):
        shutil.rmtree(work)
    src = os.path.join(vendor_dir(man, skill["source"]), skill["path"])
    shutil.copytree(src, os.path.join(work, "a"))
    shutil.copytree(src, os.path.join(work, "b"))
    if skill.get("patch") and os.path.exists(os.path.join(ROOT, skill["patch"])):
        sh(["git", "apply", "--whitespace=nowarn", "-p1", os.path.join(ROOT, skill["patch"])],
           cwd=os.path.join(work, "b"), check=False)
    print(f"Edit {work}/b (upstream + current patch), then run: sync.sh save {name}")


def save(man, name):
    skill = find_skill(man, name)
    work = os.path.join(ROOT, ".patch-work", name)
    r = subprocess.run(["diff", "-ruN", "a", "b"], cwd=work, capture_output=True, text=True)
    patch_rel = skill.get("patch") or f"patches/{name}.patch"
    with open(os.path.join(ROOT, patch_rel), "w") as f:
        f.write(r.stdout)
    if not skill.get("patch"):
        print(f"Add \"patch\": \"{patch_rel}\" to {name} in manifest.json")
    print(f"wrote {patch_rel} ({r.stdout.count(chr(10))} lines). Run sync.sh to install.")


def main(argv):
    man, lock = load()
    if argv[:1] == ["edit"] and len(argv) == 2:
        return edit(man, lock, argv[1])
    if argv[:1] == ["save"] and len(argv) == 2:
        return save(man, argv[1])
    dry = argv[-1:] == ["--dry-run"]
    if argv == ["--update"]:
        fails = update(man, lock)
    elif argv in ([], ["--dry-run"]) or (argv[:1] == ["providers"] and len(argv) == 2 + dry):
        print("devflow sync" + (" (dry run)" if dry else ""))
        if argv[:1] == ["providers"]:
            fails = set_providers(man, lock, argv[1], dry)
        else:
            fails = apply_all(man, lock, dry=dry)
            if not dry:
                save_lock(lock)
    else:
        sys.exit(__doc__)
    if fails:
        print(f"\n{len(fails)} skill(s) failed; their previously installed versions were left in place.")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
