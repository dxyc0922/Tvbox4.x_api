# coding=utf-8
# -*- coding: utf-8 -*-
"""
滴答影院 loldyw.com | TVBox Python 爬虫
================================================================

【网站结构】
    首页                /                                     -> 200, 纯 HTML(UTF-8)
    分类第 1 页         /genre/{tid}.html
    分类分页            /genre/{tid}-{page}.html               <- 真实，见【实测要点 5】
    详情页              /film/{vodId}.html                     vodId 形如 857985f / 969279f
    播放页              /watch/{vodId}/{sid}/{nid}.html
    搜索(HTML)          /lookup/wd/{关键词}.html
    搜索建议(JSON)      /index.php/ajax/suggest?mid={tid}&wd={关键词}
    筛选入口            /filter/id/{子类tid}.html                <- 注意是子类 tid，不是大类 tid
    筛选分页            /filter/{各维度}/page/{n}.html

    重要：/lookup/page/{n}/type/{tid}.html 在本站【不存在】（旧版 MacCMS 写法），
          已由 /genre/{tid}-{page}.html 取代。上一版误用该路径，导致翻页全空。

【实测要点 5 补充：筛选 panel 的真实 DOM 与 URL 规则】
    六个分类页（动作片6 / 国产剧13 / 大陆综艺25 / 国产动漫29 / 短剧大全40）的
    <div class="slideDown-box"> 内，恒为若干条:
        <ul class="iqy-screen__list nav-slide clearfix" data-align="left">
          <li><a class="btn text-muted">剧情</a></li>
          <li><a class="btn btn-warm" href="/filter/id/6.html">全部</a></li>
          <li><a class="btn" href="/filter/class/%E5%96%9C%E5%89%A7/id/6.html">喜剧</a></li>
          ...
    维度顺序恒为：类型(id) → 剧情(class) → 地区(area) → 年份(year) → 语言(lang)
                  → 字母(letter)，最后一条独立 ul 是排序(by)。
    URL 拼接顺序（由真实 href 归纳，非猜测）：
        /filter/ [by/{time|hits|score}/] [class/{剧情}/] [area/{地区}/]
                id/{子类tid} [/year/{年}] [/lang/{语}] [/letter/{字母}] [/page/{n}].html
    要点：
      * id 段出现在 area 之后、year 之前，位置固定，不是任意排列。
      * 无任何筛选时走 /genre/{tid}.html 或 /genre/{tid}-{n}.html，不走 /filter/。
      * 每个大类的剧情/地区/年份/语言取值【互不相同】，必须按大类分别建表：
          电影9子类 共享 26剧情 / 15地区(大陆…) / 2010-2026 / 9语言(含法德)
          电视剧8子类 共享 16剧情 / 10地区(内地…) / 2010-2026 / 7语言
          综艺4子类 共享 13剧情 / 4地区(内地/港台/日韩/欧美) / 2004-2018 / 7语言
          动漫5子类 共享 20剧情 / 4地区(国产/日本/欧美/其他) / 2004-2018 / 7语言
          短剧2子类 只有 类型 + 字母 + 排序（无剧情/地区/年份/语言）
      * 地区用词四个大类四套，绝不通用：电影=大陆，电视剧/综艺=内地，动漫=国产。

【实测要点 1：响应体是"JSON 字符串转义过的 HTML"】
    服务端返回的正文形如:
        "<!DOCTYPE html>\n<html>\n<head>\n<title>...<\/title>...href=\"\/film\/...\""
    即整份 HTML 被包成一个 JSON 字符串（存在 \\/ 、\\" 、\\n 、\\uXXXX 转义）。
    因此必须先用 json.loads 反解，否则所有 href="..." 都匹配不到。
    另外站点偶尔也直接返回正常 HTML，两种都要兼容（见 _normalize）。

【实测要点 2：反爬】
    默认请求 -> 403 (nginx)；带 X-Requested-With / Origin / Referer -> 200。
    这是绕过 CF 与 nginx 拦截的必要条件。

【实测要点 3：线路名不可写死】
    详情页线路名来自选项卡:
        <li><a href="#playlist4" data-toggle="tab">极速高清</a></li>
        <li><a href="#playlist3" data-toggle="tab">量子高清</a></li>
        <li><a href="#playlist2" data-toggle="tab">天堂高清</a></li>
        <li><a href="#playlist1" data-toggle="tab">无尽4K</a></li>
    同一页面 playlist 编号与名称的对应关系随影片而变，不能按 1=量子高清 硬编码。

【实测要点 4：播放页有可直接使用的真实直链】
    播放页内嵌:
        var player_aaaa={"flag":"play","encrypt":0, ... ,
            "url":"https:\\/\\/vv.jisuzyv.com\\/play\\/erkYwREa\\/index.m3u8",
            "url_next":"...", "from":"jsm3u8", "id":"857985", "sid":4, "nid":1}
    依据 /static/js/player.js 中 MacPlayer.Init 的真实逻辑:
        encrypt == '1' -> url = unescape(url)
        encrypt == '2' -> url = unescape(base64decode(url))
    实测 encrypt=0，url 即最终地址，parse 设为 0 可直接播放。
    已实测该 m3u8 HTTP 200，且内含 AES-128 加密(URI="enc.key")，分片在
    https://p.jisuts.com:999/... 。因此本地代理必须按扩展名返回正确 Content-Type，
    不能一律当图片返回，否则播放器无法解出 #EXTM3U 与密钥。

【实测要点 5：分页总数】
    列表页底部真实分页（/genre/6-2.html 原文）:
        <ul class="iqy-page text-center clearfix">
          <li><a class="btn btn-default" href="/genre/6-1.html">首页</a></li>
          <li><a class="btn btn-default" href="/genre/6-1.html">上一页</a></li>
          <li class="hidden-xs"><a class="btn btn-default" href="/genre/6-1.html">1</a></li>
          <li class="hidden-xs"><a class="btn btn-warm" href="/genre/6-2.html">2</a></li>
          <li class="visible-xs"><a class="btn btn-warm">2/820</a></li>
          <li><a class="btn btn-default" href="/genre/6-3.html">下一页</a></li>
          <li><a class="btn btn-default" href="/genre/6-820.html">尾页</a></li>
        </ul>
    总页数有两个可靠来源，优先用 "2/820" 这种 mobile 分页串，其次用"尾页"链接。
    实测各分类总页：动作片820 / 国产剧1314 / 大陆综艺343 / 国产动漫222 / 短剧1261。
"""
import re
import sys
import json
import time
import base64
import urllib.parse

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as _rq
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass

    class _BaseSpider(object):
        def __init__(self):
            self._session = None

        @property
        def _sess(self):
            if self._session is None:
                self._session = _rq.Session()
                self._session.verify = False
                adapter = _rq.adapters.HTTPAdapter(
                    pool_connections=10, pool_maxsize=10, max_retries=0)
                self._session.mount('https://', adapter)
                self._session.mount('http://', adapter)
            return self._session

        def fetch(self, url, headers=None, **kw):
            timeout = kw.pop('timeout', 15)
            r = self._sess.get(url, headers=headers, timeout=timeout, **kw)
            try:
                r.encoding = 'utf-8'
            except Exception:
                pass
            return r

        def log(self, *a, **kw):
            try:
                print("[loldyw]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.loldyw.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 简介统一前缀
INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！\n"

# 实测首页侧边导航: /genre/1.html 电影 / 2 电视剧 / 3 综艺片 / 4 动漫 / 24 短剧
CLASSES = [
    {"type_id": "1",  "type_name": "电影"},
    {"type_id": "2",  "type_name": "电视剧"},
    {"type_id": "3",  "type_name": "综艺"},
    {"type_id": "4",  "type_name": "动漫"},
    {"type_id": "24", "type_name": "短剧"},
]

# ======================================================================
#  筛选配置 —— 全部取值均抄自六份真实分类页的 <div class="slideDown-box">
#  结构: GROUP -> 大类tid -> {类型/剧情/地区/年份/语言/字母/排序}
#  铁律: 剧情 / 地区 / 年份 / 语言 四组取值按【大类】绑定，四大类互不通用。
#        地区用词尤其不能混: 电影=大陆，电视剧/综艺=内地，动漫=国产。
# ======================================================================

# ---- 类型(id) 子分类映射，来源: 各分类页 "类型" 那一行真实 href ----
SUB_TYPES = {
    # /filter/id/6.html 一页
    "1": [("6", "动作片"), ("7", "喜剧片"), ("8", "爱情片"), ("9", "科幻片"),
          ("10", "剧情片"), ("11", "战争片"), ("41", "动画片"), ("12", "记录片"),
          ("39", "恐怖片")],
    # /filter/id/13.html 一页
    "2": [("13", "国产剧"), ("14", "香港剧"), ("15", "韩国剧"), ("16", "欧美剧"),
          ("22", "台湾剧"), ("21", "日本剧"), ("20", "泰国剧"), ("23", "海外剧")],
    # /filter/id/25.html 一页
    "3": [("25", "大陆综艺"), ("26", "日韩综艺"), ("27", "港台综艺"),
          ("28", "欧美综艺")],
    # /filter/id/29.html 一页（42/43 为后补编号，不连续，必须照抄）
    "4": [("29", "国产动漫"), ("30", "日本动漫"), ("42", "港台动漫"),
          ("31", "欧美动漫"), ("43", "海外动漫")],
    # /filter/id/40.html 一页
    "24": [("40", "短剧大全"), ("44", "AI漫剧")],
}

# ---- 剧情(class) 按大类 ----
CLAZZ = {
    # 动作片页（26 项，注意"恐怖"在原站重复出现两次，此处按真实顺序保留一次）
    "1": ["喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争", "警匪", "犯罪",
          "动画", "奇幻", "武侠", "冒险", "枪战", "悬疑", "惊悚", "经典", "青春",
          "文艺", "微电影", "古装", "历史", "运动", "农村", "儿童", "网络电影"],
    # 国产剧页（16 项）
    "2": ["古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作", "奇幻",
          "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他"],
    # 大陆综艺页（13 项）
    "3": ["选秀", "情感", "访谈", "播报", "旅游", "音乐", "美食", "纪实",
          "曲艺", "生活", "游戏互动", "财经", "求职"],
    # 国产动漫页（20 项）
    "4": ["情感", "科幻", "热血", "推理", "搞笑", "冒险", "萝莉", "校园", "动作",
          "机战", "运动", "战争", "少年", "少女", "社会", "原创", "亲子", "益智",
          "励志", "其他"],
    # 短剧页：真实页面【没有剧情维度】，留空
    "24": [],
}

# ---- 地区(area) 按大类 ----
AREA = {
    # 动作片页 15 项（电影用"大陆"）
    "1": ["大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国", "德国",
          "泰国", "印度", "意大利", "西班牙", "加拿大", "其他"],
    # 国产剧页 10 项（电视剧用"内地"，且无 法/德/印/意/西/加）
    "2": ["内地", "韩国", "香港", "台湾", "日本", "美国", "泰国", "英国",
          "新加坡", "其他"],
    # 大陆综艺页 4 项
    "3": ["内地", "港台", "日韩", "欧美"],
    # 国产动漫页 4 项（动漫用"国产"）
    "4": ["国产", "日本", "欧美", "其他"],
    "24": [],
}

# ---- 年份(year) 按大类 ----
# 电影/电视剧: 2010-2026；综艺/动漫: 站点真实只有 2004-2018（2019 年后未补数据，
# 若强行给 2025 会得到空页，故严格照抄真实取值）。
YEAR = {
    "1": [str(y) for y in range(2026, 2009, -1)],
    # 根据图1：剧集年份为 2026...2019，接着是区间 2020-2016, 2015-2011, 2010-2000
    "2": ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", 
          "2020-2016", "2015-2011", "2010-2000"],
    "3": [str(y) for y in range(2018, 2003, -1)],
    "4": [str(y) for y in range(2018, 2003, -1)],
    "24": [],
}

# ---- 语言(lang) 按大类 ----
LANG = {
    # 电影 9 项（独有 法语/德语）
    "1": ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "法语", "德语", "其它"],
    # 电视剧/综艺/动漫 均为 7 项
    "2": ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "其它"],
    "3": ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "其它"],
    "4": ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "其它"],
    "24": [],
}

# ---- 字母(letter) 全站统一 27 项 ----
LETTER = [chr(x) for x in range(ord("A"), ord("Z") + 1)] + ["0-9"]

# ---- 排序(by) 全站统一 ----
# 根据图1：显示的是 最热 / 最新
SORT_BY = [("hits", "最热"), ("time", "最新")]

# ---------------- 真实源码对应的正则 ----------------

# 卡片封面锚点（首页网格 + 搜索媒体列表共用同一个 class）:
#   <a class="iqy-vodlist__thumb lazyload" href="/film/857985f.html"
#      title="青之箱第二季" data-original="https://...jpg">
#   <a class="iqy-vodlist__thumb img-lg-150 ... lazyload" href="/film/..."
_RE_THUMB = re.compile(
    r'<a\b[^>]*class="[^"]*iqy-vodlist__thumb[^"]*"[^>]*>', re.I)

# 卡片标题（两种布局都有 <h4 class="title">）:
#   <h4 class="title text-overflow"><a href="/film/969201f.html" title="...">片名</a></h4>
#   <h4 class="title"><a href="/film/857985f.html">片名</a></h4>
_RE_H4_TITLE = re.compile(
    r'<h4[^>]*class="[^"]*title[^"]*"[^>]*>\s*<a\b[^>]*>([^<]*)</a>', re.I)

# 备注: <span class="pic-text text-right">已完结</span>
_RE_REMARK = re.compile(r'class="pic-text[^"]*"[^>]*>([^<]*)<', re.I)

# 评分标记 <span class="pic-tag pic-tag-top">0.0分</span>（不是备注，需排除）
_RE_PICTAG = re.compile(r'class="pic-tag[^"]*"[^>]*>([^<]*)<', re.I)

# 卡片内 主演/分类/地区/年份，真实存在两种写法：
#  (1) 包在 span 里（搜索/详情页）: <span class="text-muted">主演：</span>内详
#      注意带后缀的情况      : <span class="text-muted hidden-xs">地区：</span>
#     同一行多个字段用分隔   : 喜剧,爱情,动画,运动<span class="split-line"></span><span ...>地区：</span>日本
#  (2) 直接写在 <p> 文本里（首页卡片）: <p class="text ... text-muted">主演：内详</p>
_RE_META = re.compile(
    r'(?:<span[^>]*class="[^"]*text-muted[^"]*"[^>]*>|>)\s*'
    r'(主演|导演|分类|地区|年份|更新|简介)\s*[:：]\s*(?:</span>)?\s*'
    r'([^<]*)', re.I)

# 字段值的右边界：遇到 split-line 或下一个标签即结束
_RE_VALUE_END = re.compile(r'<span[^>]*class="[^"]*split-line', re.I)

# 详情页标题: <h1 class="title">青之箱第二季</h1>
_RE_H1 = re.compile(r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>([\s\S]*?)</h1>', re.I)

# 详情页封面（懒加载真实图在 data-original，src 是占位图 load.gif）:
#   <img class="lazyload" src="/template/three/statics/img/load.gif"
#        data-original="https://pic.youkupic.com/upload/vod/...jpg"/>
_RE_DETAIL_PIC = re.compile(
    r'<div class="iqy-content__thumb">[\s\S]{0,600}?data-original="([^"]+)"', re.I)

# 详情页 简介 正文: <div class="col-pd text-collapse content"> ... <span class="sketch content"></span>
#                     <span class="data" style="display: none;"><p>正文</p></span>
_RE_SKETCH = re.compile(
    r'<div class="col-pd text-collapse content">([\s\S]*?)<a class="details"', re.I)
_RE_COMMENT = re.compile(r'<span class="sketch content">([\s\S]*?)</span>', re.I)
_RE_HIDDEN_DESC = re.compile(
    r'<span class="data"[^>]*style="[^"]*display:\s*none[^"]*"[^>]*>([\s\S]*?)</span>', re.I)

# 播放地址选项卡（线路名 + 线路号）:
#   <li><a href="#playlist4" data-toggle="tab">极速高清</a></li>
_RE_TAB = re.compile(
    r'<a\b[^>]*href="#playlist(\d+)"[^>]*data-toggle="tab"[^>]*>([^<]*)</a>', re.I)

# 线路内容块: <div id="playlist4" class="tab-pane fade in clearfix"> ... </div>
_RE_PANE = re.compile(
    r'<div\b[^>]*id="playlist(\d+)"[^>]*>([\s\S]*?)(?=<div\b[^>]*id="playlist\d+"|<div class="iqy-vod-detail__extras")',
    re.I)

# 剧集: <li class="..."><a class="btn btn-default" href="/watch/857985f/4/1.html">第1集</a></li>
_RE_EP = re.compile(
    r'<a\b[^>]*href="(/watch/[^"]+?\.html)"[^>]*>([^<]{0,40})</a>', re.I)

# 播放页 player_aaaa = {...};
_RE_PLAYER = re.compile(r'player_\w+\s*=\s*(\{[\s\S]*?\})\s*</script>', re.I)

# 分页"尾页"（旧路径，已废弃但保留以兼容可能的旧页）
_RE_PAGE_ANY = re.compile(r'/lookup/page/(\d+)/', re.I)

# ajax suggest 的详情链接规则未在 JSON 中给出 vodId，只能用 id 拼 /film/{id}f.html
# （实测 id=857985 <-> /film/857985f.html，见详情页 data-id="857985"）


class Spider(Spider):

    def getName(self):
        return "滴答影院"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}

        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        # 实测：不带这三个头 -> 403 Forbidden (nginx)；带上 -> 200
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.site_url + "/",
            "Origin": self.site_url,
            "X-Requested-With": "XMLHttpRequest",
            "Upgrade-Insecure-Requests": "1",
        }
        self._play_cache = {}
        self.log("init: site=%s" % self.site_url)

    # ================= 基础工具 =================

    def _raw(self, url, timeout=20, headers=None):
        """发请求，返回原始正文字符串（未做转义还原）。"""
        try:
            h = dict(self.headers)
            if headers:
                h.update(headers)
            rsp = self.fetch(url, headers=h, timeout=timeout)
            if hasattr(rsp, "text") and rsp.text is not None:
                return rsp.text
            if hasattr(rsp, "content"):
                return rsp.content.decode("utf-8", "ignore")
            return str(rsp) if rsp is not None else ""
        except Exception as e:
            self.log("fetch FAIL %s -> %s" % (url, e))
            return ""

    @staticmethod
    def _normalize(text):
        """还原"被包成 JSON 字符串的 HTML"。"""
        if not text:
            return ""
        s = text.strip()
        # 情况 A：整份文档是一个 JSON 字符串字面量
        if s[:1] == '"' and s[-1:] == '"':
            try:
                v = json.loads(s)
                if isinstance(v, str):
                    return v
            except Exception:
                pass
        # 情况 B：{"data":{"content":"..."}} 包裹
        if s[:1] == '{':
            try:
                obj = json.loads(s)
                data = obj.get("data")
                if isinstance(data, dict) and isinstance(data.get("content"), str):
                    return data["content"]
            except Exception:
                pass
        # 情况 C：HTML 中残留 \\/ \\" 转义（只做安全的最小还原）
        if '\\/' in text:
            return (text.replace('\\/', '/')
                        .replace('\\"', '"')
                        .replace("\\r", ""))
        return text

    def _fetch_html(self, url, timeout=20, headers=None, need=None, retry=3):
        """取页面并还原为正常 HTML。"""
        attempt = 0
        while True:
            raw = self._raw(url, timeout=timeout, headers=headers)
            html = self._normalize(raw)
            if not need or need in html:
                return html
            attempt += 1
            if attempt >= retry:
                return ""
            time.sleep(0.3 * attempt)

    def _fetch_json(self, url, timeout=20):
        raw = self._raw(url, timeout=timeout,
                        headers={"Accept": "application/json, text/javascript, */*; q=0.01"})
        txt = self._normalize(raw)
        for cand in (txt, raw):
            if not cand:
                continue
            t = cand.strip()
            # 兼容 JSONP
            m = re.match(r'^[\w$.]+\(([\s\S]*)\)\s*;?$', t)
            if m:
                t = m.group(1)
            try:
                return json.loads(t)
            except Exception:
                continue
        return None

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip().replace("&amp;", "&")
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return self.site_url + url
        return urllib.parse.urljoin(self.site_url + "/", url)

    def _clean(self, s):
        if not s:
            return ""
        s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
        s = re.sub(r"</p\s*>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        # 数字实体（如 &#039; &#x27;）统一还原
        s = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: self._safe_chr(int(m.group(1), 16)), s)
        s = re.sub(r"&#(\d+);", lambda m: self._safe_chr(int(m.group(1))), s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"')
              .replace("&lt;", "<").replace("&gt;", ">")
              .replace("&ldquo;", "“").replace("&rdquo;", "”")
              .replace("&hellip;", "…").replace("&middot;", "·")
              .replace("&mdash;", "—").replace("&ndash;", "–"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    @staticmethod
    def _safe_chr(code):
        try:
            return chr(code)
        except Exception:
            return ""

    @staticmethod
    def _attr(tag, name):
        m = re.search(r'\b%s\s*=\s*"([^"]*)"' % name, tag, re.I)
        if not m:
            m = re.search(r"\b%s\s*=\s*'([^']*)'" % name, tag, re.I)
        return m.group(1) if m else ""

    @staticmethod
    def _vod_id_from_href(href):
        """/film/857985f.html -> 857985f"""
        m = re.search(r'/film/([^/"?]+?)\.html', href or "", re.I)
        return m.group(1) if m else ""

    # ================= 首页 =================

    def homeContent(self, filter=False):
        """分类 + 筛选面板。"""
        filters = {}
        if filter:
            for c in CLASSES:
                tid = c["type_id"]
                groups = []

                # 1) 类型
                subs = SUB_TYPES.get(tid) or []
                if subs:
                    val_list = [{"n": "全部", "v": "全部"}]
                    val_list.extend([{"n": n, "v": v} for v, n in subs])
                    groups.append({
                        "key": "id", "name": "类型",
                        "value": val_list,
                    })
                # 2) 剧情
                if CLAZZ.get(tid):
                    val_list = [{"n": "全部", "v": "全部"}]
                    val_list.extend([{"n": x, "v": x} for x in CLAZZ[tid]])
                    groups.append({
                        "key": "class", "name": "剧情",
                        "value": val_list,
                    })
                # 3) 地区
                if AREA.get(tid):
                    val_list = [{"n": "全部", "v": "全部"}]
                    val_list.extend([{"n": x, "v": x} for x in AREA[tid]])
                    groups.append({
                        "key": "area", "name": "地区",
                        "value": val_list,
                    })
                # 4) 年份
                if YEAR.get(tid):
                    val_list = [{"n": "全部", "v": "全部"}]
                    val_list.extend([{"n": y, "v": y} for y in YEAR[tid]])
                    groups.append({
                        "key": "year", "name": "年份",
                        "value": val_list,
                    })
                # 5) 语言
                if LANG.get(tid):
                    val_list = [{"n": "全部", "v": "全部"}]
                    val_list.extend([{"n": x, "v": x} for x in LANG[tid]])
                    groups.append({
                        "key": "lang", "name": "语言",
                        "value": val_list,
                    })
                # 6) 字母
                val_list = [{"n": "全部", "v": "全部"}]
                val_list.extend([{"n": x, "v": x} for x in LETTER])
                groups.append({
                    "key": "letter", "name": "字母",
                    "value": val_list,
                })
                # 7) 排序
                val_list = [{"n": "全部", "v": "全部"}]
                val_list.extend([{"n": n, "v": v} for v, n in SORT_BY])
                groups.append({
                    "key": "by", "name": "排序",
                    "value": val_list,
                })
                filters[tid] = groups
        return {"class": CLASSES, "filters": filters}

    def homeVideoContent(self):
        # 实测首页 / 直接返回带 /film/ 链接的真实 HTML（约 70 个卡片）
        html = self._fetch_html(self.site_url + "/", need="/film/")
        return {"list": self._extract_videos(html)}

    # ================= 列表解析 =================

    def _meta_value(self, body, start_pos):
        """取字段值：到 split-line / 段落结束 / 下一页标签为止。"""
        rest = body[start_pos:]
        # 重点修复：遇到 </p> 或 <p> 或者是下一个 split-line 就停止
        m = re.search(r'</p\s*>|<p\b|<span[^>]*class="[^"]*split-line', rest, re.I)
        chunk = rest[:m.start()] if m else rest
        
        # 提取所有 <a> 标签里的文字，用逗号连接（针对主演这种多个标签的情况）
        names = [self._clean(x) for x in re.findall(r'<a\b[^>]*>([^<]*)</a>', chunk, re.I)]
        names = [x for x in names if x]
        if names:
            # 如果全是逗号连接，可能不太好看，我们用 "/" 或者 "," 都行，这里选 ,
            return ",".join(names)
        
        # 如果没找到 <a>，就清理掉标签直接返回
        return self._clean(re.sub(r'<a\b[^>]*>([^<]*)</a>', r'\1', chunk))

    def _parse_meta(self, seg):
        """从卡片 / 详情片段里取 主演/导演/分类/地区/年份。"""
        out = {}
        for m in _RE_META.finditer(seg):
            key = m.group(1)
            if not key or key in out:
                continue
            val = self._meta_value(seg, m.start(2))
            if val:
                out[key] = val
        return out

    def _extract_videos(self, html):
        """解析列表卡片。"""
        videos, seen = [], set()
        if not html:
            return videos

        for m in _RE_THUMB.finditer(html):
            tag = m.group(0)
            href = self._attr(tag, "href")
            vod_id = self._vod_id_from_href(href)
            if not vod_id or vod_id in seen:
                continue
            seen.add(vod_id)

            # 以 <li> 为界取卡片片段
            p = html.rfind("<li", 0, m.start())
            q = html.find("<li", m.end())
            seg = html[p if p >= 0 else m.start(): q if q > 0 else m.end() + 1500]

            pic = (self._attr(tag, "data-original") or
                   self._attr(tag, "data-src") or
                   self._attr(tag, "src"))
            # 占位图不能当封面
            if pic and ("load.gif" in pic or pic.startswith("data:")):
                pic = ""

            name = self._clean(self._attr(tag, "title"))
            m4 = _RE_H4_TITLE.search(seg)
            if m4 and self._clean(m4.group(1)):
                name = self._clean(m4.group(1))

            remark = ""
            mr = _RE_REMARK.search(seg)
            if mr:
                remark = self._clean(mr.group(1))

            meta = self._parse_meta(seg)

            v = {
                "vod_id": vod_id,
                "vod_name": name or vod_id,
                "vod_pic": self._fix_url(pic),
                "vod_remarks": remark,
            }
            if meta.get("主演"):
                v["vod_actor"] = meta["主演"]
            if meta.get("导演"):
                v["vod_director"] = meta["导演"]
            if meta.get("分类"):
                v["type_name"] = meta["分类"]
            if meta.get("地区"):
                v["vod_area"] = meta["地区"]
            if meta.get("年份"):
                v["vod_year"] = meta["年份"]
            videos.append(v)
        return videos

    def _main_list_videos(self, html):
        """只取主列表，排除左侧"xx推荐"侧栏。"""
        if not html:
            return []
        m = re.search(r'<div class="iqy-panel active iqy-panel-bg clearfix">([\s\S]*)',
                      html)
        if not m:
            m = re.search(r'<h3 class="title">最新[^<]*</h3>([\s\S]*)', html)
        seg = m.group(1) if m else html
        # 主列表到分页区为止，避免把页脚友情链接之类带入
        cut = seg.find('class="iqy-show__page')
        if cut > 0:
            seg = seg[:cut]
        return self._extract_videos(seg)

    def _page_count(self, html, cur_page=1):
        """取总页数。"""
        if not html:
            return cur_page
        # 方式 1: 2/820
        m = re.search(r'>\s*(\d+)\s*/\s*(\d+)\s*<', html)
        if m:
            try:
                total = int(m.group(2))
                if total >= 1:
                    return total
            except Exception:
                pass
        # 方式 2: 尾页链接 /genre/{tid}-{n}.html
        m = re.search(r'href="/genre/\d+-(\d+)\.html"[^>]*>\s*尾页', html)
        if m:
            try:
                return max(1, int(m.group(1)))
            except Exception:
                pass
        # 方式 3: 筛选分页 /filter/.../page/{n}.html 里的尾页
        m = re.search(r'href="[^"]*/page/(\d+)\.html"[^>]*>\s*尾页', html)
        if m:
            try:
                return max(1, int(m.group(1)))
            except Exception:
                pass
        # 方式 4: 取所有 /genre/{tid}-{n} 的页码最大值
        nums = [int(x) for x in re.findall(r'/genre/\d+-(\d+)\.html', html)
                if x.isdigit()]
        if nums:
            return max(nums)
        return cur_page

    # ================= 分类 =================

    def _build_filter_url(self, tid, extend, pg_int):
        """按真实顺序拼接筛选 URL。"""
        sub = (extend.get("id") or "").strip()    # 子分类 tid（类型维度）
        by = (extend.get("by") or "").strip()
        clz = (extend.get("class") or "").strip()
        area = (extend.get("area") or "").strip()
        year = (extend.get("year") or "").strip()
        lang = (extend.get("lang") or "").strip()
        letter = (extend.get("letter") or "").strip()

        # 将 "全部" 或空值视作未筛选
        if sub in ("", "全部"):
            sub = ""
        if clz in ("", "全部"):
            clz = ""
        if area in ("", "全部"):
            area = ""
        if year in ("", "全部"):
            year = ""
        if lang in ("", "全部"):
            lang = ""
        if letter in ("", "全部"):
            letter = ""
        if by in ("", "全部"):
            by = ""

        # by=time 是默认排序，若只选了 time 且无其它条件，仍走 genre 更轻
        effective = [x for x in (sub, clz, area, year, lang, letter) if x]
        if not effective:
            return None

        target = sub or tid
        q = urllib.parse.quote
        parts = ["/filter"]
        if by in ("time", "hits", "score"):
            parts += ["by", by]
        if clz:
            parts += ["class", q(clz)]
        if area:
            parts += ["area", q(area)]
        parts += ["id", target]
        if year:
            parts += ["year", q(year)]
        if lang:
            parts += ["lang", q(lang)]
        if letter:
            parts += ["letter", q(letter)]
        if pg_int > 1:
            parts += ["page", str(pg_int)]
        return self.site_url + "/".join(parts) + ".html"

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or "1")
        pg = str(pg or "1")
        try:
            pg_int = max(1, int(pg))
        except Exception:
            pg_int = 1
        extend = extend or {}

        # 真实入口:
        #   无筛选   第1页 /genre/{tid}.html      后续页 /genre/{tid}-{n}.html
        #   有筛选   /filter/by|class|area|id|year|lang|letter[/page/{n}].html
        url = self._build_filter_url(tid, extend, pg_int)
        if url:
            filtered = True
        else:
            filtered = False
            if pg_int == 1:
                url = "%s/genre/%s.html" % (self.site_url, tid)
            else:
                url = "%s/genre/%s-%d.html" % (self.site_url, tid, pg_int)

        self.log("category: %s" % url)
        html = self._fetch_html(url, need="/film/")

        # 筛选页有"xx推荐"侧栏，必须只扫主列表；无筛选页同样有侧栏，统一走主列表更稳
        videos = self._main_list_videos(html)
        pc = self._page_count(html, pg_int)
        # 防御: 若解析出的总页数小于当前页，说明页面异常，保持当前页
        if pc < pg_int:
            pc = pg_int
        return {
            "list": videos,
            "page": pg_int,
            "pagecount": pc,
            "limit": len(videos) or 20,
            "total": pc * 20 if pc > 1 else len(videos),
        }

    # ================= 搜索 =================

    def searchContent(self, key, quick, pg="1"):
        """搜索。"""
        key = (key or "").strip()
        pg = str(pg or "1")
        try:
            pg_int = max(1, int(pg))
        except Exception:
            pg_int = 1

        # --- 第 1 页：ajax suggest（更快、更稳定） ---
        if pg_int == 1:
            params = urllib.parse.urlencode({"mid": "1", "wd": key})
            api = "%s/index.php/ajax/suggest?%s" % (self.site_url, params)
            self.log("search api: %s" % api)
            obj = self._fetch_json(api)
            if isinstance(obj, dict) and isinstance(obj.get("list"), list):
                videos = []
                for it in obj.get("list") or []:
                    if not isinstance(it, dict):
                        continue
                    vid = it.get("id")
                    if vid in (None, ""):
                        continue
                    # 实测 id=857985 与 /film/857985f.html 对应（详情页 data-id）
                    videos.append({
                        "vod_id": "%sf" % vid,
                        "vod_name": self._clean(it.get("name")),
                        "vod_pic": self._fix_url(it.get("pic") or ""),
                        "vod_remarks": "",
                    })
                if videos:
                    total = obj.get("total")
                    try:
                        total = int(total)
                    except Exception:
                        total = len(videos)
                    pc = obj.get("pagecount") or 1
                    try:
                        pc = int(pc)
                    except Exception:
                        pc = 1
                    return {
                        "list": videos,
                        "page": 1,
                        "pagecount": max(1, pc),
                        "limit": len(videos),
                        "total": total,
                    }

        # --- 兜底/后续页：真实 HTML 搜索页 ---
        kw = urllib.parse.quote(key)
        if pg_int == 1:
            url = "%s/lookup/wd/%s.html" % (self.site_url, kw)
        else:
            url = "%s/lookup/page/%s/wd/%s.html" % (self.site_url, pg_int, kw)
        self.log("search html: %s" % url)
        html = self._fetch_html(url, need="/film/")
        videos = self._extract_videos(html)
        return {
            "list": videos,
            "page": pg_int,
            "pagecount": self._page_count(html, pg_int),
            "limit": len(videos) or 20,
            "total": len(videos),
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ================= 详情 =================

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        if vod_id.startswith("http"):
            url = vod_id
            m = re.search(r'/film/([^/"?]+?)\.html', vod_id, re.I)
            if m:
                vod_id = m.group(1)
        else:
            vid = vod_id.replace(".html", "")
            url = "%s/film/%s.html" % (self.site_url, vid)
            vod_id = vid

        self.log("detail: %s" % url)
        html = self._fetch_html(url, need="iqy-content")
        if not html:
            return {"list": []}

        # ---- 标题 ----
        name = ""
        m = _RE_H1.search(html)
        if m:
            name = self._clean(m.group(1))
        if not name:
            m = re.search(r"<title>([^<]*)</title>", html, re.I)
            if m:
                name = self._clean(m.group(1).split("-")[0].split("_")[0])

        # ---- 封面 ----
        pic = ""
        m = _RE_DETAIL_PIC.search(html)
        if m:
            pic = self._fix_url(m.group(1))
        if not pic:
            for tag in re.findall(r"<img\b[^>]*>", html, re.I):
                u = self._attr(tag, "data-original")
                if u and "load.gif" not in u:
                    pic = self._fix_url(u)
                    break

        # ---- 详细数据 ----
        detail_meta = {}
        # 专门匹配详情页的 <p class="data"> 提取精准信息
        for pm in re.finditer(r'<p[^>]*class="[^"]*data[^"]*"[^>]*>([\s\S]*?)</p>', html, re.I):
            for k, val in self._parse_meta(pm.group(1)).items():
                if k not in detail_meta:
                    detail_meta[k] = val

        # ---- 简介 ----
        content = ""
        m = re.search(
            r'<div class="col-pd text-collapse content">([\s\S]*?)<a class="details"',
            html, re.I)
        if m:
            block = m.group(1)
            cands = []
            mc = _RE_COMMENT.search(block)
            if mc:
                cands.append(self._clean(mc.group(1)))
            md = _RE_HIDDEN_DESC.search(block)
            if md:
                cands.append(self._clean(md.group(1)))
            cands = [c for c in cands if c and c not in ("...", "…")]
            if cands:
                # sketch 通常是截断版，取最长的一段更完整
                content = max(cands, key=len)

        if not content:
            md2 = re.search(
                r'<span class="left text-muted">简介[:：]</span>([\s\S]*?)<a href="#desc"',
                html, re.I)
            if md2:
                content = self._clean(md2.group(1))
        if not content:
            md3 = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html, re.I)
            if md3:
                content = self._clean(md3.group(1))
        if not content:
            content = detail_meta.get("简介", "")

        # 清理简介文本中可能出现的多余换行和空格
        content = re.sub(r'\s+', ' ', content).strip()

        # 用户要求：简介统一加前缀
        content = INTRO_PREFIX + (content or "")

        # ---- 播放线路 + 剧集 ----
        lines = self._extract_play_lines(html, vod_id)
        if not lines["names"]:
            return {"list": []}

        vod = {
            "vod_id": vod_id,
            "vod_name": name or vod_id,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": detail_meta.get("主演", ""),
            "vod_director": detail_meta.get("导演", ""),
            "vod_area": detail_meta.get("地区", ""),
            "vod_year": detail_meta.get("年份", ""),
            "vod_remarks": detail_meta.get("更新", ""),
            "type_name": detail_meta.get("分类", ""),
            "vod_play_from": "$$$".join(lines["names"]),
            "vod_play_url": "$$$".join(lines["urls"]),
        }
        return {"list": [vod]}

    def _extract_play_lines(self, html, vod_id):
        """解析播放地址区。"""
        names, urls = [], []
        if not html:
            return {"names": names, "urls": urls}

        tabs = []
        for m in _RE_TAB.finditer(html):
            lid = m.group(1)
            nm = self._clean(m.group(2))
            if lid and lid not in [t[0] for t in tabs]:
                tabs.append((lid, nm or ("线路%s" % lid)))

        panes = {}
        for m in _RE_PANE.finditer(html):
            lid, block = m.group(1), m.group(2)
            eps, seen = [], set()
            for em in _RE_EP.finditer(block):
                href, ep = em.group(1), self._clean(em.group(2))
                full = self._fix_url(href)
                if full in seen:
                    continue
                seen.add(full)
                eps.append((ep or ("第%d集" % (len(eps) + 1)), full))
            if eps:
                panes[lid] = eps

        ordered = [t for t in tabs if t[0] in panes]
        for lid in sorted(panes.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            if lid not in [t[0] for t in ordered]:
                ordered.append((lid, "线路%s" % lid))

        for lid, nm in ordered:
            eps = panes[lid]
            names.append(nm)
            urls.append("#".join("%s$%s" % (n, u) for n, u in eps))

        return {"names": names, "urls": urls}

    # ================= 播放 =================

    @staticmethod
    def _unescape_js(s):
        """等价于 JS 的 unescape()：%uXXXX 与 %XX。"""
        if not s:
            return ""
        s = re.sub(r"%u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
        s = re.sub(r"%([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)
        return s

    def _decode_play_url(self, url, encrypt):
        """按 /static/js/player.js 的真实逻辑解密。"""
        if not url:
            return ""
        enc = str(encrypt or "0")
        try:
            if enc == "1":
                return self._unescape_js(url)
            if enc == "2":
                raw = base64.b64decode(url + "=" * (-len(url) % 4))
                return self._unescape_js(raw.decode("utf-8", "ignore"))
        except Exception as e:
            self.log("decode FAIL: %s" % e)
        return url

    def playerContent(self, flag, id, vipFlags):
        play_page = id if str(id).startswith("http") else self._fix_url(id)
        self.log("player: %s" % play_page)

        now = int(time.time())
        cached = self._play_cache.get(play_page)
        if cached and now - cached[0] < 600:
            return cached[1]

        html = self._fetch_html(play_page, need="player_")
        media, encrypt, play_from = "", "0", ""

        if html:
            m = _RE_PLAYER.search(html)
            if m:
                try:
                    obj = json.loads(m.group(1))
                except Exception as e:
                    self.log("player json FAIL: %s" % e)
                    obj = {}
                if isinstance(obj, dict):
                    encrypt = obj.get("encrypt", 0)
                    play_from = (obj.get("from") or "").strip()
                    media = self._decode_play_url(obj.get("url") or "", encrypt)
                    if not media:
                        media = self._decode_play_url(obj.get("url_next") or "", encrypt)

        res = None
        if media and re.search(r"\.(m3u8|mp4|flv)(\?|$)", media, re.I):
            res = {
                "parse": 0,
                "playUrl": "",
                "url": media,
                "header": {
                    "User-Agent": UA,
                    "Referer": self.site_url + "/",
                },
            }

        if res is None:
            res = {
                "parse": 1,
                "playUrl": "",
                "url": play_page,
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }
            self.log("player: no direct media, fallback to sniff (from=%s, got=%s)"
                     % (play_from, bool(media)))

        self._play_cache[play_page] = (now, res)
        return res

    # ================= 本地代理（封面 & 媒体） =================

    _CT_MAP = {
        ".m3u8": "application/vnd.apple.mpegurl",
        ".ts": "video/mp2t",
        ".m4s": "video/iso.segment",
        ".key": "application/octet-stream",
        ".mp4": "video/mp4",
        ".flv": "video/x-flv",
        ".mpd": "application/dash+xml",
        ".vtt": "text/vtt",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }

    def _guess_ctype(self, url, fallback=""):
        path = urllib.parse.urlparse(url).path.lower()
        for ext, ct in self._CT_MAP.items():
            if path.endswith(ext):
                return ct
        if fallback and "/" in fallback and "text/html" not in fallback:
            return fallback
        return "application/octet-stream"

    def _parse_proxy_param(self, param):
        url = ""
        if isinstance(param, dict):
            url = param.get("url", "") or param.get("u", "")
        else:
            qs = str(param or "")
            qs = qs.split("?", 1)[-1] if "?" not in qs and "=" not in qs else qs
            for pair in qs.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    if k in ("url", "u"):
                        url = urllib.parse.unquote(v)
        if url and "%" in url and not url.startswith("http"):
            url = urllib.parse.unquote(url)
        return url or ""

    def localProxy(self, param):
        """代理封面图 / m3u8 / 分片。"""
        try:
            url = self._parse_proxy_param(param)
            if not url:
                return [200, "image/jpeg", b"", ""]
            url = self._fix_url(url)

            ref = self.site_url + "/"
            if re.search(r"\.(m3u8|ts|m4s|key|mp4|flv|vtt)(\?|$)", url, re.I):
                p = urllib.parse.urlparse(url)
                ref = "%s://%s/" % (p.scheme, p.netloc)
            elif self.site_url in url:
                ref = self.site_url + "/"

            rsp = self.fetch(url, headers={
                "User-Agent": UA,
                "Referer": ref,
                "Accept": "*/*",
            }, timeout=20)

            content = getattr(rsp, "content", b"") or b""
            hdr_ct = ""
            try:
                hdr_ct = (rsp.headers.get("Content-Type") or "").split(";")[0].strip()
            except Exception:
                pass

            if re.search(r"\.(m3u8|ts|m4s|key|mp4|flv|vtt)(\?|$)", url, re.I):
                ctype = self._guess_ctype(url, hdr_ct)
            else:
                ctype = hdr_ct if hdr_ct.startswith("image/") else self._guess_ctype(url, hdr_ct)

            return [200, ctype, content, ""]
        except Exception as e:
            self.log("localProxy FAIL: %s" % e)
            return [200, "image/jpeg", b"", ""]

    # ================= 其它 =================

    def isVideoFormat(self, url):
        if not url:
            return False
        low = url.lower()
        return any(x in low for x in (".m3u8", ".mp4", ".flv", ".mkv"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def close(self):
        self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
