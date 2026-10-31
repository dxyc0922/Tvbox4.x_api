# coding=utf-8
"""
飞快TV feikuai.in | TVBox Python 爬虫

站点结构：
  - 程序：MacCMS10 + mxtheme 模板（mxtheme / mxprocms 目录）
  - 首页         /                                   卡片 <a class="module-poster-item module-item">
  - 分类首页     /vodtype/{id}.html                   只用于取站点真实分类，不直接列表
  - 列表页       /vodshow/{id}-{area}-{lang}-{letter}-{page}-{year}.html
                 排序参数 /vodshow/{id}--{sort}---------{year}.html
  - 搜索页       /vodsearch/-------------.html?wd={kw}   卡片 <div class="module-card-item module-item">
  - 详情页       /voddetail/{id}.html
  - 播放页       /vodplay/{id}-{sid}-{nid}.html
                 var player_aaaa = {"encrypt":2,"url":"<base64(escape(url))>"}
                 unescape(base64decode(url)) 即为真实播放地址

要点：
  - 线路名取自 module-tab-item 的 data-dropdown-value / data-fk-line-sid，
    再与后面 panel 的 data-fk-line-sid 配对
  - encrypt=2 的 url 走 base64 -> unescape 两重解码；encrypt=1 只做 unescape
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
            if not r.encoding or r.encoding.lower() == 'iso-8859-1':
                r.encoding = 'utf-8'
            return r

        def log(self, *a, **kw):
            try:
                print("[feikuai]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://feikuai.in"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

# 站点导航实测：/vodtype/1.html 电影、2 剧集、3 综艺、4 动漫
CLASSES = [
    {"type_id": "1",  "type_name": "电影"},
    {"type_id": "2",  "type_name": "剧集"},
    {"type_id": "3",  "type_name": "综艺"},
    {"type_id": "4",  "type_name": "动漫"},
    {"type_id": "32", "type_name": "短剧"},
]

# 各分类列表页的“类型”（子分类）
# 注意：短剧(32)本身作为一个独立主分类，如果在这里加“内地剧”等选项，会跳转到剧集的分类，导致混入长剧。
# 因此，为了短剧体验纯粹，我们去掉了短剧的此项筛选，保留其特有的剧情、地区等筛选。
_SUBCATE_NAMES = {
    "1":  ["全部", "喜剧片", "动作片", "科幻片", "爱情片", "战争片", "恐怖片", "剧情片", "其它"],
    "2":  ["全部", "内地剧", "港台剧", "日韩剧", "欧美剧", "短剧", "其它剧"],
    "3":  ["全部", "大陆综艺", "港台综艺", "日韩综艺", "欧美综艺", "其它综艺", "记录"],
    "4":  ["全部", "大陆动漫", "港台动漫", "日韩动漫", "欧美动漫", "其它动漫"],
}

_SUBCATES = {
    "1":  ["", "6", "7", "8", "9", "10", "11", "12", "30"],
    "2":  ["", "13", "14", "15", "16", "32", "31"],
    "3":  ["", "20", "21", "23", "22", "24", "34"],
    "4":  ["", "25", "26", "27", "28", "29"],
}

# 各分类列表页真实筛选词
_GENRES = {
    "1":  ["喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争", "警匪", "犯罪", "动画",
           "奇幻", "武侠", "冒险", "枪战", "悬疑", "惊悚", "经典", "青春", "文艺", "微电影",
           "古装", "历史", "运动", "农村", "儿童", "网络电影"],
    "2":  ["古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作", "奇幻", "剧情", "历史",
           "经典", "乡村", "情景", "商战", "网剧", "其他"],
    "3":  ["选秀", "情感", "访谈", "播报", "旅游", "音乐", "美食", "纪实", "曲艺", "生活",
           "游戏互动", "财经", "求职"],
    "4":  ["情感", "科幻", "热血", "推理", "搞笑", "冒险", "萝莉", "校园", "动作", "机战",
           "运动", "战争", "少年", "少女", "社会", "原创", "亲子", "益智", "励志", "其他"],
    "32": ["古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作", "奇幻", "剧情", "历史",
           "经典", "乡村", "情景", "商战", "网剧", "其他"],
}

_AREAS = {
    "1":  ["大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国", "德国", "泰国",
           "印度", "意大利", "西班牙", "加拿大", "其他"],
    "2":  ["内地", "韩国", "香港", "台湾", "日本", "美国", "泰国", "英国", "新加坡", "其他"],
    "3":  ["内地", "港台", "日韩", "欧美"],
    "4":  ["国产", "日本", "欧美", "其他"],
    "32": ["内地", "韩国", "香港", "台湾", "日本", "美国", "泰国", "英国", "新加坡", "其他"],
}

# 语言
_LANGS = {
    "1":  ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "法语", "德语", "其它"],
    "2":  ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "其它"],
    "3":  ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "其它"],
    "4":  ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "其它"],
    "32": ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "其它"],
}

_YEARS = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017",
          "20年代", "10年代", "00年代", "90年代", "80年代", "70年代", "更早"]

# 字母
_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
            "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "0-9"]

# 排序
_SORTS = [
    {"n": "更新时间", "v": "time"},
    {"n": "豆瓣评分", "v": "score"},
]


def _opts(items):
    return [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in items]


FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    flist = []
    
    # 1. 类型（二级分类）
    if tid in _SUBCATE_NAMES:
        sub_opts = [{"n": n, "v": v} for n, v in zip(_SUBCATE_NAMES[tid], _SUBCATES[tid])]
        flist.append({"key": "sub_id", "name": "类型", "value": sub_opts})

    # 2. 剧情
    if _GENRES.get(tid):
        flist.append({"key": "class", "name": "剧情", "value": _opts(_GENRES[tid])})
        
    # 3. 地区
    flist.append({"key": "area",   "name": "地区", "value": _opts(_AREAS.get(tid, []))})
    
    # 4. 语言
    flist.append({"key": "lang",   "name": "语言", "value": _opts(_LANGS.get(tid, []))})
    
    # 5. 年份
    flist.append({"key": "year",   "name": "年份", "value": _opts(_YEARS)})
    
    # 6. 字母
    flist.append({"key": "letter", "name": "字母", "value": _opts(_LETTERS)})
    
    # 7. 排序
    flist.append({"key": "sort_field", "name": "排序", "value": _SORTS})
    
    FILTERS[tid] = flist


# ===================== 正则 =====================

# 首页 / 列表页卡片
_RE_POSTER_A = re.compile(
    r'<a\s[^>]*href="(/voddetail/\d+\.html)"[^>]*class="[^"]*module-poster-item[^"]*"[^>]*>',
    re.I)

_RE_TITLE_ATTR = re.compile(r'title="([^"]*)"', re.I)
_RE_NOTE = re.compile(r'<div class="module-item-note">([^<]*)</div>', re.I)
_RE_DOUBAN = re.compile(r'<div class="module-item-douban">\s*豆瓣[:：]\s*([\d.]*)\s*分?', re.I)
_RE_IMG = re.compile(
    r'<img[^>]*?(?:data-original|data-remote|src)="([^"]+)"', re.I)
_RE_IMG_ALT = re.compile(r'alt="([^"]*)"', re.I)
_RE_POSTER_TITLE = re.compile(
    r'<div class="module-poster-item-title">([\s\S]*?)</div>', re.I)

# 搜索页卡片
_RE_CARD_BLOCK = re.compile(
    r'<div class="module-card-item[^"]*"\s*>\s*'
    r'<div class="module-card-item-class">([^<]*)</div>\s*'
    r'<a href="(/voddetail/\d+\.html)"[^>]*>([\s\S]*?)'
    r'<div class="module-card-item-title">\s*<a[^>]*>([\s\S]*?)</a>',
    re.S | re.I)

# 详情页
_RE_H1 = re.compile(r'<h1[^>]*>([\s\S]*?)</h1>', re.I)
_RE_TITLE_TAG = re.compile(r'<title>([\s\S]*?)</title>', re.I)
_RE_INTRO = re.compile(
    r'<div class="module-info-introduction-content[^"]*"[^>]*>([\s\S]*?)</div>', re.I)
_RE_BACKDROP = re.compile(
    r'--fk-mobile-backdrop-image:url\(\'([^\']+)\'\)', re.I)
_RE_POSTER_BIG = re.compile(
    r'<div class="module-info-poster">[\s\S]{0,600}?<img[^>]*?(?:data-original|src)="([^"]+)"',
    re.I)

_RE_META_ITEM = re.compile(
    r'<div class="module-info-item">\s*<span class="module-info-item-title">([^<：:]*)'
    r'[：:]?\s*</span>\s*<div class="module-info-item-content">([\s\S]*?)</div>\s*</div>',
    re.S | re.I)

_RE_TAG_LINK = re.compile(
    r'<div class="module-info-tag-link">\s*(?:<a[^>]*>|<span>)([\s\S]*?)</(?:a|span)>', re.I)

# 线路标签
_RE_TAB = re.compile(
    r'<div class="module-tab-item[^"]*"[^>]*?data-dropdown-value="([^"]*)"[^>]*?'
    r'data-fk-line-sid="(\d+)"[^>]*>([\s\S]*?)</div>', re.S | re.I)

# 剧集 panel 与其内部链接
_RE_PANEL = re.compile(
    r'<div class="module-list[^"]*"[^>]*?data-fk-line-sid="(\d+)"[^>]*>([\s\S]*?)'
    r'(?=<div class="module-list[^"]*"[^>]*?data-fk-line-sid="|\Z)', re.I)

# 修复：兼容 class="module-play-list-link active" 或带空格的情况，避免漏集
_RE_EP = re.compile(
    r'<a\s+class="module-play-list-link[^"]*"\s+href="([^"]+)"[^>]*>\s*<span>([\s\S]*?)</span>',
    re.I)

# 分页
_RE_PAGE_BLOCK = re.compile(r'<div id="page">([\s\S]*?)</div>', re.I)
_RE_PAGE_HREF = re.compile(r'href="([^"]+)"[^>]*class="[^"]*page-link[^"]*"', re.I)
_RE_PAGE_TITLE = re.compile(r'title="第(\d+)页"', re.I)

# 播放页 player_aaaa (兼容结尾带分号)
_RE_PLAYER = re.compile(r'var\s+player_aaaa\s*=\s*(\{[\s\S]*?\})\s*;?\s*</script>', re.I)

_TAG_RE = re.compile(r'<[^>]+>')


class Spider(Spider):

    def getName(self):
        return "飞快TV"

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
        self.default_pic = self.site_url + "/mxtheme/images/errorpic.png"
        self._play_cache = {}
        self.log("init site=%s" % self.site_url)

    # ---------------- 基础工具 ----------------

    def _fetch(self, url, timeout=20, headers=None):
        try:
            h = dict(self.headers)
            if headers:
                h.update(headers)
            rsp = self.fetch(url, headers=h, timeout=timeout)
            text = ""
            if hasattr(rsp, "text"):
                text = rsp.text or ""
            elif hasattr(rsp, "content"):
                text = rsp.content.decode("utf-8", "ignore")
            else:
                text = str(rsp)
            return text
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
        s = re.sub(r"</p>\s*<p[^>]*>", "\n", s, flags=re.I)
        s = _TAG_RE.sub("", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">")
              .replace("&ldquo;", "“").replace("&rdquo;", "”")
              .replace("&middot;", "·"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n\s*\n+", "\n", s)
        return s.strip()

    def _pick_img(self, attrs_html, prefer=("data-original", "data-remote", "src")):
        for key in prefer:
            m = re.search(r'%s="([^"]+)"' % re.escape(key), attrs_html, re.I)
            if m:
                u = m.group(1).strip()
                if u and "errorpic" not in u and u not in ("", "#"):
                    return self._fix_url(u)
        return ""

    # ---------------- 列表解析 ----------------

    def _parse_poster_items(self, html):
        out = []
        seen = set()
        marks = [m for m in _RE_POSTER_A.finditer(html)]
        for idx, m in enumerate(marks):
            href = m.group(1)
            if href in seen:
                continue
            end = marks[idx + 1].start() if idx + 1 < len(marks) else min(len(html), m.end() + 3000)
            block = html[m.start():end]
            head = m.group(0)

            name = ""
            mt = _RE_TITLE_ATTR.search(head)
            if mt:
                name = self._clean(mt.group(1))
            if not name:
                mt = _RE_POSTER_TITLE.search(block)
                if mt:
                    name = self._clean(mt.group(1))
            if not name:
                mi = _RE_IMG_ALT.search(block)
                if mi:
                    name = self._clean(mi.group(1))

            img_tag = ""
            mi = _RE_IMG.search(block)
            if mi:
                start = block.rfind("<img", 0, mi.end())
                img_tag = block[start:mi.end() + 1] if start >= 0 else mi.group(0)
            pic = self._pick_img(img_tag or block)

            remarks = ""
            mn = _RE_NOTE.search(block)
            if mn:
                remarks = self._clean(mn.group(1))
            md = _RE_DOUBAN.search(block)
            if md and md.group(1):
                score = md.group(1).strip()
                remarks = ("%s 豆瓣%s" % (remarks, score)).strip() if remarks else ("豆瓣%s" % score)

            seen.add(href)
            out.append({
                "vod_id": href,
                "vod_name": name or href,
                "vod_pic": pic or self.default_pic,
                "vod_remarks": remarks,
            })
        return out

    def _parse_card_items(self, html):
        out = []
        seen = set()
        for m in _RE_CARD_BLOCK.finditer(html):
            cat, href, mid, name = m.group(1), m.group(2), m.group(3), m.group(4)
            if href in seen:
                continue
            seen.add(href)
            pic = self._pick_img(mid)
            remarks = self._clean(cat)
            mn = _RE_NOTE.search(mid)
            if mn:
                note = self._clean(mn.group(1))
                remarks = ("%s %s" % (remarks, note)).strip() if remarks else note
            out.append({
                "vod_id": href,
                "vod_name": self._clean(name) or href,
                "vod_pic": pic or self.default_pic,
                "vod_remarks": remarks,
            })
        return out

    def _extract_list(self, html):
        items = self._parse_poster_items(html)
        if items:
            return items
        return self._parse_card_items(html)

    def _page_count(self, html):
        m = _RE_PAGE_BLOCK.search(html)
        if not m:
            return 1
        block = m.group(1)
        nums = []
        for t in re.findall(r'title="第(\d+)页"', block):
            nums.append(int(t))
        tail = re.search(r'href="([^"]+)"[^>]*title="尾页"', block, re.I)
        if tail:
            mm = re.search(r'-(\d{1,6})-{3}(\d{4})?\.html$', tail.group(1))
            if mm:
                nums.append(int(mm.group(1)))
        cur = re.search(r'page-current[^>]*>\s*(\d+)', block)
        if cur:
            nums.append(int(cur.group(1)))
        if not nums:
            for href in _RE_PAGE_HREF.findall(block):
                mm = re.search(r'-(\d{1,6})-{3}(\d{4})?\.html$', href)
                if mm:
                    nums.append(int(mm.group(1)))
        if not nums:
            return 1
        return max(nums)

    # ---------------- 路由构造 ----------------

    def _build_show_url(self, tid, page, extend):
        sub_id = extend.get("sub_id") or tid

        area   = urllib.parse.quote(extend.get("area")   or "")
        genre  = urllib.parse.quote(extend.get("class")  or "")
        lang   = urllib.parse.quote(extend.get("lang")   or "")
        letter = urllib.parse.quote(extend.get("letter") or "")
        year   = urllib.parse.quote(extend.get("year")   or "")
        sort   = extend.get("sort_field") or ""
        if sort == "time":
            sort = ""
        pg = str(page) if page and int(page) > 1 else ""

        fields = ["", "", "", "", "", "", "", "", "", "", "", ""]
        fields[0]  = sub_id
        fields[1]  = area
        fields[2]  = sort
        fields[3]  = genre
        fields[4]  = lang
        fields[5]  = letter
        fields[8]  = pg
        fields[11] = year
        return "%s/vodshow/%s.html" % (self.site_url, "-".join(fields))

    # ---------------- TVBox 接口 ----------------

    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        html = self._fetch(self.site_url + "/")
        videos = self._extract_list(html)
        self.log("home: %d 条" % len(videos))
        return {"list": videos}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}

        data = {}
        for k in ("sub_id", "class", "area", "lang", "letter", "year", "sort_field"):
            v = extend.get(k)
            if v and v not in ("", "全部", "all"):
                data[k] = v

        url = self._build_show_url(tid, page, data)
        self.log("category: %s" % url)
        html = self._fetch(url)
        videos = self._extract_list(html)

        if not videos and not data:
            fb = "%s/vodtype/%s.html" % (self.site_url, tid)
            self.log("  fallback: %s" % fb)
            html = self._fetch(fb)
            videos = self._extract_list(html)

        pagecount = self._page_count(html)
        self.log("  %d 条, 共 %d 页" % (len(videos), pagecount))

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": len(videos) if videos else 20,
            "total": (pagecount if pagecount > 1 else page) * max(len(videos), 1),
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1
        kw = urllib.parse.quote(key)
        if page > 1:
            url = "%s/vodsearch/%s----------%d---.html" % (self.site_url, kw, page)
        else:
            url = "%s/vodsearch/%s-------------.html" % (self.site_url, kw)
        self.log("search: %s" % url)
        html = self._fetch(url)
        videos = self._extract_list(html)
        self.log("  %d 条" % len(videos))
        return {
            "list": videos,
            "page": page,
            "pagecount": self._page_count(html),
            "limit": len(videos) if videos else 20,
            "total": 999,
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        self.log("detail: %s" % url)

        html = self._fetch(url)
        if not html:
            return {"list": []}

        # ---- 标题 ----
        name = ""
        m = _RE_H1.search(html)
        if m:
            inner = m.group(1)
            mi = re.search(r'alt="([^"]+)"', inner, re.I)
            if mi:
                name = self._clean(mi.group(1))
            if not name:
                name = self._clean(inner)
        if not name:
            m = _RE_TITLE_TAG.search(html)
            if m:
                name = self._clean(m.group(1).split("_")[0].split("-")[0])
        name = re.sub(r"\s*\(\d{4}\)\s*$", "", name).strip() or vod_id

        # ---- 封面 ----
        pic = ""
        m = _RE_POSTER_BIG.search(html)
        if m:
            pic = self._fix_url(m.group(1))
        if not pic:
            m = _RE_BACKDROP.search(html)
            if m:
                pic = self._fix_url(m.group(1))
        if not pic:
            pic = self.default_pic

        # ---- 简介 ----
        content = ""
        m = _RE_INTRO.search(html)
        if m:
            content = self._clean(m.group(1))
        if not content:
            m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html, re.I)
            if m:
                content = self._clean(m.group(1))
        content = (INTRO_PREFIX + "\n" + content) if content else INTRO_PREFIX

        # ---- 元信息 ----
        director = actor = remark = ""
        score = ""
        for mt in _RE_META_ITEM.finditer(html):
            key_name = self._clean(mt.group(1)).replace("：", "").replace(":", "")
            val = self._clean(mt.group(2))
            if not val:
                continue
            if key_name == "导演" and not director:
                director = val.replace("/", ",").replace(" ", "")
            elif key_name == "主演" and not actor:
                actor = re.sub(r"\s*/\s*", ", ", val)
            elif key_name == "状态" and not remark:
                remark = val
            elif key_name == "评分" and not score:
                m_score = re.search(r'(\d+(\.\d+)?)', val)
                if m_score:
                    score = m_score.group(1)

        # 年份/地区/类型 标签
        tags = [self._clean(t) for t in _RE_TAG_LINK.findall(html)]
        tags = [t for t in tags if t and t != name]
        info = " / ".join(tags[:6])

        # 精准提取年份和地区（利用 title 属性）
        title_tags = re.findall(r'<div class="module-info-tag-link">\s*<a\s+[^>]*title="([^"]+)"', html)
        vod_year = next((t for t in title_tags if re.fullmatch(r"(19|20)\d{2}", t)), "")
        vod_area = next((t for t in title_tags if not re.fullmatch(r"(19|20)\d{2}", t)), "")

        # 兜底提取
        if not vod_year:
            vod_year = next((t for t in tags if re.fullmatch(r"(19|20)\d{2}", t)), "")
        if not vod_area:
            exclude_words = "剧情|喜剧|动作|爱情|科幻|动画|悬疑|惊悚|恐怖|犯罪|同性|音乐|歌舞|传记|历史|战争|西部|奇幻|冒险|灾难|武侠|情色|古装|家庭|青春|偶像|乡村|情景|商战|网剧|选秀|情感|访谈|播报|旅游|美食|纪实|曲艺|生活|游戏互动|财经|求职|热血|推理|搞笑|萝莉|校园|机战|少年|少女|社会|原创|亲子|益智|励志|其他|其它"
            for t in tags:
                if t != vod_year and not re.search(exclude_words, t):
                    vod_area = t
                    break

        # ---- 线路 + 剧集 ----
        sid_name = {}
        for mt in _RE_TAB.finditer(html):
            line_name = self._clean(mt.group(1)) or self._clean(mt.group(3))
            sid = mt.group(2)
            if sid and line_name and sid not in sid_name:
                sid_name[sid] = line_name

        groups = []
        for mp in _RE_PANEL.finditer(html):
            sid = mp.group(1)
            body = mp.group(2)
            eps = []
            for me in _RE_EP.finditer(body):
                href = me.group(1).replace("&amp;", "&")
                ep = self._clean(me.group(2))
                if not href:
                    continue
                eps.append((ep or ("第%d集" % (len(eps) + 1)), self._fix_url(href)))
            if eps:
                groups.append((sid, eps))

        self.log("  线路: %s" % [(s, sid_name.get(s, s), len(e)) for s, e in groups])

        if not groups:
            return {"list": []}

        order = [mt.group(2) for mt in _RE_TAB.finditer(html)]
        groups.sort(key=lambda x: order.index(x[0]) if x[0] in order else 999)

        play_from = []
        play_url = []
        for sid, eps in groups:
            alias = sid_name.get(sid) or ("线路%s" % sid)
            if alias in play_from:
                alias = "%s_%s" % (alias, sid)
            play_from.append(alias)
            play_url.append("#".join("%s$%s" % (n, u) for n, u in eps))

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_score": score,
            "vod_year": vod_year,
            "vod_area": vod_area,
            "vod_remarks": remark or info or ("%d条线路" % len(groups)),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    # ---------------- 播放 ----------------

    def _decode_player_url(self, enc, encrypt):
        if not enc:
            return ""
        raw = enc
        if str(encrypt) == "2":
            s = raw.strip()
            s += "=" * (-len(s) % 4)
            try:
                raw = base64.b64decode(s).decode("latin-1")
            except Exception as e:
                self.log("  base64 解码失败: %s" % e)
                return ""
        try:
            return urllib.parse.unquote(raw)
        except Exception:
            return raw

    def playerContent(self, flag, id, vipFlags):
        play_page = id if str(id).startswith("http") else self._fix_url(id)
        self.log("player: %s" % play_page)

        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600:
                return res

        html = self._fetch(play_page, headers={"Referer": play_page})
        m = _RE_PLAYER.search(html) if html else None

        if m:
            try:
                data = json.loads(m.group(1))
            except Exception as e:
                self.log("  player_aaaa JSON 解析失败: %s" % e)
                data = {}

            url = self._decode_player_url(data.get("url", ""), data.get("encrypt", 0))
            from_name = data.get("from", "")
            self.log("  encrypt=%s from=%s url=%s" % (
                data.get("encrypt"), from_name, (url or "EMPTY")[:160]))

            if url:
                res = {
                    "parse": 0,
                    "playUrl": "",
                    "url": url,
                    "header": {
                        "User-Agent": UA,
                        "Referer": self.site_url + "/",
                    },
                }
                low = url.lower()
                if not (".m3u8" in low or ".mp4" in low or "m3u8" in low):
                    res["parse"] = 1
                    res["jx"] = 0
                self._play_cache[play_page] = (now, res)
                return res

        res = {
            "parse": 1,
            "playUrl": "",
            "url": play_page,
            "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
        }
        self._play_cache[play_page] = (now, res)
        return res

    def localProxy(self, param):
        try:
            url = ""
            if isinstance(param, dict):
                url = param.get("url", "")
            else:
                for pair in str(param).split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        if k == "url":
                            url = urllib.parse.unquote(v)
            if not url:
                return [200, "image/jpeg", b"", ""]
            url = self._fix_url(url)
            rsp = self.fetch(url, headers={
                "User-Agent": UA, "Referer": self.site_url + "/"}, timeout=15)
            content = rsp.content
            ctype = rsp.headers.get("Content-Type", "image/jpeg")
            if not ctype.startswith("image/"):
                ctype = "image/jpeg"
            return [200, ctype, content, ""]
        except Exception:
            return [200, "image/jpeg", b"", ""]

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return ".m3u8" in u or ".mp4" in u

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def close(self):
        self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
