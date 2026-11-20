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
import urllib.parse
from typing import Any, Iterable

# --- 1) 采集站 API 签名（macCMS/苹果CMS 资源站采集接口）---
# 这类脚本（AI资源站.py / 采集综合.py）把一堆采集站 API 当线路，是最典型的资源站聚合。
ZY_API_RE = re.compile(
    r"/api\.php/(provide|providedown)|/inc/api_mac|provide/vod|providedown/vod",
    re.I,
)

# --- 2) 资源站播放 CDN host 特征（按资源站名拼音）---
# 只收录命名明确的资源站 CDN。少数混淆域名在用户确认归属后才收录（rstu6=索尼）；
# 签名表可配置扩展（宁可漏判也不错判）。
# 混淆域名：以下为实测在资源站聚合脚本（一起看/APP影院1）播放线路上确认的
# CDN，均为无语义随机字母域名，正常官方源不会使用，已确认归属资源站。
ZY_CDN_PATTERNS: tuple[str, ...] = (
    "ffzy", "feifei",        # 非凡资源
    "yzzy", "cdnlz", "lzzy", "lzcdn", "lz-cdn",  # 量子资源（lz=量子）/ 最大资源
    # lzv+数字（v.lzv40.com / lzv34.com）单独用 ZY_CDN_LZV_RE 匹配，避免过宽
    # 命中 lzvideo.com 之类普通域名。
    "bfzy", "rrcdnbf", "fengbao", "ffvip", "7bbffvip",  # 暴风资源 / 疯包（ffvip/7bbffvip=暴风FF资源）
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
    "mzm3u8",              # 魔爪（mzm3u8.vip，与魔都并列的资源站）
    "ppqrrs", "qqqrst", "hhuus",  # 混淆资源站 CDN（一起看/APP影院1 实测确认）
    "bdzybf",              # 百度资源（b3.bdzybf22.com，99短剧网实测）
    # 抽查实测补录：缩写聚合脚本的资源站 CDN
    "bfikuncdn", "wlcdn88", "dious", "ly166", "xgplay13", "taopianplay",
    "kuktxu", "2767.org", "892539",  # 抽查实测：不卡影视/花都影视/caoliushipinqu 资源站
)
# 只要求**左边界**（host 开头或 `.`/`-` 之后）：资源站 CDN 常带数字后缀
# （rrcdnbf6 / yzzy31 / fengbao13 / modujx10 / cdnlz14 / ruiplay18），若也要求右
# 边界会把带数字的域名漏判。左边界已足够避免 myffzyshop.com 这类误报。
ZY_CDN_RE = re.compile(
    r"(^|[.\-_])(?:%s)" % "|".join(re.escape(p) for p in ZY_CDN_PATTERNS),
    re.I,
)
# 量子资源的 lzv 系列 CDN（v.lzv40.com / lzv34.com）：必须跟数字，
# 否则 lzvideo.com 之类普通域名会被误判。此前只靠线路名（LZ/量子）识别，
# 名字是「F线」这类普通名时会漏判。
ZY_CDN_LZV_RE = re.compile(r"(^|[.\-_])lzv\d+", re.I)

# --- 3) 线路名（flag）资源站关键词 ---
# 资源站线路常直接以资源站命名（1080资源 / 极速资源 / 蜗牛资源 / 影库资源 /
# 红牛资源 / 新浪资源 / 量子资源 / 最大资源 / 暴风资源 / 魔都线路 / 暴风线路 /
# 非凡线路 / FF线路 / LZ线路 / BF线路 / 电影天堂 / 360）。
ZY_FLAG_KEYWORDS: tuple[str, ...] = (
    "资源",                       # 最显式：名字里带「资源」即资源站线路
    "量子", "非凡", "暴风", "魔都", "极速", "最大", "蜗牛", "影库",
    "红牛", "新浪", "光速", "如意", "卧龙", "无界", "人尽", "牛牛",
    "猫屋", "电影天堂", "天堂", "4K资源",
    "索尼", "无尽", "魔爪", "猫眼", "快车", "百度",  # 资源站名（实测改名脚本）
    "ikun", "速播", "站外",  # ikun资源/速播资源/站外(第三方采集站，dd脚本实测)
    "西瓜", "淘宝片", "天空", "卧龙", "拍律",  # 抽查实测资源站名
    "xiguam3u8", "ikm3u8", "tpm3u8", "rym3u8", "taopian",  # 拼音资源站名(咸鱼/电影人生实测)
)
# 裸数字（1080zyk=1080资源库 / 360=360资源）：只匹配「数字后不是 P」的情形。
# 1080P / 360P 是**分辨率标注**（如「蓝光1080P(登录专享)」是自有线路），不是资源站；
# 裸数字直接当关键词会把这类线路误判成资源站。
ZY_FLAG_NUM_RE = re.compile(r"(?i)\b(1080|360)(?!p)")
# 两字母资源站缩写（LZ=量子 FF=非凡 BF=暴风 HF/HN=红牛 YZ=云智 DY=DYTT），
# 只匹配「缩写+线路/线」组合，避免 OFF / FFF 之类误报。
ZY_FLAG_CODE_RE = re.compile(
    r"(?i)\b(LZ|FF|BF|HF|HN|YZ|DY|DYTT|LZL|YZL|FFL|BFL|MY|"
    r"IK|WL|TK|IQY|XL|WJ|BD|DB|SB|SN|MZ|PL)(?:线路|线)\b"
)
# lzm3u8 这类「缩写+m3u8」变体（云播(lzm3u8)），单独匹配避免误伤 lzvideo。
ZY_FLAG_M3U8_RE = re.compile(r"(?i)\b(?:lz|ff|bf|yz|sn|ik|bd|ry)m3u8\b")
# 纯缩写 flag（占位符型脚本：detail 只给 id|name|0，没有真实 URL，运行时 CDN
# 签名失效，只能靠名字判定）。实测「一起看」这些缩写对应的全是资源站 CDN：
#   WJ=ppqrrs SD=qqqrst HH=hhuus MT=tix8opu JY=kuktxu（混淆资源站域名）
#   BF=暴风 SN=索尼 FF=非凡 LZ=量子 YZ=云智 JS=极速 UK=uku XL=新浪 HN=红牛
#   KC=快车 BD=百度 NN=牛牛
# 用**精确相等**（upper 后整串匹配），不做子串，避免 JY/BD 出现在长名字里误报。
ZY_FLAG_EXACT_CODES: frozenset[str] = frozenset({
    "WJ", "SD", "HH", "MT", "JY", "BF", "SN", "FF", "LZ", "YZ",
    "JS", "UK", "XL", "HN", "KC", "BD", "NN", "MY",
    # 荐片缩写（实测对应资源站 CDN）：SN=索尼 WJ=玩剧 IK=ikun PL=拍律
    # WL=卧龙 MZ=魔爪 BD=百度 TK=天空 IQY=爱奇艺 RY=如意
    "IK", "PL", "WL", "MZ", "TK", "IQY", "RY",
})
# 括号代码形式（线路2(lz) / 线路3(ff) / 线路1(nby) / 线路4(bf)）：线路名后跟括号内
# 的两字母资源站缩写。只收录**已确认**的缩写：
#   lz=量子 ff=非凡 bf=暴风 hf/hn=红牛 dy=dytt yz=云智。
# 实测数据里另有 cntv=央视频、wasu=华数、pptv=PP视频、ksvideo=快手、xigua=西瓜
# 等**官方平台**代码，以及 dong/subo/jy/yd 等归属不明者——一律不收录，宁漏勿误。
# 括号内必须是完整代码（前后闭合括号），避免 (257K) / (1) 之类无关括号误报。
ZY_FLAG_PAREN_RE = re.compile(
    r"(?i)[（(]\s*(?:lz|ff|bf|hf|hn|dy|dytt|yz|lzl|yzl|ffl|bfl)\s*[）)]"
)

# 否定关键词：线路名带这些字样即为自有/官方线路，**永远不算资源站**。
# 实测猎手.py 声明 17 条线路里混有官方线（高清-官方线路B / 官方线路-C / 4K-官方线路C /
# 1080P-官方Y / 腾讯视频）——「1080P-官方Y」若按 1080 关键词判会误报成资源站，
# 把带官方线的混合源误剔成纯资源站。故否定信号优先于所有正向信号。
ZY_FLAG_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "官方", "自营", "自有", "正版",
)


# --- 运行时注入签名（供 update_api 内联到 TVBox 脚本）---
def runtime_url_signatures() -> dict[str, Any]:
    """返回可内联到脚本的资源站 URL 签名（CDN host 关键词 + 采集 API 正则）。

    注入代码只按 **URL/CDN** 判定，不按线路名——名字是上游动态返回的（猎手
    换集就变），而 CDN host 固定。音频线路走本地代理/音乐 CDN，不会命中这些
    签名，天然豁免。
    """
    return {
        "cdn": list(ZY_CDN_PATTERNS),
        "api": ZY_API_RE.pattern,
        "exact_codes": sorted(ZY_FLAG_EXACT_CODES),
        "keywords": [k for k in ZY_FLAG_KEYWORDS if k != "资源"],  # 资源太宽，单独处理
        "negatives": list(ZY_FLAG_NEGATIVE_KEYWORDS),
    }


def _host(url: str) -> str:
    """取 URL 的 host（去端口、小写）。

    本地代理型脚本（APP影院1 等）真实地址藏在 ``url=`` 参数里，外层 host 是
    127.0.0.1 —— 解码 url 参数取真实 host，否则资源站 CDN 被代理地址掩盖。
    """
    m = re.match(r"https?://([^/?]+)", url or "")
    if not m:
        return ""
    host = m.group(1).split(":")[0].lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        # 解码 url= 参数里的真实播放地址
        real = ""
        qs = re.search(r"[?&]url=([^&]+)", url)
        if qs:
            real = urllib.parse.unquote(qs.group(1))
        if real.startswith("//"):
            real = "https:" + real
        rm = re.match(r"https?://([^/?]+)", real)
        if rm:
            return rm.group(1).split(":")[0].lower()
    # 中转缓存型：真实资源站 URL 拼在路径里，如
    # https://dl.gybkw.com/cache/https://c1.7bbffvip.com/video/x.m3u8
    # 外层是中转域名，内层才是真实 CDN。取内层 host。
    inner = re.search(r"/(https?://[^/?#]+)", url)
    if inner:
        ih = re.match(r"https?://([^/?]+)", inner.group(1))
        if ih:
            return ih.group(1).split(":")[0].lower()
    return host


def match_resource_station(url: str, flag: str = "") -> str:
    """判定一条线路是否为资源站线路，返回命中的签名（非资源站返回空串）。

    信号优先级：
    1. **采集站 API**（URL 签名，最确定）
    2. **播放 CDN host**（URL 证据，强）
    3. **否定关键词**：线路名带「官方/自营/自有/正版」→ 自有线路，返回空串。
       否定只压过**线路名**正向信号，不压过 CDN/API 证据——名为「官方线路」但
       CDN 是暴风的，实际仍是资源站。
    4. **线路名**关键词 / 缩写（最弱，仅名字证据）
    """
    url = str(url or "")
    flag = str(flag or "")
    api_url = url
    if ZY_API_RE.search(api_url):
        return "采集站API"
    host = _host(url)
    if host and ZY_CDN_RE.search(host):
        return f"资源站CDN({host})"
    if host and ZY_CDN_LZV_RE.search(host):
        return f"资源站CDN({host})"
    for kw in ZY_FLAG_NEGATIVE_KEYWORDS:
        if kw in flag:
            return ""
    for kw in ZY_FLAG_KEYWORDS:
        if kw in flag:
            return f"资源站名({kw})"
    num = ZY_FLAG_NUM_RE.search(flag)
    if num:
        return f"资源站名({num.group(1)})"
    if ZY_FLAG_CODE_RE.search(flag):
        return f"资源站缩写({flag.strip()})"
    if ZY_FLAG_PAREN_RE.search(flag):
        return f"资源站缩写({flag.strip()})"
    if ZY_FLAG_M3U8_RE.search(flag):
        return f"资源站缩写({flag.strip()})"
    # 纯缩写精确匹配（占位符型脚本，CDN 签名在 detail 阶段不可用）。
    if flag.strip().upper() in ZY_FLAG_EXACT_CODES:
        return f"资源站缩写({flag.strip()})"
    return ""


def classify_source(
    line_streams: Iterable[dict[str, Any]],
    video_kinds: Iterable[str] = ("m3u8", "mp4", "hls", "flv", "local", "page"),
    declared_flags: Iterable[str] | None = None,
    declared_total: int = 0,
) -> dict[str, Any]:
    """统计一个源的资源站线路占比，返回判定结果。

    只统计**视频线路**（kind ∈ video_kinds）；音频线路（audio）不参与——
    听书/音乐源本质不同，不按资源站判。无视频线路时 pure=False（不误剔）。

    **pure 判定优先看 declared_flags（全部声明线路名）**：采样只取前 max_lines
    条线路（默认 4），但整源剔除必须确认**所有**线路都是资源站。若上游声明了
    20 条线路、只采样 4 条，剩下 16 条里可能藏着官方/自营线路——只按采样判会把
    混合源误剔成纯资源站。故三级判定：

    1. **declared_flags 非空**：pure = 每一条声明线路名都能被识别为资源站。
       **任何一条识别不出（名字普通、无 CDN 佐证）就不算纯**，保守留在混合源。
    2. **declared_total > 采样线路数**（声明了但没采到的线路存在）：pure=False。
       名字列表没落盘、又有未采样线路时无法证明「全资源站」，宁可漏判。
    3. **其余**（声明数 == 采样数，即线路已全部测到）：退回按采样判定，
       pure = 采样视频线路全部是资源站。

    返回字段：
    - n_video：采样到的视频线路数
    - n_z：其中资源站线路数
    - pure：该源是否所有线路都是资源站
    - z_flags：资源站线路的 flag 列表（用于报告）
    - video_flags：全部视频线路的 flag 集合（护栏用：剔完不能删空）
    - detail：每条资源站线路的 (flag, 签名)
    - n_declared / n_declared_z：声明线路数 / 其中被识别为资源站的数量
    """
    kinds = set(video_kinds)
    entries = list(line_streams or [])
    n_video = 0
    n_z = 0
    z_flags: list[str] = []
    video_flags: list[str] = []
    detail: list[tuple[str, str]] = []
    for entry in entries:
        stream = entry.get("stream") or {}
        kind = str(stream.get("kind") or "")
        flag = str(entry.get("flag") or "").strip()
        url = str(entry.get("url") or "")
        sig = match_resource_station(url, flag)
        if kind and kind not in kinds and kind != "unknown":
            # 明确非视频（audio）：不判资源站。
            continue
        if not kind or kind == "unknown":
            # kind 未知（如线路采样时连接超时）：URL/CDN 证据和明确的资源站
            # 名字信号都认。猎手「超清线路」超时但 CDN 是暴风；分享咕噜「蚂蚁
            # 资源」超时但名字含资源——此前只认 URL 证据导致这类漏剔。
            # 音频线路名不会叫「XX资源/暴风/量子」，名字信号可安全采信。
            if (
                sig.startswith("资源站CDN")
                or sig == "采集站API"
                or sig.startswith("资源站名")
                or sig.startswith("资源站缩写")
            ):
                n_z += 1
                if flag:
                    z_flags.append(flag)
                detail.append((flag, sig))
            continue
        n_video += 1
        video_flags.append(flag)
        if sig:
            n_z += 1
            if flag:
                z_flags.append(flag)
            detail.append((flag, sig))
    declared = [
        str(x).strip() for x in (declared_flags or []) if str(x or "").strip()
    ]
    n_declared_z = sum(1 for name in declared if match_resource_station("", name))
    # 采样里已被 CDN/URL 证据判为资源站的线路，即使名字普通（如「无尽云播」）
    # 也要计入 declared 的 z 数——代理型脚本真实 CDN 藏在 url 参数里，名字看不出。
    z_flag_set = {f for f in z_flags if f}
    for name in declared:
        if name in z_flag_set and not match_resource_station("", name):
            n_declared_z += 1
    n_sampled = len(entries)
    # 采样线路的真实 CDN/名字是硬证据（用户原则：名字会被改写，域名不会）。
    # 判整源为资源站聚合源需同时满足：
    #   1. 所有采样线路都命中资源站（名字或 CDN 信号）——只要有一条可确认自有
    #      的采样线路（名字无信号且 host 非资源站 CDN）就不整源剔，
    #      避免荐片这类「部分自有+部分资源站」的混合源被误剔
    #   2. 声明名单完整存在（declared_flags）
    #   3. 声明名单里没有明确的自有线路（官方/自营/自有/正版）
    sampled_sigs = [
        match_resource_station(str(e.get("url") or ""), str(e.get("flag") or ""))
        for e in entries
    ]
    sampled_has_own = any(not sig for sig in sampled_sigs)
    sampled_all_zy = bool(entries and not sampled_has_own)
    declared_has_own = any(
        any(kw in name for kw in ZY_FLAG_NEGATIVE_KEYWORDS) for name in declared
    )
    if sampled_all_zy and declared and not declared_has_own:
        pure = True
    elif declared:
        # 纯缩写占比 ≥60% → 资源站聚合型脚本（占位符线路，全是采集站缩写）。
        # 这类脚本不混官方线，未识别的少数线路（如「XXAPP」）也是资源站。
        n_exact = sum(1 for name in declared if name.strip().upper() in ZY_FLAG_EXACT_CODES)
        is_aggregator = len(declared) >= 3 and n_exact / len(declared) >= 0.6
        if is_aggregator:
            # 未识别线路若带官方/自营字样则不算（保守），否则算资源站。
            for name in declared:
                if match_resource_station("", name):
                    continue
                if any(kw in name for kw in ZY_FLAG_NEGATIVE_KEYWORDS):
                    continue
                n_declared_z += 1
        pure = n_declared_z == len(declared) > 0
    elif int(declared_total or 0) > n_sampled:
        # 声明了更多线路但没采到 → 存在未验证线路，不能断言「全资源站」。
        pure = False
    else:
        pure = bool(n_video > 0 and n_z == n_video)
    return {
        "n_video": n_video,
        "n_z": n_z,
        "pure": pure,
        "z_flags": z_flags,
        "video_flags": video_flags,
        "detail": detail,
        "n_declared": len(declared) or int(declared_total or 0),
        "n_declared_z": n_declared_z,
        "n_sampled": n_sampled,
    }
