# -*- coding: utf-8 -*-
"""resource_station 模块单测（离线，不联网）。

运行：python scripts/test_resource_station.py
覆盖：
- match_resource_station 的三层信号（采集站 API / CDN host / 线路名）
- 否定关键词（官方/自营/自有/正版）优先于线路名信号、但不压过 CDN 证据
- 裸数字（1080/360）与分辨率标注（1080P）的区分
- 括号缩写代码（线路2(lz)）与官方平台代码（cntv/wasu/pptv/ksvideo/xigua）的区分
- classify_source 的 pure 判定：采样只看前 4 条时，必须基于全部声明线路名
"""
import sys

sys.path.insert(0, "scripts")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import resource_station as rs  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool) -> None:
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


def is_zy(url: str, flag: str = "") -> bool:
    return bool(rs.match_resource_station(url, flag))


# --- 1) 应命中：资源站 CDN / API / 线路名 ---
print("=== 应命中 ===")
pos = [
    ("http://c1.rrcdnbf6.com/a/b.m3u8", "", "暴风CDN"),
    ("https://play.modujx10.com/x.m3u8", "", "魔都CDN"),
    ("https://vv.jisuzyv.com/x.m3u8", "", "极速CDN"),
    ("https://v13.zuidazym3u8.com/x.m3u8", "", "最大CDN"),
    ("https://vip.dytt-cinema.com/x.m3u8", "", "电影天堂CDN"),
    ("http://v3.rstu6.com/x.m3u8", "", "索尼CDN"),
    ("https://v13.wsyzym3u8.com/x.m3u8", "", "蜗牛CDN"),
    ("https://cdn1.yzzyhd-play.com/x.m3u8", "", "量子CDN"),
    ("https://api.example.com/api.php/provide/vod", "", "采集站API"),
    ("https://caiji.example.com/api.php/providedown/vod/", "", "采集站API(down)"),
    ("https://api.example.com/inc/api_mac10.php", "", "采集站API(maccms)"),
    ("", "LZ线路", "LZ缩写"),
    ("", "FF线路", "FF缩写"),
    ("", "BF线路", "BF缩写"),
    ("", "HF线路", "HF缩写(新增)"),
    ("", "HN线路", "HN缩写(新增)"),
    ("", "1080资源", "资源关键词"),
    ("", "量子资源", "量子"),
    ("", "索尼线路", "索尼"),
    ("", "电影天堂", "电影天堂"),
    ("", "360", "裸360"),
    ("", "1080zyk", "裸1080(资源站)"),
    ("", "线路2(lz)", "括号lz(新增)"),
    ("", "线路3(ff)", "括号ff(新增)"),
    ("", "线路4(bf)", "括号bf(新增)"),
    ("", "线路（lz）", "全角括号lz"),
    ("", "红牛(HN)", "红牛关键词"),
]
for url, flag, label in pos:
    check(f"{label}: {url or flag}", is_zy(url, flag))

# --- 2) 不应命中：误报防护 ---
print("\n=== 不应命中（误报防护）===")
neg = [
    ("https://myffzyshop.com/x.m3u8", "", "myffzyshop（左边界）"),
    ("https://www.example.com/x.m3u8", "官方线路", "普通官方线路"),
    ("https://127.0.0.1:8080/x.m3u8", "直链", "本地代理"),
    ("https://music.example.com/a.mp3", "无损", "音频"),
    ("", "1080P", "1080P 分辨率"),
    ("", "360P", "360P 分辨率"),
    ("", "1080P线路", "1080P线路"),
    ("", "360P线路", "360P线路"),
    ("", "蓝光1080P(登录专享)", "1080P(登录专享)"),
    ("", "线路1(nby)", "nby 未确认归属"),
    ("", "金鹰2(JY)", "JY 未确认归属"),
    ("", "4K(YD)", "YD 未确认归属"),
    ("", "Y蓝光 (Dong)", "Dong 未确认归属"),
    ("", "速博(SUBO)", "SUBO 未确认归属"),
    ("", "线路K+ (wasu)", "wasu=华数官方平台"),
    ("", "线路JP (cntv)", "cntv=央视频官方平台"),
    ("", "线路QS+ (pptv)", "pptv=PP视频官方平台"),
    ("", "线路P1 (xigua)", "xigua=西瓜官方平台"),
    ("", "K蓝光 (Ksvideo)", "ksvideo=快手官方平台"),
    ("", "4K(123)", "纯数字括号"),
    ("", "备用1（视频内广告勿信）", "中文说明括号"),
    ("", "蓝光1080P(登录专享)", "1080P+中文括号"),
]
for url, flag, label in neg:
    check(f"{label}: 非资源站", not is_zy(url, flag))

# --- 3) 否定关键词 ---
print("\n=== 否定关键词：官方/自营/自有/正版 ===")
for flag in ("官方线路", "自营线路", "正版资源", "1080P-官方Y", "4K-官方线路C", "腾讯视频"):
    check(f"{flag}: 非资源站", not is_zy("", flag))

print("\n=== 否定不压过 URL 证据 ===")
# 名为「官方线路」但 CDN 是暴风 → 仍判资源站。
check("官方线路+暴风CDN → 资源站", is_zy("https://c1.rrcdnbf6.com/a.m3u8", "官方线路"))
# 名为「天堂线路」但 CDN 是官方 → 仍判资源站（CDN 优先于否定）。
check("天堂线路+官方CDN → 资源站", is_zy("https://vip.dytt-cinema.com/a.m3u8", "官方线路"))

# --- 4) classify_source ---
print("\n=== classify_source ===")
pure_lines = [
    {"flag": "暴风线路", "url": "http://c1.rrcdnbf6.com/a.m3u8", "stream": {"kind": "m3u8"}},
    {"flag": "魔都线路", "url": "https://play.modujx10.com/a.m3u8", "stream": {"kind": "m3u8"}},
    {"flag": "索尼线路", "url": "http://v3.rstu6.com/a.m3u8", "stream": {"kind": "m3u8"}},
    {"flag": "天堂线路", "url": "https://vip.dytt-cinema.com/a.m3u8", "stream": {"kind": "m3u8"}},
]
c = rs.classify_source(pure_lines)
check("纯资源站 pure=True（无 declared）", c["pure"] is True)
check(f"n_video={c['n_video']} n_z={c['n_z']}", c["n_video"] == 4 and c["n_z"] == 4)

mixed_lines = pure_lines + [
    {"flag": "自有线路", "url": "https://cdn.example.com/a.m3u8", "stream": {"kind": "m3u8"}},
]
c = rs.classify_source(mixed_lines)
check("混合源 pure=False（无 declared）", c["pure"] is False)
check("video_flags 含自有线路", "自有线路" in c["video_flags"])

c = rs.classify_source(
    [{"flag": "无损", "url": "https://music.example.com/a.mp3", "stream": {"kind": "audio"}}]
)
check("音频源 n_video=0 pure=False", c["n_video"] == 0 and c["pure"] is False)
check("空线路 pure=False", rs.classify_source([])["pure"] is False)

# --- 5) declared_flags：采样只看前 4 条时的整源判定 ---
print("\n=== declared_flags：整源判定看全部声明线路 ===")
# 声明 24 条，其中混有自有线路 → 不能判纯（否则把混合源误剔）。
declared = [p["flag"] for p in pure_lines] + [
    "线路1", "线路2", "线路3", "线路4", "线路5",
    "官方线路", "自营线路", "独家线路", "蓝光线路", "4K线路",
] + ["备用线路"] * 10
c = rs.classify_source(pure_lines, declared_flags=declared)
check("24 条声明含自有线路 → pure=False", c["pure"] is False)
check("n_declared_z < n_declared", c["n_declared_z"] < c["n_declared"])

# 全部声明都是资源站名 → 仍判纯。
all_zy = [p["flag"] for p in pure_lines] + ["暴风HD"] * 16
c = rs.classify_source(pure_lines, declared_flags=all_zy)
check("20 条声明全资源站 → pure=True", c["pure"] is True)
check(f"n_declared_z={c['n_declared_z']}", c["n_declared_z"] == 20)

# 旧缓存无 declared_flags → 兼容退回按采样判定。
check("declared_flags=None 兼容", rs.classify_source(pure_lines, declared_flags=None)["pure"] is True)
check("declared_flags=[] 兼容", rs.classify_source(pure_lines, declared_flags=[])["pure"] is True)

print("\n=== declared_total：声明数 > 采样数时不得判纯 ===")
# 猎手系：声明 20 条只采样 4 条，无 declared_flags 名单 → 不能断言全资源站。
c = rs.classify_source(pure_lines, declared_total=20)
check("声明20/采样4 → pure=False", c["pure"] is False)
check(f"n_declared={c['n_declared']} n_sampled={c['n_sampled']}",
      c["n_declared"] == 20 and c["n_sampled"] == 4)

# 声明数 == 采样数（线路全采到）→ 仍按采样判定。
c = rs.classify_source(pure_lines, declared_total=4)
check("声明4/采样4 → pure=True", c["pure"] is True)

# 声明数 == 0（无数据）→ 退回采样判定。
c = rs.classify_source(pure_lines, declared_total=0)
check("声明0 → 退回采样 pure=True", c["pure"] is True)

# 生成器输入不应因二次遍历失效。
gen = (x for x in pure_lines)
c = rs.classify_source(gen, declared_total=20)
check("生成器 declared_total=20 → pure=False", c["pure"] is False)

# 猎手.py 实测：17 条声明线路含 6 条官方线 → 不得判纯。
print("\n=== 猎手.py 实测：17 条声明含官方线 → 不得判纯 ===")
lie = [
    "天堂线路", "非凡线路", "超清线路", "如意线路", "量子线路", "魔爪线路",
    "高清-官方线路B", "高清-官方线路D", "官方线路-C", "尊享4k", "4K-官方线路C",
    "1080P-官方Y", "无水印线路", "极速线路", "腾讯视频", "速播线路", "新浪线路",
]
c = rs.classify_source(pure_lines, declared_flags=lie)
check(f"猎手 pure={c['pure']}（须 False）", c["pure"] is False)
check(f"n_declared_z={c['n_declared_z']}/17", c["n_declared_z"] < 17)

print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)