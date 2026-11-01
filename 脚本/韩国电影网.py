# coding=utf-8
"""
韩国电影网 shukanbaoxw.com | TVBox Python 爬虫
网站结构（macCMS + ewave 模板 a_0004）
分类 URL 精确拼装（12 段 11 个短横线）：
  /vodshow/{分类}-{地区}-{排序}-{剧情}-{语言}-{字母}---{页码}---{年份}.html
"""
import re
import sys
import json
import time
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

    class _BaseSpider:
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
            r.encoding = 'utf-8'
            return r

        def log(self, *a, **kw):
            try:
                print("[shukanbao]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.shukanbaoxw.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/template/a_0004/img/load.gif"

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

CLASSES = [
    {"type_id": "1",  "type_name": "电影"},
    {"type_id": "2",  "type_name": "电视剧"},
    {"type_id": "3",  "type_name": "综艺"},
    {"type_id": "4",  "type_name": "动漫"},
    {"type_id": "20", "type_name": "短剧"},
]

_SUB_CLASS = {
    "1":  [("全部", "1"), ("动作片", "6"), ("喜剧片", "7"), ("爱情片", "8"),
           ("科幻片", "9"), ("恐怖片", "10"), ("剧情片", "11"),
           ("战争片", "12"), ("纪录片", "21"), ("动漫片", "26")],
    "2":  [("全部", "2"), ("国产剧", "13"), ("港剧", "14"), ("台剧", "15"),
           ("日剧", "16"), ("韩剧", "22"), ("泰剧", "23"), ("美剧", "24"),
           ("海外剧", "25")],
    "3":  [("全部", "3"), ("大陆综艺", "27"), ("日韩综艺", "28"),
           ("港台综艺", "29"), ("欧美综艺", "30")],
    "4":  [("全部", "4"), ("国产动漫", "31"), ("日韩动漫", "32"),
           ("港台动漫", "33"), ("欧美动漫", "34"), ("海外动漫", "35")],
    "20": [("全部", "20")],
}

_YEARS = [{"n": "全部", "v": ""}] + \
         [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]

_AREAS = {
    "1": ["全部", "大陆", "香港", "台湾", "美国", "法国", "英国", "日本",
          "韩国", "德国", "泰国", "印度", "意大利", "西班牙", "加拿大", "其他"],
    "2": ["全部", "大陆", "内地", "韩国", "香港", "台湾", "日本", "美国",
          "泰国", "英国", "新加坡", "其他"],
    "3": ["全部", "大陆", "内地", "韩国", "香港", "台湾", "日本", "美国",
          "泰国", "英国", "新加坡", "其他"],
    "4": ["全部", "大陆", "内地", "韩国", "香港", "台湾", "日本", "美国",
          "泰国", "英国", "新加坡", "其他"],
    "20": ["全部", "大陆", "内地", "韩国", "香港", "台湾", "日本", "美国",
           "泰国", "英国", "新加坡", "其他"],
}

_GENRES = {
    "1":  ["全部", "喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争",
           "警匪", "犯罪", "动画", "奇幻", "武侠", "冒险", "枪战", "悬疑",
           "惊悚", "经典", "青春", "文艺", "微电影", "古装", "历史", "运动",
           "农村", "儿童", "网络电影"],
    "2":  ["全部", "古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作",
           "奇幻", "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他"],
    "3":  ["全部", "真人秀", "脱口秀", "喜剧", "晚会", "音乐", "纪录", "游戏",
           "生活", "文化", "相声", "情感", "悬疑", "美食", "竞技"],
    "4":  ["全部", "冒险", "喜剧", "奇幻", "剧情", "科幻", "动作", "儿童",
           "悬疑", "都市", "家庭", "日常", "爱情", "玄幻", "治愈", "校园"],
    "20": ["全部", "古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作",
           "奇幻", "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他"],
}

# 语言（来自真实筛选区）
_LANGS = ["全部", "国语", "英语", "粤语", "闽南语", "韩语", "日语", "其它"]

# 字母（来自真实筛选区）
_LETTERS = ["全部"] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

_SORTS = [
    {"n": "按时间", "v": "time"},
    {"n": "按人气", "v": "hits"},
    {"n": "按评分", "v": "score"},
]

FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    subs = _SUB_CLASS.get(tid, [("全部", tid)])
    FILTERS[tid] = [
        {"key": "class", "name": "分类",
         "value": [{"n": n, "v": ("" if n == "全部" else v)} for n, v in subs]},
        {"key": "area", "name": "地区",
         "value": [{"n": x, "v": ("" if x == "全部" else x)}
                   for x in _AREAS.get(tid, ["全部"])]},
        {"key": "year", "name": "年份", "value": _YEARS},
        {"key": "genre", "name": "剧情",
         "value": [{"n": x, "v": ("" if x == "全部" else x)}
                   for x in _GENRES.get(tid, ["全部"])]},
        {"key": "lang", "name": "语言",
         "value": [{"n": x, "v": ("" if x == "全部" else x)}
                   for x in _LANGS]},
        {"key": "letter", "name": "字母",
         "value": [{"n": x, "v": ("" if x == "全部" else x)}
                   for x in _LETTERS]},
        {"key": "sort", "name": "排序", "value": _SORTS},
    ]


# ===================== 正则（全部对应真实源码） =====================

_RE_CARD = re.compile(
    r'<div[^>]*class="[^"]*ewave-vodlist__thumb[^"]*"[^>]*?'
    r'title="([^"]*)"[^>]*?'
    r'data-original="([^"]*)"[^>]*?>'
    r'[\s\S]*?'
    r'<span[^>]*class="[^"]*pic-text[^"]*"[^>]*>([^<]*)</span>'
    r'[\s\S]*?'
    r'<a[^>]*class="thumb-link"[^>]*href="([^"]+)"',
    re.S | re.I)

_RE_SEARCH_CARD = re.compile(
    r'<li[^>]*class="[^"]*active[^"]*"[^>]*>'
    r'[\s\S]*?'
    r'<a[^>]*class="[^"]*v-thumb[^"]*ewave-vodlist__thumb[^"]*"[^>]*?'
    r'href="([^"]+)"[^>]*?'
    r'title="([^"]*)"[^>]*?'
    r'data-original="([^"]*)"[^>]*?>'
    r'[\s\S]*?'
    r'<span[^>]*class="[^"]*pic-text[^"]*"[^>]*>([^<]*)</span>',
    re.S | re.I)

_RE_H1 = re.compile(r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>([\s\S]*?)</h1>', re.I)
_RE_DETAIL_PIC = re.compile(
    r'<div[^>]*class="[^"]*ewave-content__thumb[^"]*"[\s\S]*?'
    r'data-original="([^"]+)"', re.S | re.I)

_RE_DESC_FULL = re.compile(
    r'<div[^>]*id="desc"[\s\S]*?<p[^>]*class="[^"]*col-pd[^"]*"[^>]*>([\s\S]*?)</p>',
    re.S | re.I)
_RE_DESC_SHORT = re.compile(
    r'<p[^>]*class="[^"]*desc[^"]*"[^>]*>[\s\S]*?简介：</span>([\s\S]*?)<a\s+href="#desc"',
    re.S | re.I)

_RE_ACTOR = re.compile(
    r'<span[^>]*class="[^"]*text-muted[^"]*">主演：</span>([\s\S]*?)</p>',
    re.S | re.I)
_RE_DIRECTOR = re.compile(
    r'<span[^>]*class="[^"]*text-muted[^"]*">导演：</span>([\s\S]*?)</p>',
    re.S | re.I)

# 类型：<span>类型：</span><a>国产剧</a>&nbsp;<a>国产</a>...<span class="split-line">
_RE_TYPE = re.compile(
    r'<span[^>]*class="[^"]*text-muted[^"]*">类型：</span>([\s\S]*?)<span[^>]*class="[^"]*split-line[^"]*"',
    re.S | re.I)

# 地区：<span>地区：</span><a>大陆</a>
_RE_AREA = re.compile(
    r'<span[^>]*class="[^"]*text-muted[^"]*">地区：</span>\s*<a[^>]*>([^<]+)</a>',
    re.I)

# 年份：<span>年份：</span><a>2026</a>
_RE_YEAR = re.compile(
    r'<span[^>]*class="[^"]*text-muted[^"]*">年份：</span>\s*<a[^>]*>([^<]+)</a>',
    re.I)

# 更新：<span>更新：</span>2026-10-15 21:36:03
_RE_UPDATE = re.compile(
    r'<span[^>]*class="[^"]*text-muted[^"]*">更新：</span>\s*([^<\n]+)',
    re.I)

# 语言：对白语言为国语
_RE_LANG = re.compile(r'对白语言为([^。<]+)', re.I)

_RE_SCORE = re.compile(
    r'<span[^>]*class="[^"]*score[^"]*raty-score-num[^"]*"[^>]*>([\d.]+)</span>',
    re.I)

_RE_PLAYLIST_BLOCK = re.compile(
    r'<ul[^>]*class="[^"]*ewave-content__playlist[^"]*"[^>]*>([\s\S]*?)</ul>',
    re.S | re.I)
_RE_EPISODE = re.compile(
    r'<li[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([^<]*)</a>', re.S | re.I)

# 线路名：<div class="playlist-slide"><ul>...<a href="#playlist1">高清云播</a>...</ul></div>
_RE_PLAYLIST_SLIDE = re.compile(
    r'<div[^>]*class="[^"]*playlist-slide[^"]*"[^>]*>([\s\S]*?)</div>',
    re.S | re.I)

_RE_PLAYER = re.compile(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>', re.S)

_RE_PAGE_NUM = re.compile(r'<span class="num">(\d+)/(\d+)</span>', re.I)

_RE_PAGE_BLOCK = re.compile(
    r'<ul[^>]*class="[^"]*ewave-page[^"]*"[^>]*>([\s\S]*?)</ul>',
    re.S | re.I)
_RE_PAGE_LINK = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(\d+)</a>', re.I)


class Spider(Spider):

    def getName(self):
        return "韩国电影网"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}
        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.site_url + "/",
        }
        self.default_pic = DEFAULT_PIC
        self._play_cache = {}
        self._page_links_cache = {}
        self.log("init: site=%s" % self.site_url)

    # ---------- 基础 ----------
    def _fetch(self, url, timeout=15, headers=None):
        try:
            h = dict(self.headers)
            if headers:
                h.update(headers)
            rsp = self.fetch(url, headers=h, timeout=timeout)
            if hasattr(rsp, "text"):
                return rsp.text or ""
            if hasattr(rsp, "content"):
                return rsp.content.decode("utf-8", "ignore")
            return str(rsp)
        except Exception as e:
            self.log("fetch FAIL %s -> %s" % (url, e))
            return ""

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip()
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
        s = re.sub(r"<[^>]+>", "", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    # ---------- 列表解析 ----------
    def _extract_list_videos(self, html):
        videos = []
        seen = set()
        if not html:
            return videos
        for title, pic, remark, href in _RE_CARD.findall(html):
            if href in seen:
                continue
            seen.add(href)
            videos.append({
                "vod_id":      href,
                "vod_name":    self._clean(title),
                "vod_pic":     self._fix_url(pic) or self.default_pic,
                "vod_remarks": self._clean(remark),
            })
        return videos

    def _extract_search_videos(self, html):
        videos = []
        seen = set()
        if not html:
            return videos
        for href, title, pic, remark in _RE_SEARCH_CARD.findall(html):
            if href in seen:
                continue
            seen.add(href)
            videos.append({
                "vod_id":      href,
                "vod_name":    self._clean(title),
                "vod_pic":     self._fix_url(pic) or self.default_pic,
                "vod_remarks": self._clean(remark),
            })
        return videos

    def _page_count(self, html):
        if not html:
            return 1
        m = _RE_PAGE_NUM.search(html)
        if m:
            try:
                return int(m.group(2))
            except Exception:
                pass
        return 1

    def _extract_page_links(self, html):
        result = {}
        if not html:
            return result
        m = _RE_PAGE_BLOCK.search(html)
        if not m:
            return result
        block = m.group(1)
        for href, num in _RE_PAGE_LINK.findall(block):
            href = href.replace("&amp;", "&")
            if href.startswith("/"):
                href = self.site_url + href
            try:
                result[int(num)] = href
            except Exception:
                pass
        return result

    # ---------- 首页/分类/搜索 ----------
    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        html = self._fetch(self.site_url + "/")
        return {"list": self._extract_list_videos(html)}

    def _build_url(self, tid, extend, page=1):
        """分类 URL 精确拼装（12 段 11 个短横线）：
        /vodshow/{分类}-{地区}-{排序}-{剧情}-{语言}-{字母}---{页码}---{年份}.html
        真实例：
          2-----------.html                  无筛选
          2-%E5%A4%A7%E9%99%86----------.html  地区=大陆
          2---%E5%8F%A4%E8%A3%85--------.html  剧情=古装
          2-----------2026.html              年份=2026
          2--hits---------.html              排序=hits
          2----%E5%9B%BD%E8%AF%AD-------.html  语言=国语
          2-----A------.html                 字母=A
          2--------2---.html                 第2页
        """
        tid = str(tid)
        sub = extend.get("class", "") or ""
        if sub:
            tid = str(sub)

        area   = extend.get("area", "") or ""
        sort   = extend.get("sort", "") or ""
        genre  = extend.get("genre", "") or ""
        lang   = extend.get("lang", "") or ""
        letter = extend.get("letter", "") or ""
        year   = extend.get("year", "") or ""
        page_seg = str(page) if page > 1 else ""

        area_enc  = urllib.parse.quote(area) if area else ""
        genre_enc = urllib.parse.quote(genre) if genre else ""
        lang_enc  = urllib.parse.quote(lang) if lang else ""

        # 段序：0分类 1地区 2排序 3剧情 4语言 5字母 6空 7空 8页码 9空 10空 11年份
        # 模板：%s-%s-%s-%s-%s-%s---%s---%s
        # 短横线数：5 + 3 + 3 = 11 个
        return "%s/vodshow/%s-%s-%s-%s-%s-%s---%s---%s.html" % (
            self.site_url,
            tid,        # 段0 分类
            area_enc,   # 段1 地区
            sort,       # 段2 排序
            genre_enc,  # 段3 剧情
            lang_enc,   # 段4 语言
            letter,     # 段5 字母
            page_seg,   # 段8 页码
            year,       # 段11 年份
        )

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not extend:
            extend = {}

        url = self._build_url(tid, extend, page)
        self.log("category: %s" % url)

        html = self._fetch(url)
        videos = self._extract_list_videos(html)
        pagecount = self._page_count(html)
        self.log("  %d 条, 共 %d 页" % (len(videos), pagecount))

        return {
            "list": videos, "page": page, "pagecount": pagecount,
            "limit": 36, "total": pagecount * 36,
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        kw = urllib.parse.quote(key)
        url = "%s/vodsearch/%s----------%d---.html" % (self.site_url, kw, page)
        self.log("search: %s" % url)
        html = self._fetch(url)
        videos = self._extract_search_videos(html)
        return {
            "list": videos, "page": page,
            "pagecount": self._page_count(html),
            "limit": 36, "total": 999,
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ---------- 详情 ----------
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        self.log("detail: %s" % url)

        html = self._fetch(url)
        if not html:
            return {"list": []}

        # 标题
        name = ""
        m = _RE_H1.search(html)
        if m:
            raw = m.group(1)
            raw = re.sub(r'<span[^>]*class="[^"]*score[^"]*"[^>]*>[\s\S]*?</span>',
                         "", raw)
            ms = re.search(r"<span[^>]*>([\s\S]*?)</span>", raw)
            if ms:
                name = self._clean(ms.group(1))
            if not name:
                name = self._clean(raw)
        if not name:
            m = re.search(r"<title>(.*?)</title>", html, re.S)
            if m:
                name = self._clean(m.group(1).split("_")[0].split("-")[0])
        name = re.sub(r"\s*\(\d{4}\)\s*$", "", name).strip() or vod_id

        # 封面
        pic = self.default_pic
        m = _RE_DETAIL_PIC.search(html)
        if m:
            pic = self._fix_url(m.group(1))
        else:
            m2 = re.search(r'data-original="(https?://[^"]+/upload/vod/[^"]+)"', html)
            if m2:
                pic = m2.group(1)

        # 简介
        content = ""
        m = _RE_DESC_FULL.search(html)
        if m:
            content = self._clean(m.group(1))
            if "剧情简介：" in content:
                content = content.split("剧情简介：", 1)[1]
            elif "剧情:" in content:
                content = content.split("剧情:", 1)[1]
            content = re.sub(r"^[》\s：:]*", "", content).strip()
        if not content:
            m = _RE_DESC_SHORT.search(html)
            if m:
                content = self._clean(m.group(1))
        if not content:
            m = re.search(
                r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
                html, re.I)
            if m:
                content = self._clean(m.group(1))
                content = re.sub(r"^[^：:]*剧情[:：]", "", content).strip()

        content = INTRO_PREFIX + "\n" + content if content else INTRO_PREFIX

        # 主演
        actor = ""
        m = _RE_ACTOR.search(html)
        if m:
            names = re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1))
            actor = " ".join(self._clean(x) for x in names if self._clean(x))

        # 导演
        director = ""
        m = _RE_DIRECTOR.search(html)
        if m:
            names = re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1))
            director = " ".join(self._clean(x) for x in names if self._clean(x))

        # 类型
        type_name = ""
        m = _RE_TYPE.search(html)
        if m:
            names = re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1))
            type_name = " ".join(self._clean(x) for x in names if self._clean(x))

        # 地区
        area = ""
        m = _RE_AREA.search(html)
        if m:
            area = self._clean(m.group(1))

        # 年份
        year = ""
        m = _RE_YEAR.search(html)
        if m:
            year = self._clean(m.group(1))

        # 更新时间
        update_time = ""
        m = _RE_UPDATE.search(html)
        if m:
            update_time = self._clean(m.group(1))

        # 语言
        lang = ""
        m = _RE_LANG.search(html)
        if m:
            lang = self._clean(m.group(1))
        if not lang:
            lang = "国语"

        # 评分
        score = ""
        m = _RE_SCORE.search(html)
        if m:
            score = m.group(1)

        # 选集
        episodes = []
        m = _RE_PLAYLIST_BLOCK.search(html)
        if m:
            block = m.group(1)
            for href, ep_name in _RE_EPISODE.findall(block):
                href = href.replace("&amp;", "&")
                if href.startswith("/"):
                    href = self.site_url + href
                episodes.append((self._clean(ep_name) or "播放", href))

        if not episodes:
            return {"list": []}

        play_url = "#".join("%s$%s" % (n, h) for n, h in episodes)

        # 线路名：从详情页 playlist-slide 解析（真实：<a>高清云播</a>）
        play_from = ""
        m = _RE_PLAYLIST_SLIDE.search(html)
        if m:
            names = re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1))
            names = [self._clean(n) for n in names if self._clean(n)]
            if names:
                play_from = "$$$".join(names)
        if not play_from:
            play_from = "高清云播"

        # 备注：优先网页“更新”时间，否则集数
        remarks = update_time if update_time else (
            "%d集" % len(episodes) if len(episodes) > 1 else "")

        return {"list": [{
            "vod_id":       vod_id,
            "vod_name":     name,
            "vod_pic":      pic,
            "vod_content":  content,
            "vod_actor":    actor,
            "vod_director": director,
            "vod_score":    score,
            "vod_year":     year,
            "vod_area":     area,
            "vod_lang":     lang,
            "vod_class":    type_name,
            "type_name":    type_name,
            "vod_remarks":  remarks,
            "vod_play_from": play_from,
            "vod_play_url":  play_url,
        }]}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        self.log("player: %s" % play_page)

        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600:
                return res

        html = self._fetch(play_page)
        m3u8 = ""
        m = _RE_PLAYER.search(html)
        if m:
            try:
                obj = json.loads(m.group(1))
                m3u8 = obj.get("url", "") or ""
                m3u8 = m3u8.replace("\\/", "/")
            except Exception as e:
                self.log("player_aaaa parse fail: %s" % e)

        if m3u8:
            self.log("  m3u8: %s" % m3u8[:160])
            res = {
                "parse": 0,
                "playUrl": "",
                "url": m3u8,
                "header": {
                    "User-Agent": UA,
                    "Referer": self.site_url + "/",
                },
            }
            self._play_cache[play_page] = (now, res)
            return res

        res = {"parse": 1, "playUrl": "", "url": play_page,
               "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}
        self._play_cache[play_page] = (now, res)
        return res

    def localProxy(self, param):
        return [200, "image/jpeg", b"", ""]

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url or url.startswith("http")

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._page_links_cache.clear()

    def close(self):
        self.destroy()



# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = []
_TVBOX_LINE_ORDER = ["高清云播"]

def _tvbox_filter_lines(result, drop):
    if not isinstance(result, dict):
        return result
    items = result.get('list')
    if isinstance(items, list):
        for item in items:
            _tvbox_filter_item(item, drop)
    else:
        _tvbox_filter_item(result, drop)
    return result

def _tvbox_filter_item(item, drop):
    froms = item.get('vod_play_from') or ''
    urls = item.get('vod_play_url') or ''
    if not isinstance(froms, str) or not isinstance(urls, str):
        return
    if '$$$' not in froms:
        return
    parts_from = [f.strip() for f in froms.split('$$$')]
    parts_url = urls.split('$$$')
    if len(parts_from) != len(parts_url):
        return
    keep = [(f, u) for f, u in zip(parts_from, parts_url) if f not in drop]
    if not keep or len(keep) == len(parts_from):
        return
    item['vod_play_from'] = '$$$'.join(f for f, _ in keep)
    item['vod_play_url'] = '$$$'.join(u for _, u in keep)

def _tvbox_sort_lines(result, order):
    if not order or not isinstance(result, dict):
        return result
    items = result.get('list')
    if isinstance(items, list):
        for item in items:
            _tvbox_sort_item(item, order)
    else:
        _tvbox_sort_item(result, order)
    return result

def _tvbox_sort_item(item, order):
    froms = item.get('vod_play_from') or ''
    urls = item.get('vod_play_url') or ''
    if not isinstance(froms, str) or not isinstance(urls, str):
        return
    if '$$$' not in froms:
        return
    parts_from = [f.strip() for f in froms.split('$$$')]
    parts_url = urls.split('$$$')
    if len(parts_from) != len(parts_url):
        return
    known = {f: i for i, f in enumerate(order)}
    pairs = list(zip(parts_from, parts_url))
    # 已知线路按 order（画质速度最优在前），未知线路稳定保持原序后置。
    pairs.sort(key=lambda p: known.get(p[0], len(order)))
    item['vod_play_from'] = '$$$'.join(f for f, _ in pairs)
    item['vod_play_url'] = '$$$'.join(u for _, u in pairs)

def _tvbox_apply(cls):
    fn = getattr(cls, 'detailContent', None)
    if fn is None:
        return
    def wrapper(self, *a, _fn=fn, **k):
        res = _tvbox_filter_lines(_fn(self, *a, **k), _TVBOX_DROP_LINES)
        return _tvbox_sort_lines(res, _TVBOX_LINE_ORDER)
    setattr(cls, 'detailContent', wrapper)

_tvbox_apply(Spider)
