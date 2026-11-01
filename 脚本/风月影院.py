# coding=utf-8
"""
风月影院 www.cqjwny.com | TVBox Python 爬虫
网站结构解析：
  - 列表页：/vodshow/{tid}-----------.html
  - 详情页：/voddetail/{id}.html
  - 播放页：/vodplay/{id}-{sid}-{nid}.html
  - 播放地址：页面内 var player_aaaa={...} 的 url 字段（m3u8 直链）
  - 电影(tid=1)    : 地区无"内地/新加坡"，语言含"法语/德语"
  - 电视剧(tid=2)  : 地区含"内地/新加坡"，语言无法语/德语
  - 综艺(tid=3)    : 同电视剧
  - 动漫(tid=4)    : 同电视剧
  - 短剧(tid=20)   : 同电视剧
筛选 URL 12 段结构（'-' 分隔）：
  {tid}-{area}-{order}-{class}-{lang}-{letter}--{}-{page}--{}-{}-{year}
  *注意：按类型筛选本质是替换 URL 第一段的 {tid}
"""
import re
import sys
import json
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
                print("[cqjwny]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.cqjwny.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

CLASSES = [
    {"type_id": "1",  "type_name": "电影"},
    {"type_id": "2",  "type_name": "电视剧"},
    {"type_id": "3",  "type_name": "综艺"},
    {"type_id": "4",  "type_name": "动漫"},
    {"type_id": "20", "type_name": "短剧"},
]

# ==================== 严格按源码逐分类定义 ====================

_SORT_OPTS = [
    {"n": "按时间", "v": "time"},
    {"n": "按人气", "v": "hits"},
    {"n": "按评分", "v": "score"},
]

_YEAR_OPTS = [{"n": "全部", "v": ""}] + \
    [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]

_LETTER_OPTS = [{"n": "全部", "v": ""}] + \
    [{"n": c, "v": c} for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] + \
    [{"n": "0-9", "v": "0-9"}]

# 按类型选项（对应真实 tid）
_MOVIE_TYPE = [
    {"n": "全部", "v": "1"},
    {"n": "动作电影", "v": "6"},
    {"n": "喜剧电影", "v": "7"},
    {"n": "爱情电影", "v": "8"},
    {"n": "科幻电影", "v": "9"},
    {"n": "恐怖电影", "v": "10"},
    {"n": "剧情电影", "v": "11"},
    {"n": "战争电影", "v": "12"},
    {"n": "纪录电影", "v": "21"},
    {"n": "动漫电影", "v": "26"},
]

_TV_TYPE = [
    {"n": "全部", "v": "2"},
    {"n": "国产剧", "v": "13"},
    {"n": "香港剧", "v": "14"},
    {"n": "台湾剧", "v": "15"},
    {"n": "日本剧", "v": "16"},
    {"n": "韩国剧", "v": "22"},
    {"n": "泰国剧", "v": "23"},
    {"n": "欧美剧", "v": "24"},
    {"n": "海外剧", "v": "25"},
]

_VARIETY_TYPE = [
    {"n": "全部", "v": "3"},
    {"n": "大陆综艺", "v": "27"},
    {"n": "日韩综艺", "v": "28"},
    {"n": "港台综艺", "v": "29"},
    {"n": "欧美综艺", "v": "30"},
]

_ANIME_TYPE = [
    {"n": "全部", "v": "4"},
    {"n": "国产动漫", "v": "31"},
    {"n": "日韩动漫", "v": "32"},
    {"n": "港台动漫", "v": "33"},
    {"n": "欧美动漫", "v": "34"},
    {"n": "海外动漫", "v": "35"},
]

_SHORT_TYPE = [
    {"n": "全部", "v": "20"},
]

# 电影页（源码 /vodshow/7-大陆----------2026.html 筛选区）
_MOVIE_AREA = [
    {"n": "全部", "v": ""},
    {"n": "大陆", "v": "大陆"},
    {"n": "香港", "v": "香港"},
    {"n": "台湾", "v": "台湾"},
    {"n": "美国", "v": "美国"},
    {"n": "法国", "v": "法国"},
    {"n": "英国", "v": "英国"},
    {"n": "日本", "v": "日本"},
    {"n": "韩国", "v": "韩国"},
    {"n": "德国", "v": "德国"},
    {"n": "泰国", "v": "泰国"},
    {"n": "印度", "v": "印度"},
    {"n": "意大利", "v": "意大利"},
    {"n": "西班牙", "v": "西班牙"},
    {"n": "加拿大", "v": "加拿大"},
    {"n": "其他", "v": "其他"},
]

_MOVIE_LANG = [
    {"n": "全部", "v": ""},
    {"n": "国语", "v": "国语"},
    {"n": "英语", "v": "英语"},
    {"n": "粤语", "v": "粤语"},
    {"n": "闽南语", "v": "闽南语"},
    {"n": "韩语", "v": "韩语"},
    {"n": "日语", "v": "日语"},
    {"n": "法语", "v": "法语"},
    {"n": "德语", "v": "德语"},
    {"n": "其它", "v": "其它"},
]

_MOVIE_CLASS = [
    "喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争", "警匪",
    "犯罪", "动画", "奇幻", "武侠", "冒险", "枪战", "悬疑", "惊悚",
    "经典", "青春", "文艺", "微电影", "古装", "历史", "运动",
    "农村", "儿童", "网络电影",
]

# 电视剧/综艺/动漫/短剧（源码 13/27/31/20 页面筛选区）
_TV_AREA = [
    {"n": "全部", "v": ""},
    {"n": "大陆", "v": "大陆"},
    {"n": "内地", "v": "内地"},
    {"n": "韩国", "v": "韩国"},
    {"n": "香港", "v": "香港"},
    {"n": "台湾", "v": "台湾"},
    {"n": "日本", "v": "日本"},
    {"n": "美国", "v": "美国"},
    {"n": "泰国", "v": "泰国"},
    {"n": "英国", "v": "英国"},
    {"n": "新加坡", "v": "新加坡"},
    {"n": "其他", "v": "其他"},
]

_TV_LANG = [
    {"n": "全部", "v": ""},
    {"n": "国语", "v": "国语"},
    {"n": "英语", "v": "英语"},
    {"n": "粤语", "v": "粤语"},
    {"n": "闽南语", "v": "闽南语"},
    {"n": "韩语", "v": "韩语"},
    {"n": "日语", "v": "日语"},
    {"n": "其它", "v": "其它"},
]

_TV_CLASS = [
    "古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作",
    "奇幻", "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他",
]

_VARIETY_CLASS = [
    "选秀", "情感", "访谈", "播报", "旅游", "音乐", "美食", "纪实",
    "曲艺", "生活", "游戏互动", "财经", "求职",
]

_ANIME_CLASS = [
    "情感", "科幻", "热血", "推理", "搞笑", "冒险", "萝莉", "校园",
    "动作", "机战", "运动", "战争", "少年", "少女", "社会", "原创",
    "亲子", "益智", "励志", "其他",
]

FILTERS = {
    "1": [
        {"key": "type",  "name": "类型", "value": _MOVIE_TYPE},
        {"key": "class", "name": "剧情",
         "value": [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in _MOVIE_CLASS]},
        {"key": "area",  "name": "地区", "value": _MOVIE_AREA},
        {"key": "year",  "name": "年份", "value": _YEAR_OPTS},
        {"key": "lang",  "name": "语言", "value": _MOVIE_LANG},
        {"key": "letter","name": "字母", "value": _LETTER_OPTS},
        {"key": "order", "name": "排序", "value": _SORT_OPTS},
    ],
    "2": [
        {"key": "type",  "name": "类型", "value": _TV_TYPE},
        {"key": "class", "name": "剧情",
         "value": [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in _TV_CLASS]},
        {"key": "area",  "name": "地区", "value": _TV_AREA},
        {"key": "year",  "name": "年份", "value": _YEAR_OPTS},
        {"key": "lang",  "name": "语言", "value": _TV_LANG},
        {"key": "letter","name": "字母", "value": _LETTER_OPTS},
        {"key": "order", "name": "排序", "value": _SORT_OPTS},
    ],
    "3": [
        {"key": "type",  "name": "类型", "value": _VARIETY_TYPE},
        {"key": "class", "name": "剧情",
         "value": [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in _VARIETY_CLASS]},
        {"key": "area",  "name": "地区", "value": _TV_AREA},
        {"key": "year",  "name": "年份", "value": _YEAR_OPTS},
        {"key": "lang",  "name": "语言", "value": _TV_LANG},
        {"key": "letter","name": "字母", "value": _LETTER_OPTS},
        {"key": "order", "name": "排序", "value": _SORT_OPTS},
    ],
    "4": [
        {"key": "type",  "name": "类型", "value": _ANIME_TYPE},
        {"key": "class", "name": "剧情",
         "value": [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in _ANIME_CLASS]},
        {"key": "area",  "name": "地区", "value": _TV_AREA},
        {"key": "year",  "name": "年份", "value": _YEAR_OPTS},
        {"key": "lang",  "name": "语言", "value": _TV_LANG},
        {"key": "letter","name": "字母", "value": _LETTER_OPTS},
        {"key": "order", "name": "排序", "value": _SORT_OPTS},
    ],
    "20": [
        {"key": "type",  "name": "类型", "value": _SHORT_TYPE},
        {"key": "class", "name": "剧情",
         "value": [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in _TV_CLASS]},
        {"key": "area",  "name": "地区", "value": _TV_AREA},
        {"key": "year",  "name": "年份", "value": _YEAR_OPTS},
        {"key": "lang",  "name": "语言", "value": _TV_LANG},
        {"key": "letter","name": "字母", "value": _LETTER_OPTS},
        {"key": "order", "name": "排序", "value": _SORT_OPTS},
    ],
}


class Spider(Spider):

    def getName(self):
        return "风月影院"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}

        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.site_url + "/",
        }
        self.log("init site=%s" % self.site_url)

    def log(self, *a, **kw):
        try:
            print("[cqjwny]", *a)
        except Exception:
            pass

    def _fetch(self, url, timeout=15):
        try:
            r = self.fetch(url, headers=self.headers, timeout=timeout)
            if hasattr(r, "text"):
                text = r.text or ""
            elif hasattr(r, "content"):
                text = r.content.decode("utf-8", "ignore")
            else:
                text = str(r)
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
        s = re.sub(r"<[^>]+>", "", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    # ---------------- 列表解析 ----------------
    def _parse_video_list(self, html):
        videos = []
        seen = set()
        if not html:
            return videos

        patterns = [
            re.compile(
                r'<a class="stui-vodlist__thumb lazyload" href="(/voddetail/\d+\.html)" '
                r'title="([^"]*)" data-original="([^"]*)"[\s\S]*?</a>', re.S),
            re.compile(
                r'<a class="v-thumb stui-vodlist__thumb lazyload" href="(/voddetail/\d+\.html)" '
                r'title="([^"]*)" data-original="([^"]*)"[\s\S]*?</a>', re.S),
            re.compile(
                r'<a href="(/voddetail/\d+\.html)" class="stui-vodlist__thumb active" '
                r'title="([^"]*)" style="background: url\(([^)]+)\)[\s\S]*?</a>', re.S),
        ]

        for pat in patterns:
            for m in pat.finditer(html):
                href, title, pic = m.group(1), self._clean(m.group(2)), m.group(3)
                if href in seen:
                    continue
                seen.add(href)

                block = m.group(0)
                rem = re.search(r'<span class="pic-text text-right">([^<]*)</span>', block)
                remarks = self._clean(rem.group(1)) if rem else ""
                pic = (pic or "").split("#")[0]

                videos.append({
                    "vod_id": self._fix_url(href),
                    "vod_name": title or href,
                    "vod_pic": self._fix_url(pic),
                    "vod_remarks": remarks,
                })

        for m in re.finditer(
                r'<a class="top-line-dot text-overflow" href="(/voddetail/\d+\.html)" '
                r'title="([^"]*)"><span class="text-muted pull-right">([^<]*)</span>([^<]*)</a>',
                html):
            href, title, remarks, _ = m.groups()
            if href in seen:
                continue
            seen.add(href)
            videos.append({
                "vod_id": self._fix_url(href),
                "vod_name": self._clean(title),
                "vod_pic": "",
                "vod_remarks": self._clean(remarks),
            })

        return videos

    def _page_count(self, html, current=1):
        if not html:
            return current
        m = re.search(r'<span class="num">\d+/(\d+)</span>', html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass

        nums = []
        for p in re.findall(r'-------(\d+)---', html):
            try:
                nums.append(int(p))
            except Exception:
                pass
        return max(nums + [current]) if nums else current

    # ---------------- 首页 ----------------
    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        html = self._fetch(self.site_url + "/")
        videos = self._parse_video_list(html)
        return {"list": videos[:60]}

    # ---------------- 分类 / 筛选 ----------------
    def _build_category_url(self, tid, page, extend):
        """
        严格按站点真实 12 段分页结构：
        {tid}-{area}-{order}-{class}-{lang}-{letter}--{}-{page}--{}-{}-{year}
        """
        area = (extend.get("area") or "").strip()
        order = (extend.get("order") or "").strip()
        cls = (extend.get("class") or "").strip()
        lang = (extend.get("lang") or "").strip()
        letter = (extend.get("letter") or "").strip()
        year = (extend.get("year") or "").strip()

        page_str = "" if page <= 1 else str(page)

        parts = [str(tid), area, order, cls, lang, letter,
                 "", "", page_str, "", "", year]
        path = "-".join(parts)
        encoded = urllib.parse.quote(path, safe="-")
        return "%s/vodshow/%s.html" % (self.site_url, encoded)

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1

        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not extend:
            extend = {}

        # 核心逻辑：如果传入了 type 值，则用 type 的 v 替换原有的 tid
        req_tid = tid
        if extend.get("type"):
            req_tid = extend["type"]

        extend = {k: v for k, v in extend.items()
                  if v not in ("", None, "全部")}

        url = self._build_category_url(req_tid, page, extend)
        self.log("category: %s" % url)
        html = self._fetch(url)
        videos = self._parse_video_list(html)

        pagecount = self._page_count(html, page)
        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": pagecount * 24,
        }

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        keyword = urllib.parse.quote(key)

        urls = [
            "%s/vodsearch/%s-------------.html" % (self.site_url, keyword),
            "%s/vodsearch/-------------.html?wd=%s" % (self.site_url, keyword),
        ]

        html = ""
        videos = []
        for url in urls:
            self.log("search: %s" % url)
            html = self._fetch(url)
            videos = self._parse_video_list(html)
            if videos:
                break

        return {
            "list": videos,
            "page": page,
            "pagecount": self._page_count(html, page),
            "limit": 24,
            "total": len(videos),
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        if not ids:
            return {"list": []}

        vod_id = ids[0]
        url = vod_id if str(vod_id).startswith("http") else self._fix_url(vod_id)
        self.log("detail: %s" % url)

        html = self._fetch(url)
        if not html:
            return {"list": []}

        # 标题
        name = ""
        m = re.search(r'<h1 class="title">([\s\S]*?)</h1>', html)
        if m:
            name = self._clean(re.sub(
                r'<span class="score[^"]*">[\s\S]*?</span>', '', m.group(1)))
        if not name:
            m = re.search(r'<title>《?([^》<_-]+)', html)
            if m:
                name = self._clean(m.group(1))

        # 封面
        pic = ""
        m = re.search(
            r'<a class="stui-vodlist__thumb picture v-thumb"[\s\S]*?'
            r'<img[^>]*data-original="([^"]*)"', html)
        if m:
            pic = self._fix_url(m.group(1).split("#")[0])

        # 评分
        score = ""
        m = re.search(r'<span class="score text-red">([\d.]+)</span>', html)
        if m:
            score = m.group(1)

        # 备注
        remarks = ""
        m = re.search(r'<span class="pic-text text-right">([^<]*)</span>', html)
        if m:
            remarks = self._clean(m.group(1))

        # 简介（首选 #desc 的 <p class="col-pd">）
        content = ""
        m = re.search(
            r'<div class="stui-pannel stui-pannel-bg clearfix" id="desc">'
            r'[\s\S]*?<p class="col-pd">([\s\S]*?)</p>', html)
        if not m:
            m = re.search(
                r'<p class="desc hidden-xs">[\s\S]*?'
                r'<span class="left text-muted">简介：</span>([\s\S]*?)<a href="#desc">', html)
        if not m:
            m = re.search(r'<meta name="description" content="([^"]*)"', html)
        if m:
            content = self._clean(m.group(1))
        content = INTRO_PREFIX + ("\n" + content if content else "")

        # 地区 / 年份
        area = ""
        m = re.search(r'地区：</span>([\s\S]*?)&nbsp;', html)
        if m:
            area = self._clean(m.group(1))

        year = ""
        m = re.search(r'年份：</span>([\s\S]*?)&nbsp;', html)
        if m:
            year = self._clean(m.group(1))

        # 主演 / 导演 (优化：提取 <a> 标签中的文字并用逗号连接，避免粘连)
        actor = ""
        m = re.search(r'<span class="text-muted">主演：</span>([\s\S]*?)</p>', html)
        if m:
            actors = re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1))
            actor = ",".join(self._clean(a) for a in actors) if actors else self._clean(m.group(1))

        director = ""
        m = re.search(r'<span class="text-muted">导演：</span>([\s\S]*?)</p>', html)
        if m:
            directors = re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1))
            director = ",".join(self._clean(d) for d in directors) if directors else self._clean(m.group(1))

        # 剧集线路
        play_from = []
        play_url = []

        playlist_pat = re.compile(
            r'<div class="stui-pannel-box b playlist mb">[\s\S]*?'
            r'<h3 class="title">([\s\S]*?)</h3>[\s\S]*?'
            r'<ul class="stui-content__playlist clearfix">([\s\S]*?)</ul>',
            re.S)

        groups = []
        for m in playlist_pat.finditer(html):
            line_name = self._clean(m.group(1)) or ("线路%d" % (len(groups) + 1))
            groups.append((line_name, m.group(2)))

        if not groups:
            for ul in re.findall(
                    r'<ul class="stui-content__playlist clearfix">([\s\S]*?)</ul>',
                    html, re.S):
                groups.append(("线路%d" % (len(groups) + 1), ul))

        for line_name, ul in groups:
            eps = []
            for em in re.finditer(r'<a href="([^"]+)">([^<]+)</a>', ul):
                href = self._fix_url(em.group(1).replace("&amp;", "&"))
                ep_name = self._clean(em.group(2))
                eps.append("%s$%s" % (ep_name, href))
            if eps:
                play_from.append(line_name)
                play_url.append("#".join(eps))

        if not play_from:
            return {"list": []}

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name or vod_id,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_area": area,
            "vod_year": year,
            "vod_score": score,
            "vod_remarks": remarks,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    # ---------------- 播放 ----------------
    def playerContent(self, flag, id, vipFlags):
        play_page = id if str(id).startswith("http") else self._fix_url(id)
        self.log("player: %s" % play_page)

        html = self._fetch(play_page)
        if not html:
            return {
                "parse": 1,
                "playUrl": "",
                "url": play_page,
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }

        m = re.search(r'var player_aaaa=(\{[\s\S]*?\})\s*</script>', html)
        if not m:
            m = re.search(r'var player_aaaa=(\{[\s\S]*?\});', html)

        if m:
            raw = m.group(1)
            url = ""
            try:
                data = json.loads(raw)
                url = data.get("url", "")
            except Exception:
                um = re.search(r'"url"\s*:\s*"([^"]+)"', raw)
                url = um.group(1) if um else ""

            if url:
                url = (url.replace("\\/", "/")
                          .replace("\\u0026", "&")
                          .replace("&amp;", "&"))
                if url.startswith("//"):
                    url = "https:" + url

                self.log("play url: %s" % url[:200])
                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": url,
                    "header": {
                        "User-Agent": UA,
                        "Referer": play_page,
                    },
                }

        return {
            "parse": 1,
            "playUrl": "",
            "url": play_page,
            "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
        }

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url or url.startswith("http")

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
