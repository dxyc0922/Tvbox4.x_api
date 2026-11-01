# coding=utf-8
"""
达达兔影视 wangsoso.com | TVBox Python 爬虫
说明:
  - 本站为 maccms(苹果CMS) + ewave/a_0013 模板，已关闭 JSON 接口(api.php 返回 closed)，全部走 HTML 解析
  - 列表页为 /vodshow/ 模式(带分页+筛选)，/vodtype/ 页无分页、仅板块聚合，故分类走 vodshow
  - 播放页为 maccms 标准 player_aaaa，url 为可直连的 m3u8(实测无需 Referer)
实测结构:
  首页        : /                                  板块 + 卡片，卡片 data-original/data-background
  分类列表    : /vodshow/{id}--{sort}------{page}---.html
  分类+地区   : /vodshow/{id}-{area}-{sort}------{page}---.html
  搜索        : /vodsearch/{kw}----------{page}---.html   (每页 10 条)
  详情        : /voddetail/{id}.html                  h1.media-title / ul.desc / #ewave-playlist-N
  播放        : /vodplay/{id}-{sid}-{nid}.html        player_aaaa 里的 url / from / encrypt
"""
import re
import sys
import json
import time
import html as _html
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
                print("[wangsoso]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.wangsoso.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

DEFAULT_PIC = ""

# 顶部导航实测: /vodtype/1.html 电影 … /vodtype/36.html 短剧
CLASSES = [
    {"type_id": "1",  "type_name": "电影"},
    {"type_id": "2",  "type_name": "电视剧"},
    {"type_id": "3",  "type_name": "综艺"},
    {"type_id": "4",  "type_name": "动漫"},
    {"type_id": "35", "type_name": "动画片"},
    {"type_id": "36", "type_name": "短剧"},
]

# 排序实测值: 页面 list-order 里为 time / hits / score
_SORTS = [
    {"n": "按更新", "v": "time"},
    {"n": "按人气", "v": "hits"},
    {"n": "按评分", "v": "score"},
]

# 年份选项取自 /map.html 实际生成链接
_YEARS = [{"n": "全部", "v": ""}] + \
         [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]

# 各主分类真实地区值(来自 /map.html 的分类链接，注意电影用"大陆/香港/台湾"，其余用"内地")
_AREAS_MOVIE = ["大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国",
                "德国", "泰国", "印度", "意大利", "西班牙", "加拿大", "其他"]

# 分类(class)实测值，取自 /map.html 各分类的第四段参数
_FILTERS_MAP = {
    "1": ["全部", "喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争", "警匪",
          "犯罪", "动画", "奇幻", "武侠", "冒险", "枪战", "悬疑", "惊悚", "经典",
          "青春", "文艺", "微电影", "古装", "历史", "运动", "农村", "儿童", "网络电影"],
    "2": ["全部", "古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作", "奇幻",
          "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他"],
    "3": ["全部", "选秀", "情感", "访谈", "播报", "旅游", "音乐", "美食", "纪实",
          "曲艺", "生活", "游戏互动", "财经", "求职"],
    "4": ["全部", "情感", "科幻", "热血", "推理", "搞笑", "冒险", "萝莉", "校园",
          "动作", "机战", "运动", "战争", "少年", "少女", "社会", "原创", "亲子",
          "益智", "励志", "其他"],
    "35": ["全部", "古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作", "奇幻",
           "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他"],
    "36": ["全部", "古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作", "奇幻",
           "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他"],
}

FILTERS = {}
for _c in CLASSES:
    _tid = _c["type_id"]
    _areas = _AREAS_MOVIE if _tid == "1" else \
        ["内地", "韩国", "香港", "台湾", "日本", "美国", "泰国", "英国", "新加坡", "其他"]
    FILTERS[_tid] = [
        {"key": "class", "name": "分类",
         "value": [{"n": x, "v": "" if x == "全部" else x}
                   for x in _FILTERS_MAP.get(_tid, ["全部"])]},
        {"key": "area", "name": "地区",
         "value": [{"n": "全部", "v": ""}] + [{"n": a, "v": a} for a in _areas]},
        {"key": "year", "name": "年份", "value": _YEARS},
        {"key": "sort_field", "name": "排序", "value": _SORTS},
    ]


# ===================== 正则 =====================
# 列表卡片: <a class="video-link" href="/voddetail/123.html" title="名称">
#             <div class="item-pic ..." data-original="图片(或 data-background)">
#             <div class="video-duration">更新至HD</div>
# 先按 href 切段，再从段内取图/角标，避免跨卡片串行
_RE_CARD_START = re.compile(
    r'href="(/voddetail/(\d+)\.html)"\s+title="([^"]*)"', re.I)
_RE_PIC_ATTR = re.compile(
    r'(?:data-original|data-background|data-src|src)="([^"]+)"', re.I)
_RE_DURATION = re.compile(r'<div class="video-duration">([^<]*)</div>', re.I)

# 兜底: 纯 href + title
_RE_HREF_TITLE = re.compile(
    r'href="(/voddetail/(\d+)\.html)"\s+title="([^"]*)"', re.I)

# 文字列表: <span class="text-list-name">名称</span><small ...>更新至xx</small>
_RE_TEXT_ITEM = re.compile(
    r'href="(/voddetail/(\d+)\.html)"[^>]*>[\s\S]{0,120}?'
    r'<span class="text-list-name">([^<]*)</span>'
    r'(?:[\s\S]{0,120}?<small[^>]*>([^<]*)</small>)?',
    re.S | re.I)

# 搜索结果条目: 按 div.detail-wrap row 分块，块内取 href/title/封面/年份地区
_RE_SEARCH_BLOCK = re.compile(r'<div class="detail-wrap row">([\s\S]*?)</div></div></div>', re.S)
_RE_S_LINK = re.compile(
    r'href="(/voddetail/(\d+)\.html)"\s+title="([^"]*)"', re.I)
_RE_S_PIC = re.compile(r'(?:data-original|data-src|src)="([^"]+)"', re.I)
_RE_S_DESC = re.compile(r'<ul class="desc">([\s\S]*?)</ul>', re.I)
_RE_S_FIRSTLI = re.compile(r'<li>([\s\S]*?)</li>', re.I)

# 详情页
_RE_H1 = re.compile(r'<h1[^>]*class="[^"]*media-title[^"]*"[^>]*>([\s\S]*?)</h1>', re.I)
_RE_COVER = re.compile(r'<div class="detail-img">\s*<img[^>]*src="([^"]*)"', re.I)
_RE_COVER2 = re.compile(r'<div class="detail-cover blur lazyload"[^>]*data-original="([^"]*)"', re.I)

# 详情 desc 各字段 (已补全正则，支持包含 <a> 标签的结构)
_RE_ACTOR = re.compile(r'主演：([\s\S]*?)</li>', re.I)
_RE_DIRECTOR = re.compile(r'导演：([\s\S]*?)</li>', re.I)
_RE_TYPE = re.compile(r'类型：([\s\S]*?)</li>', re.I)
_RE_STATE = re.compile(r'状态：([^<]*)<', re.I)
_RE_YEAR = re.compile(r'年份：<span>([^<]*)</span>', re.I)
_RE_AREA = re.compile(r'地区：<span>([^<]*)</span>', re.I)
_RE_LANG = re.compile(r'语言：<span>([^<]*)</span>', re.I)
_RE_DOUBAN = re.compile(r'豆瓣：([\d.]+)分', re.I)
_RE_HITS = re.compile(r'data-type="hits">(\d+)<', re.I)
_RE_UPDATE = re.compile(r'更新：<span>([^<]*)</span>', re.I)
_RE_INTRO = re.compile(r'简介：([\s\S]*?)</li>', re.I)
_RE_INTRO_M = re.compile(r'detail-intro-txt[^>]*>([\s\S]*?)</p>', re.I)
_RE_INTRO_META = re.compile(
    r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', re.I)

# 播放源标签: <li ... data-target="#ewave-playlist-1">高清云播</li>
_RE_TAB = re.compile(
    r'data-target="#(ewave-playlist-\d+)"[^>]*>([^<]*)</li>', re.I)

# 剧集: <li class="... ewave-playlist-item"><a href="/vodplay/584-1-1.html">第01集</a></li>
_RE_EP = re.compile(
    r'<li[^>]*class="[^"]*ewave-playlist-item[^"]*"[^>]*>\s*'
    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>',
    re.S | re.I)

# 播放页 player_aaaa
_RE_PLAYER = re.compile(r'player_aaaa\s*=\s*(\{[\s\S]*?\})\s*</script>', re.S)

# 分页: <span class="num">1/1696</span>
_RE_PAGENUM = re.compile(r'<span class="num">(\d+)/(\d+)</span>', re.I)
_RE_TOTAL = re.compile(r'\$\(\s*["\']\.ewave-total["\']\s*\)\.text\(\s*(\d+)\s*\)', re.I)


class Spider(Spider):

    def getName(self):
        return "达达兔影视"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}

        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": self.site_url + "/",
            "Upgrade-Insecure-Requests": "1",
        }
        self.default_pic = DEFAULT_PIC
        self._cache = {}
        self.log("init: site=%s" % self.site_url)

    # ---------------- 基础 ----------------
    def _fix_url(self, url):
        if not url:
            return ""
        url = _html.unescape(url.strip())
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
        s = _html.unescape(s).replace("\xa0", " ")
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    def _fetch(self, url, timeout=20, referer=None):
        try:
            h = dict(self.headers)
            if referer:
                h["Referer"] = referer
            rsp = self.fetch(url, headers=h, timeout=timeout)
            if hasattr(rsp, "text"):
                return rsp.text or ""
            if hasattr(rsp, "content"):
                return rsp.content.decode("utf-8", "ignore")
            return str(rsp)
        except Exception as e:
            self.log("fetch FAIL %s -> %s" % (url, e))
            return ""

    def _pic_ok(self, pic):
        pic = (pic or "").strip()
        # 页面偶发出现 data-original="/" 的空图，直接丢弃
        if not pic or pic in ("/", "#"):
            return ""
        return self._fix_url(pic)

    # ---------------- 列表解析 ----------------
    def _extract_videos(self, html, limit=0, fix_pic=False):
        """从首页/分类/搜索页里统一提取视频列表"""
        videos = []
        seen = set()
        if not html:
            return videos

        def _push(vid, name, pic, remark):
            if vid in seen:
                return
            seen.add(vid)
            videos.append({
                "vod_id": vid,
                "vod_name": self._clean(name)[:100],
                "vod_pic": self._pic_ok(pic),
                "vod_remarks": self._clean(remark)[:50],
            })

        # 1) 搜索结果页独立结构
        if 'detail detail-search' in html:
            for bm in _RE_SEARCH_BLOCK.finditer(html):
                block = bm.group(1)
                lm = _RE_S_LINK.search(block)
                if not lm:
                    continue
                href, vid, title = lm.group(1), lm.group(2), lm.group(3)
                pm = _RE_S_PIC.search(block)
                year = area = ""
                dm = _RE_S_DESC.search(block)
                if dm:
                    fm = _RE_S_FIRSTLI.search(dm.group(1))
                    if fm:
                        raw = self._clean(fm.group(1)).replace("\xa0", " ")
                        parts = [p.strip() for p in raw.split("/") if p.strip()]
                        if len(parts) >= 2:
                            year, area = parts[0], parts[1]
                        elif parts:
                            year = parts[0]
                remark = " ".join(x for x in (year, area) if x)
                _push(self._fix_url(href), title,
                      pm.group(1) if pm else "", remark)

        # 2) 卡片式(video-item)：按 href 切段，每段只向前取 500 字符
        starts = list(_RE_CARD_START.finditer(html))
        for i, m in enumerate(starts):
            href, vid, title = m.group(1), m.group(2), m.group(3)
            end = starts[i + 1].start() if i + 1 < len(starts) else len(html)
            block = html[m.end():min(end, m.end() + 500)]
            pm = _RE_PIC_ATTR.search(block)
            dm = _RE_DURATION.search(block)
            _push(self._fix_url(href), title,
                  pm.group(1) if pm else "",
                  dm.group(1) if dm else "")

        # 3) 纯文字列表(text-list)
        for m in _RE_TEXT_ITEM.finditer(html):
            href, vid, name, remark = m.groups()
            _push(self._fix_url(href), name, "", remark or "")

        # 4) 最后兜底: 只有 href + title
        if not videos:
            for m in _RE_HREF_TITLE.finditer(html):
                href, vid, title = m.groups()
                _push(self._fix_url(href), title, "", "")

        if limit and len(videos) > limit:
            videos = videos[:limit]

        # 文字列表只有名称没有封面，按需补图(限制预算，避免拖慢首页)
        if fix_pic:
            budget = 12
            for v in videos:
                if budget <= 0:
                    break
                if not v["vod_pic"] and v["vod_id"].startswith("http"):
                    budget -= 1
                    v["vod_pic"] = self._detail_pic(v["vod_id"])

        # 补图失败时统一兜底(留空比塞默认图更干净，TVBox 会自行处理)
        if self.default_pic:
            for v in videos:
                if not v["vod_pic"]:
                    v["vod_pic"] = self.default_pic
        return videos

    def _detail_pic(self, detail_url):
        """文字列表没有封面时，取详情页 detail-img 的封面(实测详情页首图即海报)"""
        try:
            html = self._fetch(detail_url, timeout=12)
            if not html:
                return ""
            m = _RE_COVER.search(html) or _RE_COVER2.search(html)
            if m:
                return self._pic_ok(m.group(1))
        except Exception:
            pass
        return ""

    def _page_count(self, html):
        if not html:
            return 1
        m = _RE_PAGENUM.search(html)
        if m:
            try:
                return max(1, int(m.group(2)))
            except Exception:
                pass
        return 1

    def _total(self, html):
        m = _RE_TOTAL.search(html or "")
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        return 0

    # ---------------- 首页 ----------------
    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        html = self._fetch(self.site_url + "/")
        self.log("home HTML 长度: %d" % len(html))
        videos = self._extract_videos(html, fix_pic=True)
        self.log("home 解析: %d 条" % len(videos))
        return {"list": videos}

    # ---------------- 分类 ----------------
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if page < 1:
            page = 1

        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}

        def _val(k):
            v = extend.get(k)
            if v in (None, "", "全部"):
                return ""
            return str(v)

        area = _val("area")
        sort = _val("sort_field") or "time"
        cls = _val("class")
        year = _val("year")

        # 实测 vodshow 模板(连字符数量已逐一验证):
        #   基础+分页      /vodshow/1--time------2---.html
        #   基础(无分页)   /vodshow/1--time---------.html
        #   地区           /vodshow/1-美国-hits---------.html
        #   分类           /vodshow/1--hits-喜剧--------.html
        #   年份           /vodshow/1--hits---------2026.html
        # 实测 vodshow 模板(每条都 curl 验证过):
        #   电影第2页       /vodshow/1--time------2---.html        ← 6 个 '-'
        #   美国+人气第2页  /vodshow/1-美国-hits------2---.html     ← 6 个 '-'
        #   喜剧筛选第1页   /vodshow/1--score-喜剧-----1---.html    ← 5 个 '-'
        #   喜剧筛选第2页   /vodshow/1--score-喜剧-----2---.html    ← 5 个 '-'
        #   2026年第1页     /vodshow/1--hits---------2026.html
        # 即: 有 class 时 year 段已被 class 占用，分页位少一个 '-'；无 class 时 year 可放在分页位之前
        # 实测(每个分支都用 curl 逐一试过连字符个数):
        #   无筛选  /vodshow/1--time------1---.html          sort 与 page 之间 6 个 '-'
        #   地区    /vodshow/1-美国-hits------2---.html       同样是 6 个 '-'
        #   分类    /vodshow/1--score-喜剧-----1---.html      class 与 page 之间 5 个 '-'
        #   年份    /vodshow/1--time------2026-1---.html      year 占页位前一位
        q = lambda x: urllib.parse.quote(x, safe="")  # noqa: E731
        tpl = self.site_url + "/vodshow/" + q(str(tid)) + "-" + q(area) + "-" + q(sort)
        if cls:
            url = tpl + "-" + q(cls) + "-----" + str(page) + "---.html"
        elif year:
            # 站点地图里的年份链接是 /vodshow/1--hits---------2026.html
            url = tpl + "---------" + q(year) + ".html" if page == 1 else \
                tpl + "------" + q(year) + "-" + str(page) + "---.html"
        else:
            url = tpl + "------" + str(page) + "---.html"

        self.log("category: %s" % url)
        html = self._fetch(url)
        self.log("  HTML 长度: %d" % len(html))

        videos = self._extract_videos(html)
        pagecount = self._page_count(html)
        total = self._total(html) or pagecount * 24
        self.log("  解析: %d 条, 共 %d 页 / %d 部" % (len(videos), pagecount, total))

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": total,
        }

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        if page < 1:
            page = 1
        kw = urllib.parse.quote(str(key).strip(), safe="")
        url = "%s/vodsearch/%s----------%d---.html" % (self.site_url, kw, page)
        self.log("search: %s" % url)

        html = self._fetch(url)
        self.log("  HTML 长度: %d" % len(html))
        videos = self._extract_videos(html)
        total = self._total(html)
        pagecount = self._page_count(html)
        self.log("  解析: %d 条, %d 页" % (len(videos), pagecount))

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 10,
            "total": total or len(videos),
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        self.log("detail: %s" % url)

        html = self._fetch(url)
        self.log("  HTML 长度: %d" % len(html))
        if not html:
            return {"list": []}

        # 标题
        name = ""
        m = _RE_H1.search(html)
        if m:
            name = self._clean(m.group(1))
        if not name:
            m = re.search(r"<title>(.*?)</title>", html, re.S)
            if m:
                name = self._clean(m.group(1)).split("_")[0].split("-")[0]
        name = re.sub(r"\s*\(\d{4}\)\s*$", "", name).strip() or vod_id

        # 封面
        pic = ""
        m = _RE_COVER.search(html) or _RE_COVER2.search(html)
        if m:
            pic = self._pic_ok(m.group(1))
        if not pic:
            pic = self.default_pic

        # 简介(多层兜底)
        content = ""
        m = _RE_INTRO.search(html)
        if m:
            content = self._clean(m.group(1))
        if not content:
            m = _RE_INTRO_M.search(html)
            if m:
                content = self._clean(m.group(1))
        if not content:
            m = _RE_INTRO_META.search(html)
            if m:
                content = self._clean(m.group(1))

        content = INTRO_PREFIX + ("\n" + content if content else "")

        # 元信息
        def _g(rx, default=""):
            mm = rx.search(html)
            return self._clean(mm.group(1)) if mm else default

        def _g_names(rx, default=""):
            mm = rx.search(html)
            if not mm:
                return default
            block = mm.group(1)
            names = re.findall(r'<a[^>]*>([^<]*)</a>', block)
            if names:
                return ", ".join(self._clean(n) for n in names if self._clean(n))
            return self._clean(block).replace(" ", "")

        actor = _g_names(_RE_ACTOR)
        director = _g_names(_RE_DIRECTOR)
        vod_type = _g_names(_RE_TYPE)
        area = _g(_RE_AREA)
        year = _g(_RE_YEAR)
        lang = _g(_RE_LANG)
        state = _g(_RE_STATE)
        update = _g(_RE_UPDATE)
        score = _g(_RE_DOUBAN)
        hits = _g(_RE_HITS)

        actor = re.sub(r"\s*,\s*", ", ", actor)
        remarks = state or update or ("%s %s" % (year, area)).strip()

        # ===== 剧集: 每条播放源一个 #ewave-playlist-N =====
        tabs = _RE_TAB.findall(html)
        tab_map = {}
        for idx, (pid, tname) in enumerate(tabs, 1):
            tab_map["ewave-playlist-%d" % idx] = self._clean(tname) or ("线路%d" % idx)

        # 按 <div id="ewave-playlist-N"> 分段收集剧集
        groups = {}   # sid -> [(name, url)]
        order = []
        for m in re.finditer(
                r'id="(ewave-playlist-\d+)"([\s\S]*?)(?=id="ewave-playlist-\d+"|</section>|$)',
                html):
            pid, block = m.group(1), m.group(2)
            eps = []
            for em in _RE_EP.finditer(block):
                href, epname = em.group(1), em.group(2)
                if not href:
                    continue
                eps.append((self._clean(epname) or ("第%d集" % (len(eps) + 1)),
                            self._fix_url(href)))
            if eps:
                order.append(pid)
                groups[pid] = eps

        # 兜底: 页面没有 playlist 容器，直接全量抓 vodplay 链接
        if not groups:
            eps = []
            for em in re.finditer(r'href="(/vodplay/(\d+)-(\d+)-(\d+)\.html)"[^>]*>([^<]*)</a>',
                                  html):
                href, vid, sid, nid, epname = em.groups()
                key = "ewave-playlist-%s" % sid
                groups.setdefault(key, [])
                if key not in order:
                    order.append(key)
                groups[key].append((
                    self._clean(epname) or ("第%s集" % nid),
                    self._fix_url(href)))

        self.log("  播放源: %s" % {k: len(v) for k, v in groups.items()})

        if not groups:
            return {"list": []}

        play_from = []
        play_url = []
        for pid in order:
            eps = groups.get(pid) or []
            if not eps:
                continue
            play_from.append(tab_map.get(pid, pid))
            play_url.append("#".join("%s$%s" % (n, h) for n, h in eps))

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_type": vod_type,
            "vod_area": area,
            "vod_year": year,
            "vod_lang": lang,
            "vod_score": score,
            "vod_remarks": remarks,
            "vod_hits": hits,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    # ---------------- 播放 ----------------
    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        self.log("player: %s" % play_page)

        now = int(time.time())
        if play_page in self._cache:
            ts, res = self._cache[play_page]
            if now - ts < 600:
                return res

        html = self._fetch(play_page, referer=self.site_url + "/")
        info = {}
        m = _RE_PLAYER.search(html or "")
        if m:
            try:
                info = json.loads(m.group(1))
            except Exception as e:
                self.log("  player_aaaa 解析失败: %s" % e)

        url = (info.get("url") or "").replace("\\/", "/")
        encrypt = info.get("encrypt", 0)

        # player_aaaa 里的 url 是含中文(如 /第01集/)的字面量，必须转成百分号编码，
        # 否则播放器直接请求会抛 UnicodeEncodeError
        if url and re.search(r'[^\x00-\x7f]', url):
            sp = urllib.parse.urlsplit(url)
            url = urllib.parse.urlunsplit((
                sp.scheme, sp.netloc,
                urllib.parse.quote(sp.path, safe="/%"),
                urllib.parse.quote(sp.query, safe="=&%?"),
                sp.fragment))

        # 站点正常为 encrypt=0 + 可直连 m3u8；如遇到 encrypt=1 则交给 TVBox 解析
        if url and encrypt in (0, "0", None):
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = self.site_url + url
            res = {
                "parse": 0,
                "playUrl": "",
                "url": url,
                "header": {
                    "User-Agent": UA,
                    "Referer": self.site_url + "/",
                },
            }
            self._cache[play_page] = (now, res)
            self.log("  => 直链: %s" % url[:180])
            return res

        if url:
            # 需要平台解析
            res = {
                "parse": 1,
                "playUrl": "",
                "url": url,
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }
            self._cache[play_page] = (now, res)
            self.log("  => 需解析(encrypt=%s): %s" % (encrypt, url[:180]))
            return res

        # 兜底: 交给 TVBox 嗅探播放页
        res = {"parse": 1, "playUrl": "", "url": play_page,
               "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}
        self._cache[play_page] = (now, res)
        return res

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
