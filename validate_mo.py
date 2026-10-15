#!/usr/bin/env python3
"""Validate gettext .mo files changed in a pull request.

Errors (job fails): .mo is not a strictly well-formed catalog, or the PR touches
files outside the allowed pattern, symlinks or executables.
Warnings: .mo does not match the sibling .po, or no .po was found.
"""
import json, os, re, struct, subprocess, sys, tempfile, urllib.request
from pathlib import Path

PATTERN = r"(?:.*/)?lang/(?:.*/)?[^/]+\.(?:po|mo|pot)"
LIMIT = 5


def parse_mo(data: bytes) -> dict[str, str]:
    """Strictly parse a .mo: every byte must belong to the header, a table, or a string."""
    if len(data) < 28: raise ValueError("truncated header")
    end = {b"\xde\x12\x04\x95": "<", b"\x95\x04\x12\xde": ">"}.get(data[:4])
    if not end: raise ValueError("bad magic number")
    rev, n, o, t, s, h = struct.unpack(end + "6I", data[4:28])
    if rev >> 16: raise ValueError(f"unsupported revision {rev}")
    spans = [(0, 28)]
    if s: spans.append((h, h + 4 * s))
    entries = []
    for off in (o, t):
        if off + 8 * n > len(data): raise ValueError("table out of range")
        spans.append((off, off + 8 * n))
        entries.append([struct.unpack_from(end + "2I", data, off + 8 * i) for i in range(n)])
    strings = []
    for table in entries:
        strings.append([])
        for length, off in table:
            if off + length + 1 > len(data) or data[off + length]: raise ValueError("string out of range or not NUL-terminated")
            spans.append((off, off + length + 1))
            strings[-1].append(data[off:off + length].decode("utf-8"))
    pos = 0
    for a, b in sorted(spans):
        if a != pos: raise ValueError(f"{'unreferenced bytes' if a > pos else 'overlapping regions'} at offset {min(a, pos)}")
        pos = b
    if pos != len(data): raise ValueError(f"{len(data) - pos} trailing bytes after offset {pos}")
    return dict(zip(*strings))


def sibling_po(mo: Path) -> Path:
    """`x/ru.mo` -> `x/ru.po`; `lang/mo/<loc>/LC_MESSAGES/<n>.mo` -> `lang/po/<loc>.po`."""
    if mo.parent.name == "LC_MESSAGES" and mo.parents[2].name == "mo": return mo.parents[3] / "po" / f"{mo.parents[1].name}.po"
    return mo.with_suffix(".po")


def compile_po(po: Path) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.mo"
        subprocess.run(["msgfmt", "--check", "-o", out, po], check=True, capture_output=True, text=True)
        return parse_mo(out.read_bytes())


def compare(mo: dict[str, str], po: dict[str, str]) -> str | None:
    missing, extra = sorted(po.keys() - mo.keys()), sorted(mo.keys() - po.keys())
    changed = sorted(k for k in po.keys() & mo.keys() if po[k] != mo[k])
    if not (missing or extra or changed): return None
    pct = 100 * (len(missing) + len(extra) + len(changed)) / len(po.keys() | mo.keys())
    sample = [f"{tag} {k[:60]!r}" for tag, ks in (("missing", missing), ("extra", extra), ("changed", changed)) for k in ks[:LIMIT]]
    return f"differs from .po: {len(missing)} missing, {len(extra)} extra, {len(changed)} changed ({pct:.1f}% of {len(po.keys() | mo.keys())} msgids); " + "; ".join(sample[:LIMIT])


def validate(root: Path, files: list[str], pattern: str = PATTERN) -> tuple[list, list, list]:
    errors, warnings, rows = [], [], []
    for f in files:
        p = root / f
        if not re.fullmatch(pattern, f): errors.append((f, "path outside allowed pattern"))
        elif p.is_symlink(): errors.append((f, "symlink"))
        elif p.stat().st_mode & 0o111: errors.append((f, "executable bit set"))
    for f in (f for f in files if f.endswith(".mo") and (root / f).is_file() and not any(e[0] == f for e in errors)):
        mo = root / f
        try: catalog = parse_mo(mo.read_bytes())
        except ValueError as e:
            errors.append((f, f"invalid .mo: {e}")); rows.append((f, "FAIL", str(e))); continue
        po = sibling_po(mo)
        if not po.is_file():
            warnings.append((f, "no sibling .po to compare against")); rows.append((f, "ok", "no .po")); continue
        try: diff = compare(catalog, compile_po(po))
        except subprocess.CalledProcessError as e:
            warnings.append((f, f"msgfmt rejected {po.name}: {e.stderr.strip()[:300]}")); rows.append((f, "ok", ".po rejected")); continue
        if diff and po.name not in map(os.path.basename, files): diff += " (.po not changed in this PR)"
        if diff: warnings.append((f, diff))
        rows.append((f, "ok", diff or f"{len(catalog)} entries match"))
    return errors, warnings, rows


def pr_files(event: dict, token: str) -> list[str]:
    repo, num, files, page = os.environ["GITHUB_REPOSITORY"], event["pull_request"]["number"], [], 1
    while True:
        req = urllib.request.Request(f"{os.environ.get('GITHUB_API_URL', 'https://api.github.com')}/repos/{repo}/pulls/{num}/files?per_page=100&page={page}", headers={"Authorization": f"Bearer {token}"})
        batch = json.load(urllib.request.urlopen(req))
        files += [f["filename"] for f in batch if f["status"] != "removed"]
        if len(batch) < 100: return files
        page += 1


def esc(s: str) -> str: return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main() -> int:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    files = pr_files(event, os.environ["GITHUB_TOKEN"])
    errors, warnings, rows = validate(Path.cwd(), files, os.environ.get("PATTERN") or PATTERN)
    for level, items in (("error", errors), ("warning", warnings)):
        for f, msg in items: print(f"::{level} file={esc(f)},title=validate-mo::{esc(msg)}")
    summary = "| file | result | detail |\n|---|---|---|\n" + "".join(f"| `{f}` | {r} | {d.replace('|', '\\|')} |\n" for f, r, d in rows)
    if "GITHUB_STEP_SUMMARY" in os.environ: Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a").write(summary)
    print(summary)
    return 1 if errors else 0


if __name__ == "__main__": sys.exit(main())
