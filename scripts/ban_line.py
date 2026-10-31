#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""便捷维护：把源/线路加进配置黑名单或豁免，然后可选地重跑生成。

用法：
    python scripts/ban_line.py 华谊影视.py --line F蓝光 --line QQ蓝光
    python scripts/ban_line.py 低端影视.py --bitrate      # 加入码率豁免
    python scripts/ban_line.py 麒麟影视.py --speed        # 加入速度豁免
    python scripts/ban_line.py 华谊影视.py --line K蓝光 --unban   # 取消
    python scripts/ban_line.py 华谊影视.py --line F蓝光 --run     # 改完直接重跑

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
    data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    return data


def save_config(data: dict) -> None:
    CONFIG.write_text(
        json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把源/线路加进配置黑名单或豁免")
    parser.add_argument("script", help="脚本文件名，例如 华谊影视.py")
    parser.add_argument("--line", action="append", default=[], help="线路名，可多次")
    parser.add_argument("--speed", action="store_true", help="把源加进 speed_allow")
    parser.add_argument("--bitrate", action="store_true", help="把源加进 bitrate_allow")
    parser.add_argument("--unban", action="store_true", help="取消上述加入")
    parser.add_argument("--run", action="store_true", help="改完直接跑 update_api.py")
    args = parser.parse_args(argv)

    data = load_config()
    quality = data.setdefault("quality", {})
    line_prune = quality.setdefault("line_prune", {})
    blacklist = line_prune.setdefault("blacklist", {})
    speed_allow = set(quality.setdefault("speed_allow", []))
    bitrate_allow = set(quality.setdefault("bitrate_allow", []))

    changed = False

    def _set(items: set, name: str) -> None:
        nonlocal changed
        if args.unban:
            if name in items:
                items.discard(name)
                changed = True
        else:
            if name not in items:
                items.add(name)
                changed = True

    if args.speed:
        _set(speed_allow, args.script)
    if args.bitrate:
        _set(bitrate_allow, args.script)

    flags = set(args.line)
    if flags:
        current = set(blacklist.get(args.script, []))
        if args.unban:
            removed = current & flags
            current -= flags
            blacklist[args.script] = sorted(current)
            changed = bool(removed) or changed
        else:
            added = flags - current
            current |= flags
            blacklist[args.script] = sorted(current)
            changed = bool(added) or changed

    quality["speed_allow"] = sorted(speed_allow)
    quality["bitrate_allow"] = sorted(bitrate_allow)

    if not changed:
        print("没有变化，未写 config.json")
        return 0
    save_config(data)
    print(f"已更新 {CONFIG}")
    print(json.dumps(data["quality"], ensure_ascii=False, indent=2))

    if args.run:
        code = subprocess.call(
            [sys.executable, str(ROOT / "scripts" / "update_api.py")]
        )
        return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
