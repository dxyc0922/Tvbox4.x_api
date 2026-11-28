# -*- coding: utf-8 -*-
"""需第三方解析的平台线路识别（严格过滤：这类线路在 TVBox 里播不了）。

腾讯/爱奇艺/优酷/芒果/哔哩哔哩等平台线路给的是**平台播放页**（playerContent
返回 ``parse=1`` 或解析失败返回空 url），依赖 TVBox 内置解析器/第三方解析接口。
本项目的使用环境没有内置解析器，这类线路等于不可播，应按资源站线路同样剔除。

判定信号（任一命中即算需解析线路）：
1. 采样证据：``parse == 1`` 或 ``resolve_failed``（解析失败返回空 url）。
2. 播放地址落在平台播放页域名（v.qq.com / iqiyi.com / youku.com ...）。
3. 线路名是平台名（腾讯 / 爱奇艺 / 优酷 ...）——覆盖只声明未采样到的线路。

判定粒度与 resource_station 一致：混合源只剔需解析线路，全部线路不可播时整源剔除。
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# 平台线路名（`from` 值或线路 tab 名）。只收平台播放页类，不收 m3u8 直链类。
PLATFORM_FLAG_NAMES: tuple[str, ...] = (
    "腾讯", "腾讯视频", "qq",
    "爱奇艺", "爱奇艺视频", "iqiyi", "qiyi",
    "优酷", "优酷视频", "youku",
    "芒果TV", "芒果", "mgtv",
    "哔哩哔哩", "B站", "bilibili",
    "搜狐视频", "乐视视频", "PPTV", "咪咕视频", "央视频", "华数",
)

# 平台播放页域名（不是平台 CDN，CDN 直链属于可播线路，不在此列）。
PLATFORM_PAGE_HOSTS: tuple[str, ...] = (
    "v.qq.com", "film.qq.com",
    "iqiyi.com", "qiyipic.com",
    "youku.com",
    "mgtv.com",
    "bilibili.com", "b23.tv",
    "sohu.com", "le.com", "pptv.com", "miguvideo.com", "cntv.cn", "wasu.com",
)


def _host(url: str) -> str:
    m = re.match(r"https?://([^/?]+)", str(url or ""))
    return m.group(1).split(":")[0].lower() if m else ""


def match_parse_required(
    url: str, flag: str = "", parse: Any = None, resolve_failed: bool = False
) -> str:
    """判定一条线路是否需第三方解析，返回命中的签名（可播返回空串）。"""
    try:
        need_parse = int(parse) == 1
    except (TypeError, ValueError):
        need_parse = False
    if need_parse:
        return "需内置解析(parse=1)"
    if resolve_failed:
        return "解析失败(空url)"
    host = _host(url)
    if host:
        for page in PLATFORM_PAGE_HOSTS:
            if host == page or host.endswith("." + page):
                return f"平台播放页({host})"
    f = str(flag or "")
    for name in PLATFORM_FLAG_NAMES:
        if name.lower() in f.lower():
            return f"平台线路({name})"
    return ""


def classify_source(
    entries: Iterable[dict[str, Any]],
    declared_flags: Iterable[str] | None = None,
    declared_total: int = 0,
) -> dict[str, Any]:
    """统计一个源的需解析线路，判定是否「整源不可播」。

    与 resource_station.classify_source 同样的口径：优先看完整声明名单，
    避免采样只看前 4 条时把混有自有线路的源误判。
    """
    rows = list(entries or [])
    flags: set[str] = set()
    detail: list[tuple[str, str]] = []
    for row in rows:
        flag = str(row.get("flag") or "").strip()
        sig = match_parse_required(
            str(row.get("url") or ""),
            flag,
            row.get("parse"),
            bool(row.get("resolve_failed")),
        )
        if sig and flag:
            flags.add(flag)
            detail.append((flag, sig))
    declared = [
        str(x).strip() for x in (declared_flags or []) if str(x or "").strip()
    ]
    declared_parse = {
        f for f in declared if match_parse_required("", f)
    }
    if declared:
        pure = len(declared_parse) == len(declared)
    elif int(declared_total or 0) > len(rows):
        pure = False
    else:
        pure = bool(rows) and len(flags) == len(rows)
    return {
        "flags": sorted(flags),
        "declared_flags": sorted(declared_parse),
        "detail": detail,
        "pure": pure,
        "n_declared": len(declared) or int(declared_total or 0),
        "n_declared_parse": len(declared_parse),
        "n_sampled": len(rows),
    }


def runtime_signatures() -> dict[str, Any]:
    """供 update_api 内联到脚本的运行时签名（按线路名/播放页域名兜底）。"""
    return {
        "names": list(PLATFORM_FLAG_NAMES),
        "hosts": list(PLATFORM_PAGE_HOSTS),
    }
