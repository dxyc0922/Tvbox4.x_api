#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""便捷维护：把线路加入/移出配置黑名单，然后可选地重跑生成。

用法：
    python scripts/ban_line.py 华谊影视.py --line F蓝光 --line QQ蓝光
    python scripts/ban_line.py 华谊影视.py --line K蓝光 --unban
    python scripts/ban_line.py 华谊影视.py --line F蓝光 --run

只改 scripts/config.json，不直接动脚本文件；线路裁减仍由 update_api 注入。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "scripts" / "config.json"


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8-sig"))


def save_config(data: dict) -> None:
    CONFIG.write_text(
        json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把线路加入/移出配置黑名单")
    parser.add_argument("script", help="脚本文件名，例如 华谊影视.py")
    parser.add_argument("--line", action="append", default=[], help="线路名，可多次")
    parser.add_argument("--unban", action="store_true", help="取消上述加入")
    parser.add_argument("--run", action="store_true", help="改完直接跑 update_api.py")
    args = parser.parse_args(argv)

    data = load_config()
    quality = data.setdefault("quality", {})
    blacklist = quality.setdefault("line_prune", {}).setdefault("blacklist", {})

    flags = set(args.line)
    if not flags:
        print("请至少指定一个 --line")
        return 1
    current = set(blacklist.get(args.script, []))
    if args.unban:
        removed = current & flags
        current -= flags
        changed = bool(removed)
    else:
        added = flags - current
        current |= flags
        changed = bool(added)
    if changed:
        blacklist[args.script] = sorted(current)

    if not changed:
        print("没有变化，未写 config.json")
        return 0
    save_config(data)
    print(f"已更新 {CONFIG}")
    print(json.dumps(quality, ensure_ascii=False, indent=2))

    if args.run:
        return subprocess.call(
            [sys.executable, str(ROOT / "scripts" / "update_api.py")]
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
