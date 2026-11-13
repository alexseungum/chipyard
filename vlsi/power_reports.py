#!/usr/bin/env python3
import glob
import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Tuple

DEFAULTS = {"power.reports.blocks": []}
TYPES = {"power.reports.blocks": "list[dict[str, str]]"}

NUM = re.compile(r"^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$")
COMPONENTS = ("leakage", "internal", "switching", "total")


class Power(NamedTuple):
    cells: int
    leakage: float
    internal: float
    switching: float
    total: float


def parse_joules_hier(path: str) -> Tuple[str, Dict[str, Power]]:
    rows: Dict[str, Power] = {}
    top = ""
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) < 8 or not p[7].startswith("/") or not all(NUM.match(x) for x in p[2:7]):
                continue
            rows[p[7]] = Power(int(p[0]), *(float(x) for x in p[2:6]))
            if not top:
                top = p[7]
    return top, rows


def parse_joules_categories(path: str) -> List[Tuple[str, Power]]:
    out = []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) == 6 and p[0] != "Subtotal" and all(NUM.match(x) for x in p[1:5]) and p[5].endswith("%"):
                out.append((p[0], Power(0, *(float(x) for x in p[1:5]))))
    return out


def glob_to_re(pattern: str) -> re.Pattern:
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + "$")


def match_blocks(top: str, rows: Dict[str, Power], block: Dict[str, str]) -> List[Tuple[str, Power]]:
    inst = block.get("inst", "").strip("/")
    full = top + ("/" + inst if inst else "")
    rx = glob_to_re(full)
    ex = glob_to_re(top + "/" + block["exclude"].strip("/")) if block.get("exclude") else None
    return [(k, v) for k, v in rows.items() if rx.match(k) and not (ex and ex.match(k))]


def summed(matches: List[Tuple[str, Power]]) -> Power:
    return Power(*(sum(getattr(v, f) for _, v in matches) for f in Power._fields))


def block_rows(top: str, rows: Dict[str, Power], blocks: List[Dict[str, str]]) -> List[Tuple[str, int, Power, str]]:
    out = [("total", 1, rows[top], top)]
    for b in blocks:
        name = b["name"]
        mode = b.get("mode", "sum")
        matches = sorted(match_blocks(top, rows, b))
        if not matches:
            out.append((name, 0, Power(0, 0.0, 0.0, 0.0, 0.0), "no match: " + b.get("inst", "")))
            continue
        if mode == "each":
            for k, v in matches:
                out.append((f"{name}[{k.rsplit('/', 1)[1]}]", 1, v, k))
        elif mode == "stats":
            n = len(matches)
            s = summed(matches)
            out.append((f"{name}(sum)", n, s, b.get("inst", "")))
            out.append((f"{name}(mean)", n, Power(s.cells // n, *(getattr(s, f) / n for f in COMPONENTS)), b.get("inst", "")))
            lo = min(matches, key=lambda kv: kv[1].total)
            hi = max(matches, key=lambda kv: kv[1].total)
            out.append((f"{name}(min)", 1, lo[1], lo[0]))
            out.append((f"{name}(max)", 1, hi[1], hi[0]))
        else:
            out.append((name, len(matches), summed(matches), matches[0][0] if len(matches) == 1 else b.get("inst", "")))
    return out


def rule(width: int) -> str:
    return "  " + "-" * width


def write_blocks(path: str, src: str, top: str, rows: List[Tuple[str, int, Power, str]]) -> None:
    total = rows[0][2].total or 1.0
    w = max(len(r[0]) for r in rows) + 2
    with open(path, "w") as f:
        f.write(f"Source: {src}\nInstance: {top}\nPower Unit: mW\n")
        f.write(rule(w + 52) + "\n")
        f.write(f"  {'Block':<{w}}{'Count':>8}{'Cells':>10}{'Total':>14}{'Top%':>9}   Instance\n")
        f.write(rule(w + 52) + "\n")
        for name, n, p, inst in rows:
            f.write(f"  {name:<{w}}{n:>8}{p.cells:>10}{p.total:>14.5e}{100 * p.total / total:>8.2f}%   {inst}\n")
        f.write(rule(w + 52) + "\n")


def write_components(path: str, src: str, top: str, rows: List[Tuple[str, int, Power, str]]) -> None:
    w = max(len(r[0]) for r in rows) + 2
    with open(path, "w") as f:
        f.write(f"Source: {src}\nInstance: {top}\nPower Unit: mW\n")
        f.write(rule(w + 84) + "\n")
        f.write(f"  {'Block':<{w}}{'Leakage':>14}{'Internal':>14}{'Switching':>14}{'Total':>14}{'Leak%':>9}{'Int%':>9}{'Sw%':>9}\n")
        f.write(rule(w + 84) + "\n")
        for name, _, p, _ in rows:
            t = p.total or 1.0
            f.write(f"  {name:<{w}}{p.leakage:>14.5e}{p.internal:>14.5e}{p.switching:>14.5e}{p.total:>14.5e}"
                    f"{100 * p.leakage / t:>8.2f}%{100 * p.internal / t:>8.2f}%{100 * p.switching / t:>8.2f}%\n")
        f.write(rule(w + 84) + "\n")


def write_category_table(f, cats: List[Tuple[str, Power]]) -> None:
    total = sum(p.total for _, p in cats) or 1.0
    f.write(rule(74) + "\n")
    f.write(f"  {'Category':<12}{'Leakage':>14}{'Internal':>14}{'Switching':>14}{'Total':>14}{'Row%':>8}\n")
    f.write(rule(74) + "\n")
    for name, p in cats:
        f.write(f"  {name:<12}{p.leakage:>14.5e}{p.internal:>14.5e}{p.switching:>14.5e}{p.total:>14.5e}{100 * p.total / total:>7.2f}%\n")
    f.write(rule(74) + "\n")
    s = summed(cats)
    f.write(f"  {'Subtotal':<12}{s.leakage:>14.5e}{s.internal:>14.5e}{s.switching:>14.5e}{s.total:>14.5e}{100.0:>7.2f}%\n")
    f.write(rule(74) + "\n")


def write_categories(path: str, src: str, top: str, cats: List[Tuple[str, Power]], tool: str, runtime_s: Optional[float]) -> None:
    with open(path, "w") as f:
        f.write(f"Source: {src}\nInstance: {top}\nPower Unit: mW\n")
        if runtime_s is not None:
            s = int(round(runtime_s))
            f.write(f"{tool} runtime: {s} s ({s // 3600}:{s // 60 % 60:02d}:{s % 60:02d})\n")
        write_category_table(f, cats)


def category_blocks(blocks: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out, seen = [], set()
    for b in blocks:
        inst = b.get("inst", "").strip("/")
        if b.get("mode", "sum") != "sum" or not inst or any(c in inst for c in "*?") or b["name"] in seen:
            continue
        seen.add(b["name"])
        out.append(b)
    return out


def write_block_categories(base: str, top: str, blocks: List[Dict[str, str]]) -> bool:
    sections = []
    for b in category_blocks(blocks):
        src = f"{base}.cat.{b['name']}.rpt"
        if os.path.isfile(src):
            cats = parse_joules_categories(src)
            if cats:
                sections.append((b["name"], top + "/" + b["inst"].strip("/"), src, cats))
    if not sections:
        return False
    with open(base + ".blockcats.rpt", "w") as f:
        f.write(f"Instance: {top}\nPower Unit: mW\n")
        for name, inst, src, cats in sections:
            f.write(f"\nBlock: {name}\nSource: {src}\nInstance: {inst}\n")
            write_category_table(f, cats)
    return True


def write_joules_reports(reports_dir: str, stem: str, blocks: List[Dict[str, str]], runtime_s: Optional[float]) -> bool:
    base = os.path.join(reports_dir, stem)
    hier, cat = base + ".hier.power.rpt", base + ".power.rpt"
    if not (os.path.isfile(hier) and os.path.isfile(cat)):
        return False
    top, rows = parse_joules_hier(hier)
    if not top:
        return False
    brows = block_rows(top, rows, blocks)
    write_blocks(base + ".blocks.rpt", hier, top, brows)
    write_components(base + ".components.rpt", hier, top, brows)
    write_categories(base + ".categories.rpt", cat, top, parse_joules_categories(cat), "Joules", runtime_s)
    write_block_categories(base, top, blocks)
    return True


def joules_stems(reports_dir: str, newer_than: float = 0.0) -> List[str]:
    out = []
    for p in sorted(glob.glob(os.path.join(reports_dir, "*.hier.power.rpt"))):
        if os.path.getmtime(p) >= newer_than:
            out.append(os.path.basename(p)[:-len(".hier.power.rpt")])
    return out


def load_blocks(yml: str) -> List[Dict[str, str]]:
    import yaml
    with open(yml) as f:
        d = yaml.safe_load(f) or {}
    if "power.reports.blocks" in d:
        return d["power.reports.blocks"] or []
    return ((d.get("power") or {}).get("reports") or {}).get("blocks") or []


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print(f"usage: {argv[0]} <reports_dir> <blocks.yml> [runtime_s]", file=sys.stderr)
        return 2
    runtime = float(argv[3]) if len(argv) > 3 else None
    blocks = load_blocks(argv[2])
    stems = joules_stems(argv[1])
    for stem in stems:
        write_joules_reports(argv[1], stem, blocks, runtime)
    return 0 if stems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
