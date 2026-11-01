# -*- coding: utf-8 -*-
"""动态功能校验关键词：从豆瓣.py categoryContent 拿最新动漫/剧集，生成降级搜索链。

用户标准：固定测旧片（庆余年等）等于没测——源的新旧影视画质/卡顿不同。
改为从豆瓣.py 的 categoryContent 拿**非凡动漫（tid=29）/非凡新剧集（tid=13）**
最新条目名，用这些**最新名称**去搜各源。同一作品在不同源名称可能不同
（"沧元图"/"沧元图 第3季"/"沧元图年番"），搜不到时按降级链回退到基础名
（"沧元图第3季" → "沧元图"）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# 豆瓣.py 在仓库 脚本/ 目录
DOUBAN_SCRIPT = Path(__file__).resolve().parent.parent / "脚本" / "豆瓣.py"
SHIM_DIR = Path(__file__).resolve().parent / "spider_shim"

# 分类 id：非凡动漫 / 非凡新剧集（豆瓣.py homeContent 里定义）
ANIME_TID = "29"
DRAMA_TID = "13"


def degrade_chain(name: str) -> list[str]:
    """生成一个作品名的降级链（原名称在前，基础名在后）。

    例："沧元图第3季" → ["沧元图第3季", "沧元图"]
        "大理寺日志第三季" → ["大理寺日志第三季", "大理寺日志"]
        "动态漫画·全民诡异：开局掌握零元购" → ["动态漫画·全民诡异：开局掌握零元购"]
        副标题（·/：）不去掉，避免降级过宽误匹配；只去季数/集数/年番等后缀。
    """
    chain: list[str] = []
    cur = str(name).strip()
    if not cur:
        return chain
    chain.append(cur)

    # 1) 去 "第X季/集/部/期"（中文/数字）
    prev = None
    while prev != cur:
        prev = cur
        cur = re.sub(
            r"第\s*[0-9一二三四五六七八九十百零\d]+\s*[季集部期话]", "", cur
        ).strip()
    if cur and cur != chain[-1]:
        chain.append(cur)

    # 2) 去 "X季" / "X 季"（如 "沧元图3" / "沧元图 3" / "沧元图 第3季" 剩余）
    prev = None
    while prev != cur:
        prev = cur
        cur = re.sub(r"[\s\-_]*[0-9一二三四五六七八九十百\d]+\s*季", "", cur).strip()
    if cur and cur != chain[-1]:
        chain.append(cur)

    # 3) 去 年番/全集/完整版/国语/粤语 等后缀
    for suf in ("年番", "全集", "完整版", "国语", "粤语", "普通话"):
        if cur.endswith(suf) and len(cur) > len(suf):
            cur = cur[: -len(suf)].strip()
            if cur and cur != chain[-1]:
                chain.append(cur)
            break

    # 4) 去尾随空格/数字（如 "沧元图 3" 剩余空格）
    m = re.sub(r"[\s\-_]+$", "", cur).strip()
    if m and m != chain[-1]:
        chain.append(m)

    # 去重保持顺序
    seen: set[str] = set()
    result: list[str] = []
    for item in chain:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _load_douban_spider() -> Any | None:
    """import 豆瓣.py，返回其 Spider 类（需 shim 提供 base.spider）。"""
    import importlib.util
    import sys

    shim = str(SHIM_DIR)
    if shim not in sys.path:
        sys.path.insert(0, shim)
    spec = importlib.util.spec_from_file_location("douban_dynamic", DOUBAN_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:  # noqa: BLE001
        return None
    # 豆瓣.py 的类名也是 Spider（class Spider(Spider)），取定义在该模块的
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if (
            isinstance(obj, type)
            and getattr(obj, "__module__", "") == "douban_dynamic"
            and hasattr(obj, "categoryContent")
        ):
            return obj
    return None


def fetch_latest_names(anime_count: int = 3, drama_count: int = 3) -> list[str]:
    """从豆瓣.py categoryContent 拿最新动漫+剧集名。

    返回前 anime_count 个最新动漫 + 前 drama_count 个最新剧集名。
    """
    spider_cls = _load_douban_spider()
    if spider_cls is None:
        return []
    try:
        spider = spider_cls()
        spider.init("")
    except Exception:  # noqa: BLE001
        return []
    names: list[str] = []
    for tid, count in ((ANIME_TID, anime_count), (DRAMA_TID, drama_count)):
        try:
            result = spider.categoryContent(tid, "1", False, None)
            lst = (result or {}).get("list") or []
            for item in lst[:count]:
                name = str((item or {}).get("vod_name") or "").strip()
                if name and name not in names:
                    names.append(name)
        except Exception:  # noqa: BLE001
            continue
    return names


def keyword_chains(names: list[str] | None = None, anime_count: int = 3, drama_count: int = 3) -> list[list[str]]:
    """生成降级搜索链：[[原词, 降级词...], ...]。

    优先用传入 names（调试），否则动态从豆瓣拿。每个作品名展开 degrade_chain。
    """
    if not names:
        names = fetch_latest_names(anime_count, drama_count)
    chains: list[list[str]] = []
    for name in names:
        chain = degrade_chain(name)
        if chain:
            chains.append(chain)
    return chains


if __name__ == "__main__":
    # 自测：打印当前最新作品名 + 降级链
    import json

    print("豆瓣.py:", DOUBAN_SCRIPT)
    print("最新名:", fetch_latest_names())
    print()
    print("降级链示例:")
    for example in ["沧元图第3季", "沧元图 第三季", "大理寺日志第三季", "动态漫画·全民诡异：开局掌握零元购"]:
        print(f"  {example} -> {degrade_chain(example)}")
