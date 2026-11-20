# -*- coding: utf-8 -*-
"""注入代码单测：运行时按 CDN 剔除动态线路名（不联网）。

运行：python scripts/test_inject_filter.py
"""
import sys

sys.path.insert(0, "scripts")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import update_api as ua  # noqa: E402
import resource_station as rs  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool) -> None:
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


SRC = '''
class Spider:
    def detailContent(self, ids):
        return {"list": []}
'''
sigs = rs.runtime_url_signatures()

print("=== 动态线路名（采样时未出现）按 CDN 实时剔除 ===")
code = ua.inject_line_filter(SRC, ["天堂线路"], line_order=[], zy_sigs=sigs)
ns: dict = {}
exec(compile(code, "injected", "exec"), ns)  # noqa: S102
result = {
    "list": [{
        "vod_play_from": "暴风线路$$$魔都线路$$$索尼线路$$$天堂线路$$$自有线路",
        "vod_play_url": (
            "https://c1.rrcdnbf6.com/a.m3u8$$$"
            "https://play.modujx10.com/a.m3u8$$$"
            "https://v3.rstu6.com/a.m3u8$$$"
            "https://play.phimgood.com/a.m3u8$$$"
            "https://cdn.example.com/own.m3u8"
        ),
    }]
}
ns["_tvbox_filter_lines"](result, ns["_TVBOX_DROP_LINES"])
kept = result["list"][0]["vod_play_from"].split("$$$")
print("  保留线路:", kept)
check("暴风线路剔除(rrcdnbf6)", "暴风线路" not in kept)
check("魔都线路剔除(modujx)", "魔都线路" not in kept)
check("索尼线路剔除(rstu6)", "索尼线路" not in kept)
check("天堂线路剔除(静态名单/phimgood)", "天堂线路" not in kept)
check("自有线路保留", "自有线路" in kept)

print("\n=== 采集站 API 线路（macCMS）也剔除 ===")
result2 = {
    "list": [{
        "vod_play_from": "采集线路$$$自有线路",
        "vod_play_url": (
            "https://caiji.example.com/api.php/provide/vod$$$"
            "https://cdn.example.com/own.m3u8"
        ),
    }]
}
ns["_tvbox_filter_lines"](result2, ns["_TVBOX_DROP_LINES"])
kept2 = result2["list"][0]["vod_play_from"].split("$$$")
check("采集站 API 线路剔除", "采集线路" not in kept2)
check("自有线路保留", "自有线路" in kept2)

print("\n=== 量子 lzv 数字系列 CDN ===")
result3 = {
    "list": [{
        "vod_play_from": "F线$$$自有线路",
        "vod_play_url": "https://v.lzv40.com/a.m3u8$$$https://cdn.example.com/own.m3u8",
    }]
}
ns["_tvbox_filter_lines"](result3, ns["_TVBOX_DROP_LINES"])
kept3 = result3["list"][0]["vod_play_from"].split("$$$")
check("lzv40 剔除", "F线" not in kept3)
check("自有线路保留", "自有线路" in kept3)

print("\n=== 音频源豁免：音乐 CDN 不命中资源站签名 ===")
result4 = {
    "list": [{
        "vod_play_from": "无损$$$标准音质",
        "vod_play_url": "http://127.0.0.1:37777/a.mp3$$$https://music.91q.com/b.mp3",
    }]
}
ns["_tvbox_filter_lines"](result4, ns["_TVBOX_DROP_LINES"])
check("音频线路全保留",
      result4["list"][0]["vod_play_from"] == "无损$$$标准音质")

print("\n=== 无 drop/order/签名时不注入过滤 ===")
code5 = ua.inject_line_filter(SRC, [], line_order=[], zy_sigs=None)
ns5: dict = {}
exec(compile(code5, "injected5", "exec"), ns5)  # noqa: S102
check("不注入过滤代码", "_tvbox_filter_lines" not in ns5)
check("仅保留标记", "TVBox 本地线路过滤" in code5)

print("\n=== 多集拼接串（集名$URL#集名$URL）按 CDN 剔除 ===")
result7 = {
    "list": [{
        "vod_play_from": "暴风线路$$$魔都线路$$$索尼线路$$$自有线路",
        "vod_play_url": (
            "第01集$https://c1.rrcdnbf6.com/a.m3u8#第02集$https://c1.rrcdnbf6.com/b.m3u8$$$"
            "第01集$https://play.modujx10.com/a.m3u8#第02集$https://play.modujx10.com/b.m3u8$$$"
            "第01集$https://v3.rstu6.com/a.m3u8#第02集$https://v3.rstu6.com/b.m3u8$$$"
            "第01集$https://cdn.example.com/own.m3u8#第02集$https://cdn.example.com/own2.m3u8"
        ),
    }]
}
ns["_tvbox_filter_lines"](result7, ns["_TVBOX_DROP_LINES"])
kept7 = result7["list"][0]["vod_play_from"].split("$$$")
check("多集串暴风线路剔除", "暴风线路" not in kept7)
check("多集串魔都线路剔除", "魔都线路" not in kept7)
check("多集串索尼线路剔除", "索尼线路" not in kept7)
check("多集串自有线路保留", "自有线路" in kept7)

print("\n=== 占位符型线路（相对路径/id，无 CDN）按名字判定 ===")
result8 = {
    "list": [{
        "vod_play_from": "BF线路$$$MY线路$$$腾讯$$$官方线路-C",
        "vod_play_url": (
            "第1集$/vodplay/248-3-1.html$$$"   # BF线路：占位符，名字是资源站缩写
            "第1集$/vodplay/248-5-1.html$$$"   # MY线路：猫眼资源缩写
            "第1集$/vodplay/248-6-1.html$$$"   # 腾讯：未识别缩写，保留
            "第1集$/vodplay/248-7-1.html"      # 官方线路-C：否定词，保留
        ),
    }]
}
ns["_tvbox_filter_lines"](result8, ns["_TVBOX_DROP_LINES"])
kept8 = result8["list"][0]["vod_play_from"].split("$$$")
print("  保留:", kept8)
check("BF线路剔除(占位符+名字)", "BF线路" not in kept8)
check("MY线路剔除(占位符+名字)", "MY线路" not in kept8)
check("腾讯保留", "腾讯" in kept8)
check("官方线路-C保留(否定词)", "官方线路-C" in kept8)

print("\n=== 不剔空源：全是资源站线路时保留原样 ===")
result6 = {
    "list": [{
        "vod_play_from": "暴风线路$$$魔都线路",
        "vod_play_url": "https://c1.rrcdnbf6.com/a.m3u8$$$https://play.modujx10.com/a.m3u8",
    }]
}
before6 = (result6["list"][0]["vod_play_from"], result6["list"][0]["vod_play_url"])
ns["_tvbox_filter_lines"](result6, ns["_TVBOX_DROP_LINES"])
after6 = (result6["list"][0]["vod_play_from"], result6["list"][0]["vod_play_url"])
check("全资源站时不剔空（保持原样）", before6 == after6)

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)