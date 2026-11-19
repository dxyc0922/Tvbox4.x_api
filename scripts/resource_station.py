# -*- coding: utf-8 -*-
"""资源站线路检测（严格过滤：资源站线路 = 低质源，剔除）。

项目定位是**剔除低质源**，不是聚合影视源。实测发现大量保留源的线路是
**资源站（采集站）线路**——线路名直接叫资源站名（量子 LZ / 非凡 FF / 暴风 BF /
魔都 / 极速 / 最大 / 蜗牛 / 影库 / 红牛 / 新浪 / 光速 / 如意 / 电影天堂 / 360），
播放 m3u8 也由资源站 CDN 分发（ffzy / yzzy / cdnlz / rrcdnbf / fengbao /
modujx / jisuzy / zuidazy / wsyzym3u8 / xluuss / bfvvs / dytt / phimgood /
gsuus ...）。这类线路内容来自第三方采集站聚合，质量不可控（转码/压缩/失效），
用户判定「基本是低质源」，严格过滤应剔除。

三个判定信号（任一命中即算资源站线路）：
1. **采集站 API**：线路资源地址是 macCMS/苹果CMS 采集接口 ``api.php/provide/vod``。
2. **播放 CDN**：采样到的播放地址由已知资源站 CDN 分发（按 host 特征匹配）。
3. **线路名**：flag 含资源站名关键词（``资源`` 或量子/非凡/暴风/魔都/极速...）。

判定粒度：
- **纯资源站源**：所有视频线路都是资源站 → 整源剔除（无自有线路可留）。
- **混合源**：只剔资源站线路，保留自有线路。
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# --- 1) 采集站 API 签名（macCMS/苹果CMS 资源站采集接口）---
# 这类脚本（AI资源站.py / 采集综合.py）把一堆采集站 API 当线路，是最典型的资源站聚合。
ZY_API_RE = re.compile(
    r"/api\.php/(provide|providedown)|/inc/api_mac|provide/vod|providedown/vod",
    re.I,
)

# --- 2) 资源站播放 CDN host 特征（按资源站名拼音）---
# 只收录命名明确的资源站 CDN。少数混淆域名在用户确认归属后才收录（rstu6=索尼）；
# 其余仍不收录（qqqrst / ppqrrs / hhuus 等），避免把非资源站线路误判。
# 签名表可配置扩展（宁可漏判也不错判）。
ZY_CDN_PATTERNS: tuple[str, ...] = (
    "ffzy", "feifei",        # 非凡资源
    "yzzy", "cdnlz", "lzzy",  # 量子资源（lz=量子）/ 最大资源
    "bfzy", "rrcdnbf", "fengbao",  # 暴风资源 / 疯包
    "modujx", "modudm", "mujizybf",  # 魔都
    "jisuzy", "jisuzyv",     # 极速资源
    "zuidazy",               # 最大资源
    "wsyzym3u8",             # 蜗牛资源
    "xluuss",                # 新浪资源
    "bfvvs",                 # 红牛资源
    "dytt", "phimgood",      # 电影天堂
    "ryiplay", "ryplay", "ruyijx",  # 如意
    "gsuus", "guangsuzy",    # 光速资源
    "maowushi",              # 猫屋资源
    "ukuzi", "niuniuzy",     # uku / 牛牛资源
    "rstu6",                 # 索尼（混淆域名，用户确认归属）
)
# 只要求**左边界**（host 开头或 `.`/`-` 之后）：资源站 CDN 常带数字后缀
# （rrcdnbf6 / yzzy31 / fengbao13 / modujx10 / cdnlz14 / ruiplay18），若也要求右
# 边界会把带数字的域名漏判。左边界已足够避免 myffzyshop.com 这类误报。
ZY_CDN_RE = re.compile(
    r"(^|[.\-_])(?:%s)" % "|".join(re.escape(p) for p in ZY_CDN_PATTERNS),
    re.I,
)

# --- 3) 线路名（flag）资源站关键词 ---
# 资源站线路常直接以资源站命名（1080资源 / 极速资源 / 蜗牛资源 / 影库资源 /
# 红牛资源 / 新浪资源 / 量子资源 / 最大资源 / 暴风资源 / 魔都线路 / 暴风线路 /
# 非凡线路 / FF线路 / LZ线路 / BF线路 / 电影天堂 / 360）。
ZY_FLAG_KEYWORDS: tuple[str, ...] = (
    "资源",                       # 最显式：名字里带「资源」即资源站线路
    "量子", "非凡", "暴风", "魔都", "极速", "最大", "蜗牛", "影库",
    "红牛", "新浪", "光速", "如意", "卧龙", "无界", "人尽", "牛牛",
    "猫屋", "电影天堂", "天堂", "360", "1080", "4K资源",
    "索尼",
)
# 两字母资源站缩写（LZ=量子 FF=非凡 BF=暴风 YZ=云智 DY=DYTT），只匹配「缩写+线路/线」
# 组合，避免 OFF / FFF 之类误报。
ZY_FLAG_CODE_RE = re.compile(
    r"(?i)\b(LZ|FF|BF|YZ|DY|DYTT|LZL|YZL|FFL|BFL)(?:线路|线)\b"
)


def _host(url: str) -> str:
    """取 URL 的 host（去端口、小写）。"""
    m = re.match(r"https?://([^/]+)", url or "")
    if not m:
        return ""
    return m.group(1).split(":")[0].lower()


def match_resource_station(url: str, flag: str = "") -> str:
    """判定一条线路是否为资源站线路，返回命中的签名（非资源站返回空串）。

    优先看采集站 API（最确定），再看播放 CDN host，最后看线路名。
    """
    url = str(url or "")
    flag = str(flag or "")
    api_url = url
    if ZY_API_RE.search(api_url):
        return "采集站API"
    host = _host(url)
    if host and ZY_CDN_RE.search(host):
        return f"资源站CDN({host})"
    for kw in ZY_FLAG_KEYWORDS:
        if kw in flag:
            return f"资源站名({kw})"
    if ZY_FLAG_CODE_RE.search(flag):
        return f"资源站缩写({flag.strip()})"
    return ""


def classify_source(
    line_streams: Iterable[dict[str, Any]],
    video_kinds: Iterable[str] = ("m3u8", "mp4", "hls", "flv"),
) -> dict[str, Any]:
    """统计一个源的资源站线路占比，返回判定结果。

    只统计**视频线路**（kind ∈ video_kinds）；音频线路（audio）不参与——
    听书/音乐源本质不同，不按资源站判。无视频线路时 pure=False（不误剔）。

    返回字段：
    - n_video：视频线路数（没采到的按 0）
    - n_z：其中资源站线路数
    - pure：视频线路**全部**是资源站（n_video>0 且 n_z==n_video）
    - z_flags：资源站线路的 flag 列表（用于报告）
    - video_flags：全部视频线路的 flag 集合（护栏用：剔完不能删空）
    - detail：每条资源站线路的 (flag, 签名)
    """
    kinds = set(video_kinds)
    n_video = 0
    n_z = 0
    z_flags: list[str] = []
    video_flags: list[str] = []
    detail: list[tuple[str, str]] = []
    for entry in line_streams or []:
        stream = entry.get("stream") or {}
        kind = str(stream.get("kind") or "")
        if kind and kind not in kinds:
            continue
        if not kind:
            # kind 未知（未测出）：不统计，避免把未验证线路算成视频线路。
            continue
        n_video += 1
        flag = str(entry.get("flag") or "").strip()
        video_flags.append(flag)
        sig = match_resource_station(
            str(entry.get("url") or ""), flag
        )
        if sig:
            n_z += 1
            if flag:
                z_flags.append(flag)
            detail.append((flag, sig))
    return {
        "n_video": n_video,
        "n_z": n_z,
        "pure": bool(n_video > 0 and n_z == n_video),
        "z_flags": z_flags,
        "video_flags": video_flags,
        "detail": detail,
    }
