# coding=utf-8
"""
一起影视 yiqiys.com | TVBox Python 爬虫 
关键:
  - MacCMS 标准模板, 结构固定
  - 分类页: /show/{tid}-{area}-{by}-{lang}--{page}---{year}.html
  - 分类筛选: 类型/地区/年份/语言/排序 
  - 搜索页: /search/{keyword}----------{page}---.html (有页码)
            /search/{keyword}-------------.html    (无页码)
  - 详情页: /detail/{id}.html, 从 player_data 直接提取 m3u8 直链
  - 详情页线路数量/名称/CDN 全由服务端动态决定, 全部动态解析
  - m3u8 全部托管在第三方 CDN, 统一用 m3u8 自身域名做 Referer
"""
import re
import sys
import json
import time
import urllib.parse
import datetime

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
                print("[yiqiys]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.yiqiys.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/statics/img/load.gif"

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
]

_SORTS = [{"n": "最新", "v": "time"},
          {"n": "热门", "v": "hits"}]

_current_year = datetime.datetime.now().year
_YEARS = [{"n": "全部", "v": ""}] + \
         [{"n": str(y), "v": str(y)} for y in range(_current_year, 2009, -1)]

_AREAS_FULL = [
    {"n": "全部", "v": ""},
    {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
    {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"},
    {"n": "法国", "v": "法国"}, {"n": "英国", "v": "英国"},
    {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"},
    {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"},
    {"n": "西班牙", "v": "西班牙"}, {"n": "加拿大", "v": "加拿大"},
    {"n": "俄罗斯", "v": "俄罗斯"}, {"n": "新加坡", "v": "新加坡"},
    {"n": "其它", "v": "其它"},
]

_AREAS_SHORT = [
    {"n": "全部", "v": ""},
    {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
    {"n": "美国", "v": "美国"}, {"n": "台湾", "v": "台湾"},
    {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"},
]

# 语言选项 (从分类页源码 <ul><li><span>语言：</span>... 提取)
_LANGS = [
    {"n": "全部", "v": ""},
    {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"},
    {"n": "粤语", "v": "粤语"}, {"n": "韩语", "v": "韩语"},
    {"n": "日语", "v": "日语"}, {"n": "法语", "v": "法语"},
    {"n": "德语", "v": "德语"}, {"n": "其它", "v": "其它"},
]

# 从 /show/5-----------.html / /show/12-----------.html 源码提取
_FILTERS_MAP = {
    "dianying": [
        {"n": "全部", "v": ""},
        {"n": "动作片", "v": "5"}, {"n": "喜剧片", "v": "6"},
        {"n": "爱情片", "v": "7"}, {"n": "科幻片", "v": "8"},
        {"n": "恐怖片", "v": "9"}, {"n": "剧情片", "v": "10"},
        {"n": "战争片", "v": "11"},
    ],
    "dianshiju": [
        {"n": "全部", "v": ""},
        {"n": "国产剧", "v": "12"}, {"n": "港台剧", "v": "13"},
        {"n": "欧美剧", "v": "14"}, {"n": "日韩剧", "v": "15"},
        {"n": "海外剧", "v": "16"},
    ],
    "zongyi":    [{"n": "全部", "v": ""}],
    "dongman":   [{"n": "全部", "v": ""}],
}

_TID_TO_KEY = {
    "1": "dianying", "2": "dianshiju",
    "3": "zongyi",   "4": "dongman",
}

FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    key = _TID_TO_KEY.get(tid, tid)
    areas = _AREAS_FULL if tid in ("1", "2") else _AREAS_SHORT
    FILTERS[tid] = [
        {"key": "class", "name": "类型",
         "value": _FILTERS_MAP.get(key, [{"n": "全部", "v": ""}])},
        {"key": "area",  "name": "地区", "value": areas},
        {"key": "year",  "name": "年份", "value": _YEARS},
        {"key": "lang",  "name": "语言", "value": _LANGS},
        {"key": "sort",  "name": "排序", "value": _SORTS},
    ]


# ===================== 正则 =====================
# 卡片: <a class="stui-vodlist__thumb [active ]lazyload" href="/detail/xxx.html"
#       title="..." data-original="...">
_RE_CARD = re.compile(
    r'<a\s+class="stui-vodlist__thumb[^"]*"[^>]*?'
    r'href="(/detail/[^"]+?\.html)"[^>]*?'
    r'title="([^"]*)"[^>]*?'
    r'data-original="([^"]*)"',
    re.I)

# 备注: <span class="pic-text text-right">更新至01集</span>
#       <span class="score pull-right">第24集已完结</span>
_RE_REMARK = re.compile(
    r'<span\s+class="(?:pic-text[^"]*|score\s+pull-right)">([^<]+)</span>',
    re.I)

# 分页总数: <li class="active num"><a>2/59</a></li>
_RE_PAGECOUNT = re.compile(r'<li\s+class="active num"><a>\d+/(\d+)</a></li>')

# 详情页标题: <h1 class="title">老舅</h1>
_RE_H1 = re.compile(r'<h1\s+class="title"[^>]*>([^<]+)</h1>', re.I)

# 详情页封面: <a class="pic" ...><img class="lazyload" data-original="...">
_RE_PIC = re.compile(
    r'<a\s+class="pic"[^>]*>[\s\S]*?<img[^>]*?data-original="([^"]+)"',
    re.I)

# 简介: <span class="detail-content" style="display: none;">...</span>
_RE_INTRO = re.compile(
    r'<span\s+class="detail-content"[^>]*>([\s\S]*?)</span>',
    re.I)

# 元信息（均按真实标签后紧跟内容的模式）
# 状态: <p class="data"><span class="data2">状态：</span><span class="data3">更新至第16集</span></p>
_RE_STATUS = re.compile(
    r'状态：</span>\s*<span[^>]*>([^<]+)</span>', re.I)
_RE_YEAR = re.compile(r'年份：</span>\s*(\d{4})')
# 更新: <p class="data"><span class="data2">更新：</span>2026-10-16</p>
_RE_UPDATE = re.compile(
    r'更新：</span>\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})')
_RE_AREA = re.compile(r'国家：</span>\s*([^<\s]+)')
# 类型: <p class="data"><span class="data2">类型：</span><a href="/show/12-----------.html">国产剧</a></p>
_RE_CLASS = re.compile(r'类型：</span>\s*<a[^>]*>([^<]+)</a>')
_RE_DIRECTOR = re.compile(r'导演：</span>([\s\S]*?)</p>')
_RE_ACTOR = re.compile(r'主演：</span>([\s\S]*?)</p>')

# 播放线路块: <h4>...<i class="...iconfontplay2"></i>&nbsp;红牛云播</h4>
#              <ul class="stui-content__playlist clearfix">...</ul>
# 注: 站点线路数量/名称均由服务端动态决定, 正则按 order 顺序遍历所有块
_RE_PLAY_BLOCK = re.compile(
    r'iconfontplay2[^>]*></i>&nbsp;([^<]+?)</h4>\s*'
    r'<ul\s+class="stui-content__playlist clearfix">([\s\S]*?)</ul>',
    re.I)

# 单集: <li><a href="/play/560573-2-1.html">第01集</a></li>
_RE_EPISODE = re.compile(
    r'<a\s+href="(/play/[^"]+?\.html)"[^>]*>([^<]+)</a>',
    re.I)

# 播放页 player_data 里的 url 字段
#   源码: "url":"https:\/\/xxx.cdn.com\/...\/index.m3u8"
#   CDN 域名不固定, 由站点后端按线路动态分配
_RE_PLAYER_URL = re.compile(r'"url"\s*:\s*"([^"]+)"')


class Spider(Spider):

    def getName(self):
        return "一起影视"

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
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": self.site_url + "/",
            "Upgrade-Insecure-Requests": "1",
        }
        self.default_pic = DEFAULT_PIC
        self._play_cache = {}
        self._warmed = False
        self.log("init: site=%s" % self.site_url)

    def _warm_up(self):
        if self._warmed:
            return
        try:
            self._fetch(self.site_url + "/", timeout=15)
            self._warmed = True
            self.log("预热完成")
        except Exception as e:
            self.log("预热失败: %s" % e)

    def _fetch(self, url, timeout=15, headers=None):
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
        s = re.sub(r"<[^>]+>", "", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    def _extract_videos(self, html):
        videos = []
        seen = set()
        if not html:
            self.log("  HTML 为空")
            return videos

        matches = list(_RE_CARD.finditer(html))
        self.log("  完整卡片: %d 条" % len(matches))

        for m in matches:
            href = m.group(1)
            title = m.group(2)
            pic = m.group(3)
            if href in seen:
                continue
            seen.add(href)

            # 备注紧跟卡片之后, 扫描 300 字符以内
            start = m.end()
            end = min(start + 300, len(html))
            snippet = html[start:end]
            rm = _RE_REMARK.search(snippet)
            remark = rm.group(1).strip() if rm else ""

            videos.append({
                "vod_id":      href,
                "vod_name":    self._clean(title)[:100],
                "vod_pic":     self._fix_url(pic) or self.default_pic,
                "vod_remarks": remark,
            })
        return videos

    def _page_count(self, html):
        if not html:
            return 1
        m = _RE_PAGECOUNT.search(html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        return 1

    # 源码 URL 拆解:
    #   /show/6-----------.html                        (无筛选)
    #   /show/6-大陆----------2026.html                 (area+year)
    #   /show/6-大陆-------2---2026.html                (area+page+year)
    #   /show/6-大陆-time---------2026.html             (area+sort+year)
    #   /show/6-大陆---国语-------2026.html              (area+lang+year)
    # 12 字段: [tid, area, by, "", lang, "", "", "", page, "", "", year]
    def _build_show_url(self, tid, area="", year="", by="", lang="", page=1):
        parts = [""] * 12
        parts[0] = str(tid)
        parts[1] = urllib.parse.quote(area) if area else ""
        parts[2] = by or ""
        parts[4] = urllib.parse.quote(lang) if lang else ""
        parts[8] = str(page) if page and int(page) > 1 else ""
        parts[11] = year or ""
        return "%s/show/%s.html" % (self.site_url, "-".join(parts))

    # 搜索 URL 拆解 (来自搜索结果页源码分页栏):
    #   无页码: /search/{keyword}-------------.html          (13个-)
    #   有页码: /search/{keyword}----------{page}---.html    (10个- + page + 3个-)
    def _build_search_url(self, key, page=1):
        enc = urllib.parse.quote(key)
        if page and int(page) > 1:
            return "%s/search/%s----------%d---.html" % (
                self.site_url, enc, int(page))
        return "%s/search/%s-------------.html" % (self.site_url, enc)

    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        self._warm_up()
        url = self.site_url + "/"
        html = self._fetch(url)
        self.log("home HTML 长度: %d" % len(html))
        videos = self._extract_videos(html)
        return {"list": videos}

    def categoryContent(self, tid, pg, filter, extend):
        self._warm_up()
        page = int(pg) if pg else 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not extend:
            extend = {}

        for k in list(extend.keys()):
            if extend[k] in ("", None, "全部"):
                del extend[k]

        # 选中子分类时用子分类 tid 覆盖一级 tid
        use_tid = extend.get("class") or tid
        area = extend.get("area") or ""
        year = extend.get("year") or ""
        by   = extend.get("sort") or ""
        lang = extend.get("lang") or ""

        url = self._build_show_url(
            use_tid, area=area, year=year, by=by, lang=lang, page=page)
        self.log("category: %s" % url)
        html = self._fetch(url)
        self.log("  HTML 长度: %d" % len(html))

        videos = self._extract_videos(html)
        pagecount = self._page_count(html)
        self.log("  最终: %d 条, 总页数: %d" % (len(videos), pagecount))

        return {
            "list": videos, "page": page, "pagecount": pagecount,
            "limit": 24, "total": pagecount * 24,
        }

    def searchContent(self, key, quick, pg="1"):
        self._warm_up()
        page = int(pg) if pg else 1
        url = self._build_search_url(key, page)
        self.log("search: %s" % url)
        html = self._fetch(url)
        self.log("  HTML 长度: %d" % len(html))
        videos = self._extract_videos(html)
        pagecount = self._page_count(html)
        return {
            "list": videos, "page": page,
            "pagecount": pagecount,
            "limit": 24, "total": pagecount * 24,
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
        self.log("  HTML 长度: %d" % len(html))
        if not html:
            return {"list": []}

        # 标题
        name = ""
        try:
            m = _RE_H1.search(html)
            if m:
                name = self._clean(m.group(1))
        except Exception:
            pass
        if not name:
            try:
                m = re.search(r"<title>(.*?)</title>", html, re.S)
                if m:
                    name = self._clean(m.group(1).split("_")[0].split("-")[0])
            except Exception:
                pass
        name = re.sub(r"\s*\(\d{4}\)\s*$", "", name).strip() or vod_id

        # 封面
        pic = self.default_pic
        try:
            m = _RE_PIC.search(html)
            if m:
                pic = self._fix_url(m.group(1))
        except Exception:
            pass

        # 简介
        content = ""
        try:
            m = _RE_INTRO.search(html)
            if m:
                content = self._clean(m.group(1))
        except Exception:
            pass

        if content:
            content = INTRO_PREFIX + "\n" + content
        else:
            content = INTRO_PREFIX

        # 元信息
        # 状态: 更新至第16集
        status_val = ""
        try:
            m = _RE_STATUS.search(html)
            if m:
                status_val = self._clean(m.group(1))
        except Exception:
            pass

        year = ""
        try:
            m = _RE_YEAR.search(html)
            if m:
                year = m.group(1)
        except Exception:
            pass

        # 更新: 2026-10-16
        update_val = ""
        try:
            m = _RE_UPDATE.search(html)
            if m:
                update_val = m.group(1)
        except Exception:
            pass

        area_val = ""
        try:
            m = _RE_AREA.search(html)
            if m:
                area_val = self._clean(m.group(1))
        except Exception:
            pass

        # 类型: 国产剧
        class_val = ""
        try:
            m = _RE_CLASS.search(html)
            if m:
                class_val = self._clean(m.group(1))
        except Exception:
            pass

        director = ""
        try:
            m = _RE_DIRECTOR.search(html)
            if m:
                director = self._clean(m.group(1))
        except Exception:
            pass

        actor = ""
        try:
            m = _RE_ACTOR.search(html)
            if m:
                actor = self._clean(m.group(1))
        except Exception:
            pass

        # 播放列表 (按 <h4>线路</h4><ul>剧集</ul> 顺序提取)
        # 注: 站点线路数量/名称动态, 全部保留, 不写死任何一条
        groups = {}
        try:
            for m in _RE_PLAY_BLOCK.finditer(html):
                line_name = self._clean(m.group(1))
                ul_html = m.group(2)

                eps = []
                for em in _RE_EPISODE.finditer(ul_html):
                    href = em.group(1)
                    ep_name = self._clean(em.group(2)) or ("第%d集" % (len(eps) + 1))
                    if href.startswith("/"):
                        href = self.site_url + href
                    eps.append((ep_name, href))

                if eps:
                    groups[line_name] = eps
        except Exception as e:
            self.log("  剧集解析失败: %s" % e)

        self.log("  剧集: %s" % {k: len(v) for k, v in groups.items()})
        self.log("  状态: [%s] | 更新: [%s] | 类型: [%s]" % (
            status_val, update_val, class_val))

        if not groups:
            return {"list": []}

        play_from = []
        play_url = []
        for line_name, eps in groups.items():
            play_from.append(line_name)
            play_url.append("#".join("%s$%s" % (n, h) for n, h in eps))

        # vod_remarks 优先用状态, 无状态时回退到线路数
        remarks = status_val if status_val else ("%d条线路" % len(groups))

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_year": year,
            "vod_area": area_val,
            "vod_class": class_val,
            "type_name": class_val,
            "vod_pubdate": update_val,
            "vod_date":    update_val,
            "vod_note":    update_val,
            "vod_remarks": remarks,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url":  "$$$".join(play_url),
        }]}

    # -------- 播放 --------
    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        self.log("player: %s" % play_page)

        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600:
                return res

        html = self._fetch(play_page)
        if not html:
            res = {"parse": 1, "playUrl": "", "url": play_page,
                   "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}
            self._play_cache[play_page] = (now, res)
            return res

        # player_data 里的 "url":"https:\/\/xxx.cdn.com\/...\/index.m3u8"
        # 域名由站点后端按线路动态分配, 不写死任何 CDN
        m3u8_url = ""
        try:
            m = _RE_PLAYER_URL.search(html)
            if m:
                raw = m.group(1)
                raw = (raw.replace("\\/", "/")
                          .replace("\\u0026", "&")
                          .replace("\\u0022", '"'))
                if raw.startswith("http"):
                    m3u8_url = raw
        except Exception as e:
            self.log("  player_data 解析失败: %s" % e)

        if m3u8_url:
            # 关键: 一律用 m3u8 自身域名做 Referer,
            # 第三方 CDN 都带防盗链, 用站点域名做 Referer 会被拒,
            # 表现为"只有声音没有画面"。对任何线路都通用, 不写死
            try:
                p = urllib.parse.urlparse(m3u8_url)
                m3u8_referer = "%s://%s/" % (p.scheme, p.netloc)
            except Exception:
                m3u8_referer = self.site_url + "/"

            self.log("  => 直链 m3u8: %s" % m3u8_url[:200])
            self.log("  => Referer: %s" % m3u8_referer)

            res = {
                "parse": 0,
                "playUrl": "",
                "url": m3u8_url,
                "header": {
                    "User-Agent": UA,
                    "Referer": m3u8_referer,
                },
            }
            self._play_cache[play_page] = (now, res)
            return res

        # 兜底：交给 TVBox 嗅探
        res = {"parse": 1, "playUrl": "", "url": play_page,
               "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}
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
                            url = v
            if not url:
                return [200, "image/jpeg", b"", ""]
            url = urllib.parse.unquote(url) if "%" in url else url
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
        return ".m3u8" in url or ".mp4" in url or url.startswith("http")

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def close(self):
        self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
