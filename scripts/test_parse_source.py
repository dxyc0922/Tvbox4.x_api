# -*- coding: utf-8 -*-
"""需解析平台线路过滤单测（离线，不联网）。

运行：python scripts/test_parse_source.py
"""
import sys

sys.path.insert(0, "scripts")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import parse_source as ps  # noqa: E402
import update_api as ua  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool) -> None:
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


print("=== match_parse_required 应命中 ===")
pos = [
    ("https://cdn.example.com/a.m3u8", "自有线路", 1, False, "parse=1"),
    ("https://cdn.example.com/a.m3u8", "自有线路", 0, True, "解析失败"),
    ("https://www.iqiyi.com/v_19rr7s0ol4.html", "", 0, False, "爱奇艺播放页"),
    ("https://v.qq.com/x/cover/abc.html", "", 0, False, "腾讯播放页"),
    ("https://v.youku.com/v_show/id_abc.html", "", 0, False, "优酷播放页"),
    ("", "腾讯", 0, False, "线路名腾讯"),
    ("", "爱奇艺", 0, False, "线路名爱奇艺"),
    ("", "芒果TV", 0, False, "线路名芒果TV"),
]
for url, flag, parse, failed, label in pos:
    check(label, bool(ps.match_parse_required(url, flag, parse, failed)))

print("\n=== match_parse_required 不应命中（可播线路）===")
neg = [
    ("https://cdn.example.com/a.m3u8", "自有线路", 0, False, "自有 m3u8"),
    ("https://vv.jisuzyv.com/play/x/index.m3u8", "JS线路", 0, False, "资源站直链"),
    ("https://v.lzv40.com/2026/x/index.m3u8", "LZ线路", 0, False, "量子直链"),
    ("", "无损", 0, False, "音频线路"),
]
for url, flag, parse, failed, label in neg:
    check(label, not ps.match_parse_required(url, flag, parse, failed))

print("\n=== classify_source 千千影视（资源站 + 平台解析，无自有线路）===")
declared = ["腾讯", "LZ线路", "FF线路", "BF线路", "JS线路", "MY线路"]
rows = [
    {"flag": "腾讯", "url": "/vodplay/248-6-1.html", "parse": 1, "resolve_failed": True},
    {"flag": "LZ线路", "url": "https://v.lzv40.com/x.m3u8", "parse": 0},
    {"flag": "FF线路", "url": "https://svip.feifei-play.com/x.m3u8", "parse": 0},
    {"flag": "BF线路", "url": "https://v.fengbao14.com/x.m3u8", "parse": 0},
]
c = ps.classify_source(rows, declared_flags=declared)
check("采样识别出腾讯", "腾讯" in c["flags"])
check("声明识别出腾讯", "腾讯" in c["declared_flags"])
check("自有直链未被误判", len(c["declared_flags"]) == 1)

mixed = rows + [
    {"flag": "自有线路", "url": "https://cdn.example.com/a.m3u8", "parse": 0}
]
c2 = ps.classify_source(mixed, declared_flags=declared + ["自有线路"])
check("含自有线路 → pure=False", c2["pure"] is False)

print("\n=== 运行时注入：平台线路按名字/播放页域名剔除 ===")
SRC = '''
class Spider:
    def detailContent(self, ids):
        return {"list": []}
'''
code = ua.inject_line_filter(
    SRC,
    ["腾讯"],
    zy_sigs=None,
    parse_sigs=ps.runtime_signatures(),
)
ns: dict = {}
exec(compile(code, "injected", "exec"), ns)
result = {"list": [{
    "vod_play_from": "腾讯$$$爱奇艺$$$自有线路",
    "vod_play_url": (
        "https://www.iqiyi.com/v_abc.html$$$"
        "https://www.iqiyi.com/v_def.html$$$"
        "https://cdn.example.com/own.m3u8"
    ),
}]}
ns["_tvbox_filter_lines"](result, ns["_TVBOX_DROP_LINES"])
kept = result["list"][0]["vod_play_from"].split("$$$")
print("  保留线路:", kept)
check("腾讯剔除（静态名单）", "腾讯" not in kept)
check("爱奇艺剔除（平台域名）", "爱奇艺" not in kept)
check("自有直链保留", "自有线路" in kept)

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
