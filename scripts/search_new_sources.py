# -*- coding: utf-8 -*-
"""每周搜索 GitHub 找新可用 TVBox 源仓库。

用户方向6：项目不依赖固定仓库——若删库/分支变动，重新按关键字搜 GitHub
收集新源。应**每周主动搜一次** GitHub，发现新可用来源加入候选。

流程：
1. 读 config.json 现有 upstream（排除已接入的）。
2. GitHub 搜索仓库（多关键词：tvbox / TVBox接口 / 影视源 / spider 等）。
3. 排除现有仓库；筛选最近活跃 + 有 py 脚本的。
4. 对候选查 git/trees 找 py 目录，输出建议加入的 upstream。

用法：
    python scripts/search_new_sources.py            # 搜索 + 输出建议
    python scripts/search_new_sources.py --dry-run  # 只打印候选，不写建议
环境变量 GITHUB_TOKEN 可提高搜索限额（匿名 10 req/min）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_api  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "scripts" / "config.json"
OUTPUT = ROOT / "reports" / "new-source-candidates.json"

# 搜索关键词：TVBox 源仓库常见命名。每个都会搜，去重。
SEARCH_KEYWORDS = [
    "tvbox 接口",
    "TVBox 影视源",
    "tvbox spider",
    "TVBox cms",
    "影视 采集 源",
    "tvbox 配置",
]

# 只考虑最近活跃的仓库（天内）
MAX_AGE_DAYS = 60
# 候选里最多查 trees 的仓库数（限速）
MAX_PROBE = 12


def github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "User-Agent": "Tvbox4.x_api-search/1.0",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def search_repos(keyword: str, token: str | None, per_page: int = 30) -> list[dict[str, Any]]:
    """GitHub 搜索仓库，按最近更新排序。"""
    q = urllib.parse.quote(f"{keyword} in:name,description")
    url = (
        f"https://api.github.com/search/repositories?q={q}"
        f"&sort=updated&order=desc&per_page={per_page}"
    )
    try:
        r = requests.get(url, headers=github_headers(token), timeout=15)
        if r.status_code == 403:
            print(f"  !! 搜索限流（{keyword}）: {r.headers.get('X-RateLimit-Remaining')} 剩余",
                  file=sys.stderr)
            return []
        r.raise_for_status()
        return list((r.json() or {}).get("items") or [])
    except requests.RequestException as exc:
        print(f"  !! 搜索失败（{keyword}）: {exc}", file=sys.stderr)
        return []


def probe_py_dir(
    owner: str, repo: str, branch: str, token: str | None
) -> tuple[str | None, int]:
    """查仓库 git/trees，找含 .py 脚本的目录（path + py 文件数）。"""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    try:
        r = requests.get(url, headers=github_headers(token), timeout=15)
        if r.status_code != 200:
            return None, 0
        tree = (r.json() or {}).get("tree") or []
    except (requests.RequestException, ValueError):
        return None, 0
    py_by_dir: dict[str, int] = {}
    for item in tree:
        path = str(item.get("path") or "")
        if path.lower().endswith(".py"):
            dirname = path.rsplit("/", 1)[0] if "/" in path else ""
            py_by_dir[dirname] = py_by_dir.get(dirname, 0) + 1
    if not py_by_dir:
        return None, 0
    # 取 py 最多的目录（TVBox 源通常在 py/ 或根目录）
    best_dir, best_count = max(py_by_dir.items(), key=lambda kv: kv[1])
    return (best_dir or None, best_count)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="搜索 GitHub 新 TVBox 源仓库")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--max-probe", type=int, default=MAX_PROBE)
    parser.add_argument("--max-age-days", type=int, default=MAX_AGE_DAYS)
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写建议")
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN") or ""
    config = update_api.load_config(Path(args.config))
    existing = {
        f"{u['owner']}/{u['repo']}".lower()
        for u in (config.get("upstream") or [])
        if isinstance(u, dict)
    }
    print(f"现有上游: {len(existing)} 个")
    for u in existing:
        print(f"  - {u}")

    # 1) 搜索各关键词收集候选
    seen: dict[str, dict[str, Any]] = {}
    for kw in SEARCH_KEYWORDS:
        print(f"\n搜索: {kw}")
        items = search_repos(kw, token)
        for it in items:
            full = f"{it.get('full_name', '')}".lower()
            if full in existing:
                continue
            if full not in seen:
                seen[full] = it
        print(f"  候选 {len(items)} 条（累计去重 {len(seen)}）")
        time.sleep(2)  # 限速：匿名搜索 10 req/min

    # 2) 筛选最近活跃
    now = time.time()
    cutoff = now - args.max_age_days * 86400
    active: list[dict[str, Any]] = []
    for full, it in seen.items():
        pushed = it.get("pushed_at") or ""
        try:
            ts = time.mktime(time.strptime(pushed[:19], "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, TypeError):
            ts = 0
        if ts >= cutoff:
            active.append(it)
    active.sort(key=lambda it: it.get("stargazers_count", 0), reverse=True)
    print(f"\n最近 {args.max_age_days} 天活跃候选: {len(active)} 个")

    # 3) 对前 N 个查 py 目录
    suggestions: list[dict[str, Any]] = []
    # 排除明显不是「源仓库」的（播放器壳/不带内容源/客户端）
    NOT_SOURCE_RE = [
        "播放器", "不带任何内容源", "客户端", "播放器壳", "声明式源配置",
        "安卓播放器", "不带源", "不包含任何", "纯播放器",
    ]
    for it in active[: args.max_probe]:
        owner_repo = it.get("full_name", "")
        if "/" not in owner_repo:
            continue
        owner, repo = owner_repo.split("/", 1)
        default_branch = it.get("default_branch") or "main"
        desc = str(it.get("description") or "")
        if any(k in desc for k in NOT_SOURCE_RE):
            print(f"  跳过（非源仓库）: {owner_repo} — {desc[:50]}")
            continue
        print(f"  探测 {owner_repo}（star {it.get('stargazers_count')}）...")
        py_dir, py_count = probe_py_dir(owner, repo, default_branch, token)
        if py_count >= 3:  # 至少 3 个 py 才算源仓库
            sugg = {
                "owner": owner,
                "repo": repo,
                "branch": default_branch,
                "path": py_dir or "",
                "py_count": py_count,
                "stars": it.get("stargazers_count", 0),
                "pushed_at": it.get("pushed_at"),
                "description": desc[:120],
            }
            suggestions.append(sugg)
            print(f"    ✓ 有 {py_count} 个 py，建议 path={py_dir or '.'}")
        else:
            print(f"    ✗ py 太少（{py_count}），跳过")
        time.sleep(1)

    # 4) 输出建议
    print(f"\n=== 建议加入的新上游（{len(suggestions)} 个）===")
    for s in suggestions:
        print(f"  {s['owner']}/{s['repo']}  branch={s['branch']}  "
              f"path={s['path'] or '.'}  py={s['py_count']}  star={s['stars']}")
        print(f"    {s['description']}")

    if not args.dry_run and suggestions:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps({"suggestions": suggestions}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n建议写入: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
