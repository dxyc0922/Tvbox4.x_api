# coding=utf-8
"""
麻花影视 ynjcsj.com | TVBox Python 爬虫 
关键:
  - 完美对应网页侧边栏/顶部筛选频道（含「频道」二级子分类）
  - 完整筛选维度: 频道/类型/地区/年份/语言/资源/版本/字母/排序
  - vodshow 参数槽位按实测抓包对齐: tid-area-by-class-lang-letter-?-?-page-资源-?-year
  - 版本走 /version/xxx.html 路径后缀（站点特殊设计）
  - 大类走搜索流兜底，子类走原生静态 HTML
  - 全链路防爬拦截处理
  - player_aaaa.url 直链提取
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
                adapter = _rq.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=0)
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
                print("[mahua]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.ynjcsj.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/upload/site/20251221-1/ac2bc08f7f6c858edf82dbb792f7734b.png"

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

# 完美对应网页左侧/顶部导航栏的频道
CLASSES = [
    {"type_id": "1",  "type_name": "电影"},
    {"type_id": "2",  "type_name": "电视剧"},
    {"type_id": "3",  "type_name": "综艺"},
    {"type_id": "4",  "type_name": "动漫"},
    {"type_id": "35", "type_name": "动画片"},
    {"type_id": "36", "type_name": "短剧"},
]

# 「频道」二级子分类（从首页导航栏实测抓取的真实 type_id）
_CHANNELS_MAP = {
    "1":  [("6", "动作片"), ("7", "喜剧片"), ("8", "爱情片"), ("9", "科幻片"), ("10", "恐怖片"),
           ("11", "剧情片"), ("12", "战争片"), ("24", "纪录片"), ("44", "香港电影"), ("45", "动漫电影")],
    "2":  [("13", "国产剧"), ("14", "香港剧"), ("15", "台湾剧"), ("16", "日本剧"), ("20", "泰国剧"),
           ("21", "韩国剧"), ("22", "欧美剧"), ("23", "海外剧")],
    "3":  [("25", "大陆综艺"), ("26", "港台综艺"), ("27", "日韩综艺"), ("28", "欧美综艺")],
    "4":  [("29", "国产动漫"), ("30", "日韩动漫"), ("31", "港台动漫"), ("32", "欧美动漫"),
           ("33", "有声动漫"), ("34", "海外动漫")],
    "35": [],
    "36": [("37", "女频恋爱"), ("38", "反转爽剧"), ("39", "年代穿越"), ("40", "脑洞悬疑"),
           ("41", "现代都市"), ("42", "古装仙侠"), ("43", "热血剧情")],
}

_SORTS = [{"n": "时间", "v": "time"}, {"n": "人气", "v": "hits"}, {"n": "评分", "v": "score"}]
_YEARS = [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]
_LANGS = [{"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"}, {"n": "粤语", "v": "粤语"},
          {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"}, {"n": "其它", "v": "其它"}]
_RESOURCES = [{"n": "全部", "v": ""}, {"n": "正片", "v": "正片"}, {"n": "预告片", "v": "预告片"}, {"n": "花絮", "v": "花絮"}]
_VERSIONS = [{"n": "全部", "v": ""}, {"n": "高清版", "v": "高清版"}, {"n": "剧场版", "v": "剧场版"}, {"n": "抢先版", "v": "抢先版"},
             {"n": "OVA", "v": "OVA"}, {"n": "TV", "v": "TV"}, {"n": "影院版", "v": "影院版"}]
_LETTERS = [{"n": "全部", "v": ""}] + [{"n": chr(c), "v": chr(c)} for c in range(ord("A"), ord("Z") + 1)]
_AREAS_TV = [{"n": "全部", "v": ""}, {"n": "内地", "v": "内地"}, {"n": "韩国", "v": "韩国"}, {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"}, {"n": "日本", "v": "日本"}, {"n": "美国", "v": "美国"}, {"n": "泰国", "v": "泰国"}, {"n": "英国", "v": "英国"}, {"n": "新加坡", "v": "新加坡"}, {"n": "其他", "v": "其他"}]
_AREAS_MOVIE = [{"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "法国", "v": "法国"}, {"n": "英国", "v": "英国"}, {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"}, {"n": "德国", "v": "德国"}, {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"}, {"n": "意大利", "v": "意大利"}, {"n": "西班牙", "v": "西班牙"}, {"n": "加拿大", "v": "加拿大"}, {"n": "其他", "v": "其他"}]

_FILTERS_MAP = {
    "1":  ["全部", "喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争", "警匪", "犯罪", "动画", "奇幻", "武侠", "冒险", "枪战", "悬疑", "惊悚", "经典", "青春", "文艺", "微电影", "古装", "历史", "运动", "农村", "儿童", "网络电影"],
    "2":  ["全部", "古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作", "奇幻", "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他"],
    "3":  ["全部", "选秀", "情感", "访谈", "播报", "旅游", "音乐", "美食", "纪实", "曲艺", "生活", "游戏互动", "财经", "求职"],
    "4":  ["全部", "情感", "科幻", "热血", "推理", "搞笑", "冒险", "萝莉", "校园", "动作", "机战", "运动", "战争", "少年", "少女", "社会", "原创", "亲子", "益智", "励志", "其他"],
    "35": ["全部", "动画", "奇幻", "冒险", "亲子", "益智", "励志", "其他"],
    "36": ["全部", "古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作", "奇幻", "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他"],
}

FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    areas = _AREAS_MOVIE if tid == "1" else _AREAS_TV
    _filter_list = [
        {"key": "class",    "name": "类型", "value": [{"n": x, "v": "" if x == "全部" else x} for x in _FILTERS_MAP.get(tid, ["全部"])]},
        {"key": "area",     "name": "地区", "value": areas},
        {"key": "year",     "name": "年份", "value": _YEARS},
        {"key": "lang",     "name": "语言", "value": _LANGS},
        {"key": "resource", "name": "资源", "value": _RESOURCES},
        {"key": "version",  "name": "版本", "value": _VERSIONS},
        {"key": "letter",   "name": "字母", "value": _LETTERS},
        {"key": "sort",     "name": "排序", "value": _SORTS},
    ]
    # 有二级子分类的大类，在最前面加「频道」筛选
    if _CHANNELS_MAP.get(tid):
        _filter_list.insert(0, {
            "key": "channel", "name": "频道",
            "value": [{"n": name, "v": cid} for cid, name in _CHANNELS_MAP[tid]],
        })
    FILTERS[tid] = _filter_list

# ===================== 正则 =====================
# 静态分类页列表
_RE_CARD = re.compile(
    r'<a class="video-img lazyload"\s+href="(/voddetail/[^"]+)"\s+data-original="([^"]*)"[^>]*>'
    r'[\s\S]{0,400}?'
    r'<span class="video-title[^"]*">([^<]*)</span>'
    r'[\s\S]{0,400}?'
    r'<p class="video-name"><a[^>]*title="([^"]*)"',
    re.S | re.I)

# 搜索页列表
_RE_SEARCH_CARD = re.compile(
    r'<a class="block-fea lazyload"\s+data-original="([^"]*)"\s+href="(/voddetail/[^"]+)"\s+title="([^"]*)"',
    re.S | re.I)

# 详情页解析
_RE_H1 = re.compile(r'<h1 class="detail-info-title[^"]*"><a[^>]*>([\s\S]*?)</a></h1>', re.I)
_RE_DETAIL_PIC = re.compile(r'<article class="post detail-post[^"]*">[\s\S]{0,500}?<div class="block-fea lazyload"\s+data-original="([^"]*)"', re.S | re.I)
_RE_ACTOR = re.compile(r'<span>演员：</span>([\s\S]*?)</p>', re.S | re.I)
_RE_DIRECTOR = re.compile(r'<span>导演：</span>([\s\S]*?)</p>', re.S | re.I)
_RE_STATE = re.compile(r'<span>状态：</span><em[^>]*>([^<]*)</em>', re.I)
_RE_SCORE = re.compile(r'<h4 class="ewave-star-num[^"]*">([\d.]+)</h4>', re.I)
_RE_LANG = re.compile(r'<span>语言：</span><a[^>]*>([^<]*)</a>', re.I)
_RE_TYPE = re.compile(r'<span>类型：</span><a[^>]*>([^<]*)</a>', re.I)
_RE_AREA = re.compile(r'<span>地区：</span><a[^>]*>([^<]*)</a>', re.I)
_RE_YEAR = re.compile(r'<span>年份：</span><a[^>]*>([^<]*)</a>', re.I)
_RE_UPDATE = re.compile(r'<span>更新时间：</span>(?:<a[^>]*>)?([^<&\s]+)', re.I)
_RE_INTRO = re.compile(r'<div class="entry-content clearfix">([\s\S]*?)</div>', re.S | re.I)

# 剧集列表解析
_RE_TAB = re.compile(r'<li class="swiper-slide ewave-tab[^"]*" data-target="#(ewave-playlist-\d+)"><a[^>]*>([^<]*)</a></li>', re.I)
_RE_PLAYLIST = re.compile(r'<ul[^>]*id="(ewave-playlist-\d+)"[^>]*>([\s\S]*?)</ul>', re.S | re.I)
_RE_EP = re.compile(r'<a class="text-overflow"\s+href="(/vodplay/[^"]+)">([^<]*)</a>', re.I)

# 播放器解析
_RE_PLAYER = re.compile(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>', re.S)


class Spider(Spider):

    def getName(self):
        return "麻花影视"

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
        self.log("init: site=%s" % self.site_url)

    def _fetch(self, url, timeout=20, headers=None):
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
        if not url: return ""
        url = url.strip()
        if url.startswith("//"): return "https:" + url
        if url.startswith("http"): return url
        if url.startswith("/"): return self.site_url + url
        return urllib.parse.urljoin(self.site_url + "/", url)

    def _clean(self, s):
        if not s: return ""
        s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    def _extract_videos(self, html):
        videos = []
        seen = set()
        if not html: return videos
        for m in _RE_CARD.finditer(html):
            href, pic, remark, name = m.groups()
            if href in seen: continue
            seen.add(href)
            videos.append({
                "vod_id":      href,
                "vod_name":    self._clean(name)[:100],
                "vod_pic":     self._fix_url(pic) or self.default_pic,
                "vod_remarks": self._clean(remark),
            })
        return videos

    def _extract_search_videos(self, html):
        videos = []
        seen = set()
        if not html: return videos
        for m in _RE_SEARCH_CARD.finditer(html):
            pic, href, name = m.groups()
            if href in seen: continue
            seen.add(href)
            videos.append({
                "vod_id":      href,
                "vod_name":    self._clean(name)[:100],
                "vod_pic":     self._fix_url(pic) or self.default_pic,
                "vod_remarks": "",
            })
        return videos

    def _page_count(self, html):
        if not html: return 1
        m = re.search(r'<span class="hidden-sm hidden-md hidden-lg">/(\d+)</span>', html)
        if m:
            try: return int(m.group(1))
            except Exception: pass
        # vodshow 筛选页分页兜底: title="第230页"
        m = re.search(r'title="第(\d+)页"', html)
        if m:
            try: return int(m.group(1))
            except Exception: pass
        return 1

    def _build_show_url(self, tid, area, cls, lang, letter, resource, version, sort, year, page):
        # 站点 vodshow 参数槽位(实测抓包对齐):
        # /vodshow/{tid}-{area}-{by}-{class}-{lang}-{letter}--{page}-{资源}--{year}.html
        # 版本特殊: 以 /version/{版本}.html 路径后缀追加
        fields = [
            urllib.parse.quote(area or ""),
            urllib.parse.quote(sort or "time"),
            urllib.parse.quote(cls or ""),
            urllib.parse.quote(lang or ""),
            urllib.parse.quote(letter or ""),
            "", "",                       # 两个保留槽位
            str(page),
            urllib.parse.quote(resource or ""),
            "",                           # 保留槽位
            urllib.parse.quote(year or ""),
        ]
        url = "%s/vodshow/%s.html" % (self.site_url, "-".join([tid] + fields))
        if version:
            url += "/version/%s.html" % urllib.parse.quote(version)
        return url

    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        html = self._fetch(self.site_url + "/")
        return {"list": self._extract_videos(html)}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if isinstance(extend, str):
            try: extend = json.loads(extend)
            except Exception: extend = {}
        if not extend: extend = {}

        area     = extend.get("area") or ""
        cls      = extend.get("class") or ""
        year     = extend.get("year") or ""
        lang     = extend.get("lang") or ""
        resource = extend.get("resource") or ""
        version  = extend.get("version") or ""
        letter   = extend.get("letter") or ""
        sort     = extend.get("sort") or "time"
        # 「频道」筛选直接切换子分类 type_id
        channel  = extend.get("channel") or ""
        if channel:
            tid = channel

        videos = []
        html = ""

        # 1. 无任何筛选时，原生静态子分类直连（最稳）
        if (tid not in ("1", "2", "3", "4") and not area and not cls and not year
                and not lang and not resource and not version and not letter
                and sort in ("time", "") and page == 1):
            url = "%s/vodtype/%s.html" % (self.site_url, tid)
            self.log("category (原生页): %s" % url)
            html = self._fetch(url)
            videos = self._extract_videos(html)

        # 2. 走 /vodshow/ 完整筛选路径（参数槽位实测对齐）
        if not videos:
            url = self._build_show_url(tid, area, cls, lang, letter, resource, version, sort, year, page)
            self.log("category (筛选页): %s" % url)
            html = self._fetch(url)
            videos = self._extract_videos(html)

        # 3. 终极兜底（如果上面都被 Ajax 防爬拦截了，搜索流直接干）
        if not videos:
            self.log("  ⚠️ 页面被防爬拦截，启用搜索流")
            wd = cls or year or area or lang or ""
            url2 = "%s/vodsearch/-------------.html?wd=%s&page=%d" % (self.site_url, urllib.parse.quote(wd), page)
            self.log("  (搜索兜底): %s" % url2)
            html2 = self._fetch(url2)
            videos = self._extract_search_videos(html2)
            html = html2

        pagecount = self._page_count(html)
        if pagecount == 1 and videos:
            pagecount = 999  # 搜索兜底情况允许无限翻页

        self.log("  最终: %d 条, 总页数: %d" % (len(videos), pagecount))

        return {
            "list": videos, "page": page, "pagecount": pagecount,
            "limit": 24, "total": pagecount * 24,
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        keyword = urllib.parse.quote(key)
        url = "%s/vodsearch/-------------.html?wd=%s&page=%d" % (self.site_url, keyword, page)
        html = self._fetch(url)
        videos = self._extract_search_videos(html)
        return {
            "list": videos, "page": page, "pagecount": self._page_count(html),
            "limit": 24, "total": 999,
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    def detailContent(self, ids):
        if not ids: return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        html = self._fetch(url)
        if not html: return {"list": []}

        name = ""
        m = _RE_H1.search(html)
        if m: name = self._clean(m.group(1))
        if not name:
            m = re.search(r"<title>(.*?)</title>", html, re.S)
            if m: name = self._clean(m.group(1).split("_")[0].split("-")[0])
        name = name or vod_id

        pic = self.default_pic
        m = _RE_DETAIL_PIC.search(html)
        if m: pic = self._fix_url(m.group(1)) or self.default_pic

        actor = ""
        m = _RE_ACTOR.search(html)
        if m:
            actor = self._clean(re.sub(r"</a>", "", m.group(1)))
            actor = re.sub(r"\s+", ",", actor).strip(",")

        director = ""
        m = _RE_DIRECTOR.search(html)
        if m:
            director = self._clean(re.sub(r"</a>", "", m.group(1)))
            director = re.sub(r"\s+", ",", director).strip(",")

        state = ""
        m = _RE_STATE.search(html)
        if m: state = self._clean(m.group(1))

        score = ""
        m = _RE_SCORE.search(html)
        if m: score = m.group(1)

        # 新增: 语言/类型/地区/年份/更新时间（对应详情页信息栏）
        lang = vtype = varea = vyear = upd = ""
        m = _RE_LANG.search(html)
        if m: lang = self._clean(m.group(1))
        m = _RE_TYPE.search(html)
        if m: vtype = self._clean(m.group(1))
        m = _RE_AREA.search(html)
        if m: varea = self._clean(m.group(1))
        m = _RE_YEAR.search(html)
        if m: vyear = self._clean(m.group(1))
        m = _RE_UPDATE.search(html)
        if m: upd = self._clean(m.group(1))

        content = ""
        m = _RE_INTRO.search(html)
        if m: content = self._clean(m.group(1))
        content = INTRO_PREFIX + ("\n" + content if content else "")

        tab_map = {}
        for m in _RE_TAB.finditer(html):
            tab_map[m.group(1)] = self._clean(m.group(2)) or "线路"

        lines = []
        for m in _RE_PLAYLIST.finditer(html):
            pid, inner = m.group(1), m.group(2)
            eps = []
            for em in _RE_EP.finditer(inner):
                href, ep_name = em.group(1), self._clean(em.group(2))
                eps.append("%s$%s" % (ep_name, self._fix_url(href)))
            if eps: lines.append((tab_map.get(pid, pid), eps))

        if not lines: return {"list": []}

        remarks = state or ("%d条线路" % len(lines))
        extra = " | ".join(x for x in [vtype, varea, vyear, lang, ("更新:" + upd) if upd else ""] if x)
        if extra:
            remarks = (remarks + " | " + extra) if remarks else extra

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_score": score,
            "vod_remarks": remarks,
            "vod_class": vtype,
            "vod_area": varea,
            "vod_year": vyear,
            "vod_lang": lang,
            "vod_time": upd,
            "vod_play_from": "$$$".join(x[0] for x in lines),
            "vod_play_url":  "$$$".join("#".join(x[1]) for x in lines),
        }]}

    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600: return res

        html = self._fetch(play_page)
        real_url = self._extract_player_url(html)

        if real_url:
            res = {
                "parse": 0,
                "playUrl": "",
                "url": real_url,
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }
        else:
            res = {
                "parse": 1,
                "playUrl": "",
                "url": play_page,
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }
            
        self._play_cache[play_page] = (now, res)
        return res

    def _extract_player_url(self, html):
        if not html: return ""
        m = _RE_PLAYER.search(html)
        if not m: return ""
        raw = m.group(1)
        try:
            data = json.loads(raw)
            url = data.get("url") or ""
            return url.replace("\\/", "/")
        except Exception:
            m2 = re.search(r'"url"\s*:\s*"([^"]+)"', raw)
            if m2: return m2.group(1).replace("\\/", "/")
            return ""

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
_TVBOX_LINE_ORDER = ["高清资源", "云播资源"]

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
