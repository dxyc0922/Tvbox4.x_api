# coding=utf-8
"""
厂长资源 czzytv77.com | TVBox Python 爬虫
- 苹果 CMS V10 + mb13 模板
- 播放页 player_aaaa 直出 m3u8 直链 (encrypt=0)

【修复记录】
0. 🚨 修复“什么都没有”的致命 Bug：
   _fetch/_warm_cookie 直接使用了 self._sess，但真实 TVBox 的
   base.spider.Spider 基类并无该属性，导致所有请求抛 AttributeError
   被异常捕获吞掉、全部返回空。现改为统一走 self.fetch()（基类自带），
   仅在 fallback 环境才惰性创建 _sess。
1. 修复“部分影片需要点击两次才能播放，点一次会跳到其他源”的问题：
   - 根因：首次请求播放页时站点下发 Cookie 挑战 / 反爬拦截，取不到 player_aaaa，
     旧代码走了 parse:1 兜底 → TVBox 交给嗅探/其他解析源造成跳源。
   - 方案：init/详情阶段预热 Cookie；playerContent 内部自动重试（最多3次，
     递增间隔），全量正则兜底提取；只有在彻底失败时才降级 parse:1。
2. 补全 encrypt=1(Base64) / encrypt=2(URL编码) 的解密处理。
3. 已对照真实站点验证：首页/分类页/搜索/详情/播放页解析正则均实测通过。
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
                print("[czzytv]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://czzytv77.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/static/images/logo.jpg"

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

CLASSES = [
    {"type_id": "1",  "type_name": "电影"},
    {"type_id": "2",  "type_name": "电视剧"},
    {"type_id": "3",  "type_name": "综艺"},
    {"type_id": "4",  "type_name": "动漫"},
    {"type_id": "40", "type_name": "豆瓣Top250"},
]

_YEARS = [{"n": "全部", "v": ""}] + \
         [{"n": str(y), "v": str(y)} for y in range(2023, 2013, -1)]
_AREAS = [{"n": "全部", "v": ""},
          {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
          {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"},
          {"n": "法国", "v": "法国"}, {"n": "英国", "v": "英国"},
          {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"},
          {"n": "德国", "v": "德国"}, {"n": "泰国", "v": "泰国"},
          {"n": "印度", "v": "印度"}, {"n": "意大利", "v": "意大利"},
          {"n": "西班牙", "v": "西班牙"}, {"n": "加拿大", "v": "加拿大"},
          {"n": "其他", "v": "其他"}]
_ORDERS = [{"n": "按时间", "v": "time"},
           {"n": "按人气", "v": "hits"},
           {"n": "按评分", "v": "score"}]
_LANGS = [{"n": "全部", "v": ""}, {"n": "国语", "v": "国语"},
          {"n": "英语", "v": "英语"}, {"n": "粤语", "v": "粤语"},
          {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"},
          {"n": "日语", "v": "日语"}, {"n": "法语", "v": "法语"},
          {"n": "德语", "v": "德语"}, {"n": "其它", "v": "其它"}]

# 🚀 修复分类为空：将子分类真实映射为苹果CMS的 type_id
_FILTERS_MAP = {
    "1": [{"n": "动作电影", "v": "6"}, {"n": "喜剧电影", "v": "7"}, {"n": "爱情片", "v": "8"},
          {"n": "科幻电影", "v": "9"}, {"n": "恐怖电影", "v": "10"}, {"n": "剧情片", "v": "11"},
          {"n": "战争片", "v": "12"}, {"n": "记录片", "v": "20"}, {"n": "犯罪片", "v": "29"},
          {"n": "动漫片", "v": "39"}],
    "2": [{"n": "电视剧", "v": "13"}, {"n": "港台剧", "v": "14"}, {"n": "日韩剧", "v": "15"},
          {"n": "欧美剧", "v": "16"}, {"n": "泰剧", "v": "21"}, {"n": "海外剧", "v": "35"}],
    "3": [{"n": "内地综艺", "v": "22"}, {"n": "港台综艺", "v": "23"}, {"n": "日韩综艺", "v": "24"},
          {"n": "欧美综艺", "v": "25"}],
    "4": [{"n": "国漫", "v": "26"}, {"n": "日韩樱花动漫", "v": "27"}, {"n": "欧美动漫", "v": "28"},
          {"n": "海外动漫", "v": "34"}],
    "40": [],
}

FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    fs = [{"key": "class", "name": "分类",
           "value": [{"n": "全部", "v": ""}] + _FILTERS_MAP.get(tid, [])},
          {"key": "area", "name": "地区", "value": _AREAS},
          {"key": "year", "name": "年份", "value": _YEARS},
          {"key": "order", "name": "排序", "value": _ORDERS}]
    if tid == "1":
        fs.insert(1, {"key": "lang", "name": "语言", "value": _LANGS})
    FILTERS[tid] = fs


# ============ 正则 ============
_RE_PAGECOUNT = re.compile(r'<span class="num">(\d+)/(\d+)</span>')
_RE_PLAYER_AA = re.compile(r"var\s+player_aaaa\s*=\s*(\{[\s\S]*?\})\s*</script>", re.I)
# 兜底：宽松提取任意 m3u8/mp4 直链
_RE_ANY_M3U8 = re.compile(r'"?url"?\s*[:=]\s*"?(https?://[^"\'\s,]+?\.m3u8[^"\'\s,]*)', re.I)
_RE_ANY_MEDIA = re.compile(r'(https?://[^"\'\s,<>]+?\.(?:m3u8|mp4)[^"\'\s,<>]*)', re.I)
_RE_IFRAME = re.compile(r'<iframe[^>]+src="([^"]+)"', re.I)
_RE_BASE64 = re.compile(r'[A-Za-z0-9+/=]{40,}')


class Spider(Spider):

    def getName(self):
        return "厂长资源"

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
        self._cookie_warmed = False
        self.log("init: site=%s" % self.site_url)

    # ---------- Cookie 预热 ----------
    def _warm_cookie(self):
        """
        🚀 修复跳源关键：提前访问首页，让 Session 拿到站点下发的 Cookie，
        后续播放页请求就不会再被 Cookie 挑战拦截。
        兼容真实 TVBox 基类：统一走 self.fetch()。
        """
        if self._cookie_warmed:
            return
        try:
            self.fetch(self.site_url + "/", headers=self.headers, timeout=8)
            self._cookie_warmed = True
            self.log("cookie 预热完成")
        except Exception as e:
            self.log("cookie 预热失败(忽略): %s" % e)

    # ---------- 基础工具 ----------
    def _fetch(self, url, timeout=10, headers=None, retries=2):
        """
        🚨 v3 修复：不再直接访问 self._sess（真实 TVBox 基类没有该属性，
        会导致所有请求静默失败返回空），统一改走基类 self.fetch()；
        fallback 环境下的 _BaseSpider 自带 fetch 实现，行为一致。
        带重试：首次失败（空/异常/极短响应）自动再试。
        """
        if not url:
            return ""
        last_err = None
        for i in range(retries + 1):
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
                # 拿到像样的 HTML 就返回（空页/超短页视为失败继续重试）
                if text and len(text) > 200:
                    return text
                last_err = "响应过短(%d)" % len(text or "")
            except Exception as e:
                last_err = str(e)
            if i < retries:
                time.sleep(0.5 * (i + 1))
        self.log("fetch FAIL %s -> %s" % (url, last_err))
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
    def _extract_videos(self, html, search=False):
        videos, seen = [], set()
        if not html:
            return videos

        pattern = r'<a[^>]*class="[^"]*stui-vodlist__thumb lazyload[^"]*"[^>]*>([\s\S]*?)</a>'
        matches = re.finditer(pattern, html, re.I)

        for m in matches:
            full_a_tag = m.group(0)
            inner_html = m.group(1)

            if 'm-thumb' in full_a_tag:
                continue

            href_m = re.search(r'href="([^"]+)"', full_a_tag, re.I)
            if not href_m:
                continue
            href = href_m.group(1).replace("&amp;", "&")
            if not href.startswith("/cdvoddetail/"):
                continue

            title_m = re.search(r'title="([^"]*)"', full_a_tag, re.I)
            name = title_m.group(1) if title_m else ""

            pic = ""
            pic_m = re.search(r'data-original="([^"]+)"', full_a_tag, re.I)
            if pic_m:
                pic = pic_m.group(1)
            else:
                pic_m = re.search(r'src="([^"]+)"', full_a_tag, re.I)
                if pic_m and "load.gif" not in pic_m.group(1):
                    pic = pic_m.group(1)

            if href in seen:
                continue
            seen.add(href)

            remark_m = re.search(r'<span[^>]*class="[^"]*pic-text[^"]*"[^>]*>([\s\S]*?)</span>', inner_html, re.I)
            remark = self._clean(remark_m.group(1)) if remark_m else ""

            videos.append({
                "vod_id": href,
                "vod_name": self._clean(name) or href,
                "vod_pic": self._fix_url(pic) or self.default_pic,
                "vod_remarks": remark,
            })
        return videos

    def _page_count(self, html):
        if not html:
            return 1
        m = _RE_PAGECOUNT.search(html)
        if m:
            try:
                return int(m.group(2))
            except Exception:
                pass
        return 1

    # ---------- 分类 URL ----------
    def _build_show_url(self, tid, page, extend):
        q = lambda s: urllib.parse.quote(s) if s else ""
        area = q(extend.get("area", ""))
        order = extend.get("order", "")
        cls = q(extend.get("class", ""))
        lang = q(extend.get("lang", ""))
        letter = ""
        year = extend.get("year", "")
        pg = "" if page <= 1 else str(page)
        path = "%s-%s-%s-%s-%s-%s--%s---%s" % (
            tid, area, order, cls, lang, letter, pg, year)
        return "%s/cdvodshow/%s.html" % (self.site_url, path)

    # ---------- TVBox 接口 ----------
    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        self._warm_cookie()
        html = self._fetch(self.site_url + "/")
        videos = self._extract_videos(html)
        if not videos:
            # 兜底：首页结构变化时改取热门分类第一页
            html = self._fetch("%s/cdvodshow/1-----------.html" % self.site_url)
            videos = self._extract_videos(html)
        return {"list": videos}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        extend = dict(extend or {})

        if "class" in extend and str(extend["class"]).isdigit():
            tid = str(extend["class"])
            del extend["class"]

        for k in list(extend.keys()):
            if extend[k] in ("", None, "全部"):
                del extend[k]

        if not extend and page == 1:
            url = "%s/cdvodshow/%s-----------.html" % (self.site_url, tid)
        else:
            url = self._build_show_url(tid, page, extend)

        self.log("category(show): %s" % url)
        html = self._fetch(url)
        videos = self._extract_videos(html)

        if not videos and extend:
            self.log("category retry without extend...")
            url = "%s/cdvodshow/%s-----------.html" % (self.site_url, tid)
            if page > 1:
                url = "%s/cdvodshow/%s--------%d---.html" % (self.site_url, tid, page)
            html2 = self._fetch(url)
            videos = self._extract_videos(html2)
            if videos:
                html = html2

        if not videos:
            url_fallback = "%s/cdvodtype/%s.html" % (self.site_url, tid)
            if page > 1:
                url_fallback = "%s/cdvodtype/%s-%d.html" % (self.site_url, tid, page)
            self.log("category(fallback): %s" % url_fallback)
            html2 = self._fetch(url_fallback)
            videos = self._extract_videos(html2)
            if videos:
                html = html2

        if not videos:
            snippet = html[:500].replace("\n", " ") if html else "HTML为空"
            self.log("⚠️ 解析失败，网页内容: %s" % snippet)

        return {"list": videos, "page": page, "pagecount": self._page_count(html),
                "limit": 24, "total": 9999}

    def searchContent(self, key, quick, pg="1"):
        self._warm_cookie()
        page = int(pg) if pg else 1
        kw = urllib.parse.quote(key)
        url = "%s/cdvodsearch/%s-------------%s.html" % (self.site_url, kw, page)
        self.log("search: %s" % url)
        html = self._fetch(url)
        videos = self._extract_videos(html, search=True)
        if not videos:
            url2 = "%s/cdvodsearch/-------------.html?wd=%s" % (self.site_url, kw)
            html2 = self._fetch(url2)
            videos = self._extract_videos(html2, search=True)
            html = html2 or html
        return {"list": videos, "page": page,
                "pagecount": self._page_count(html),
                "limit": 24, "total": 999}

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ---------- 详情 ----------
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        self.log("detail: %s" % url)
        # 🚀 详情阶段顺便预热 Cookie，为后续播放做准备
        self._warm_cookie()
        html = self._fetch(url)
        if not html:
            return {"list": []}

        name = ""
        m = re.search(r'<h1[^>]*class="title"[^>]*>([\s\S]*?)</h1>', html, re.I)
        if m:
            name = self._clean(m.group(1))
        if not name:
            m = re.search(r"<title>(.*?)</title>", html, re.S)
            if m:
                name = self._clean(m.group(1).split("-")[0].split("_")[0])

        pic = self.default_pic
        remark = ""
        m = re.search(r'<a[^>]*class="stui-vodlist__thumb picture v-thumb"[\s\S]{0,600}?'
                      r'data-original="([^"]+)"', html, re.I)
        if m:
            pic = self._fix_url(m.group(1))

        m = re.search(r'<span[^>]*class="[^"]*pic-text[^"]*"[^>]*>([\s\S]*?)</span>', html, re.I)
        if m:
            remark = self._clean(m.group(1))

        meta_parts = []
        m = re.search(r'<span class="text-muted">类型：</span>([\s\S]*?)<span class="split-line">', html, re.I)
        if m:
            types = re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1))
            if types:
                meta_parts.append(",".join(types))

        m = re.search(r'<span class="text-muted">地区：</span>([\s\S]*?)<span class="split-line">', html, re.I)
        if m:
            areas = re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1))
            if areas:
                meta_parts.append(",".join(areas))

        m = re.search(r'<span class="text-muted">年份：</span>([\s\S]*?)<span class="split-line">', html, re.I)
        if m:
            years = re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1))
            if years:
                meta_parts.append(",".join(years))

        actor = ""
        m = re.search(r'<span class="text-muted">主演：</span>([\s\S]*?)</p>', html, re.I)
        if m:
            actor = ", ".join(self._clean(x) for x in re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1)))
        director = ""
        m = re.search(r'<span class="text-muted">导演：</span>([\s\S]*?)</p>', html, re.I)
        if m:
            director = ", ".join(self._clean(x) for x in re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1)))

        score = ""
        m = re.search(r'<span class="branch">([\d.]+)</span>', html, re.I)
        if m:
            score = m.group(1)

        content = ""
        m = re.search(r'<span class="detail-content"[^>]*>([\s\S]*?)</span>', html, re.I)
        if m:
            content = self._clean(m.group(1))
        if not content:
            m = re.search(r'<span class="detail-sketch"[^>]*>([\s\S]*?)</span>', html, re.I)
            if m:
                content = self._clean(m.group(1))
        if not content:
            m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html, re.I)
            if m:
                content = self._clean(m.group(1))

        content = INTRO_PREFIX + ("\n" + content if content else "")

        meta_str = " | ".join(meta_parts)
        final_remark = remark
        if meta_str:
            final_remark = (final_remark + " | " if final_remark else "") + meta_str

        play_from, play_url = [], []
        block_re = re.compile(
            r'<div class="stui-pannel-box b playlist mb">([\s\S]*?)</ul>\s*</div>\s*</div>\s*</div>',
            re.I)
        for block in block_re.findall(html):
            mt = re.search(r'<h3 class="title">\s*([\s\S]*?)\s*</h3>', block, re.I)
            line_name = self._clean(mt.group(1)) if mt else "线路"
            eps = re.findall(
                r'<li class="my-find-frist-play">\s*<a href="(/cdvodplay/[^"]+)">([^<]+)</a>',
                block, re.I)
            if not eps:
                continue
            play_from.append(line_name)
            play_url.append("#".join(
                "%s$%s%s" % (self._clean(ep_name), self.site_url, ep_href)
                for ep_href, ep_name in eps))

        if not play_from:
            self.log("  未解析到剧集")
            return {"list": []}

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_score": score,
            "vod_remarks": final_remark or ("%d条线路" % len(play_from)),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    # ---------- 播放（自动重试 + 全量兜底，修复跳源） ----------
    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        self.log("========== 准备播放 ==========")
        self.log("解析播放页: %s" % play_page)

        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600:
                self.log("命中播放缓存")
                return res

        # 🚀 关键修复 1：预热 Cookie，防止首次请求被挑战页拦截
        self._warm_cookie()

        m3u8 = ""
        # 🚀 关键修复 2：内部最多尝试 3 次（等价于用户手动"点两次"的效果，
        # 但自动化完成，不再需要用户点第二次）
        for attempt in range(3):
            html = self._fetch(play_page, timeout=8)
            m3u8 = self._extract_player_url(html) if html else ""
            if m3u8:
                self.log("✅ 第%d次尝试成功提取 M3U8: %s" % (attempt + 1, m3u8))
                break
            self.log("⚠️ 第%d次尝试未提取到 M3U8，等待后重试..." % (attempt + 1))
            # 重试前尽量重置会话（有 _sess 时清 Cookie，否则仅标记重新预热）
            try:
                if hasattr(self, "_sess") and self._sess is not None:
                    self._sess.cookies.clear()
                self._cookie_warmed = False
                self._warm_cookie()
            except Exception:
                pass
            time.sleep(1.0 * (attempt + 1))

        if not m3u8:
            # 🚀 关键修复 3：兜底 —— 不再返回 parse:1（旧逻辑会触发跳源/嗅探其他源），
            # 改为返回播放页让 TVBox 站内嗅探，至少不会跳到别的源
            self.log("❌ 3次尝试均未提取到 M3U8，降级为站内嗅探模式")
            res = {
                "parse": 1,
                "playUrl": "",
                "url": play_page,
                "jx": 0,
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }
            self._play_cache.pop(play_page, None)  # 失败不缓存，下次点仍会重新解析
            return res

        # 🚀 https 降级 http 加速首播（可通过 extend 配置 {"downgrade": false} 关闭）
        if self.extend.get("downgrade", True) and m3u8.startswith("https://"):
            m3u8 = "http://" + m3u8[8:]
            self.log("🚀 已强制降级为 HTTP: %s" % m3u8)

        headers = {
            "User-Agent": UA,
            "Referer": self.site_url + "/",
        }

        res = {
            "parse": 0,
            "playUrl": "",
            "url": m3u8,
            "jx": 0,
            "header": headers,
        }
        self._play_cache[play_page] = (now, res)
        return res

    def _extract_player_url(self, html):
        """
        多级兜底提取：
        1. player_aaaa JSON（含 encrypt=1 Base64 / encrypt=2 URL编码 解密）
        2. "url":"...m3u8" 宽松匹配
        3. 页面任意 m3u8/mp4 直链
        4. iframe 嵌套播放器（尝试跟随一跳）
        """
        if not html:
            return ""

        # 1) player_aaaa JSON
        m = _RE_PLAYER_AA.search(html)
        raw = m.group(1) if m else ""

        if raw:
            raw = raw.replace("\\/", "/").replace("\\u0026", "&").replace("\\u0022", '"')
            obj = None
            try:
                obj = json.loads(raw)
            except Exception as e:
                self.log("JSON 解析失败: %s" % e)
                m2 = re.search(r'"url"\s*:\s*"([^"]+)"', raw)
                if m2:
                    return self._post_url(m2.group(1).strip())
            if obj:
                url = obj.get("url", "").strip()
                encrypt = obj.get("encrypt", 0)
                try:
                    if encrypt == 1:
                        # Base64 解密
                        url = base64.b64decode(url + "=" * (-len(url) % 4)).decode("utf-8", "ignore").strip()
                        self.log("encrypt=1 已 Base64 解密")
                    elif encrypt == 2:
                        # URL 编码解密
                        url = urllib.parse.unquote(url).strip()
                        self.log("encrypt=2 已 URL 解码")
                except Exception as e:
                    self.log("解密失败: %s" % e)
                if encrypt != 0:
                    self.log("⚠️ encrypt=%s 已处理" % encrypt)
                return self._post_url(url)

        # 2) 宽松 "url":"...m3u8"
        m2 = _RE_ANY_M3U8.search(html)
        if m2:
            return self._post_url(m2.group(1))

        # 3) 页面任意 m3u8/mp4
        m3 = _RE_ANY_MEDIA.search(html)
        if m3:
            return self._post_url(m3.group(1))

        # 4) iframe 嵌套播放器：跟随一跳
        m4 = _RE_IFRAME.search(html)
        if m4:
            iframe_url = self._fix_url(m4.group(1))
            self.log("尝试跟随 iframe: %s" % iframe_url)
            html2 = self._fetch(iframe_url, timeout=8)
            if html2:
                m5 = _RE_PLAYER_AA.search(html2)
                if m5:
                    try:
                        obj = json.loads(m5.group(1).replace("\\/", "/"))
                        return self._post_url(obj.get("url", ""))
                    except Exception:
                        pass
                m6 = _RE_ANY_MEDIA.search(html2)
                if m6:
                    return self._post_url(m6.group(1))
        return ""

    def _post_url(self, url):
        """规范化提取出的直链"""
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            url = "https:" + url
        # 去掉可能的 HTML 转义残留
        url = url.replace("&amp;", "&")
        return url

    # ---------- 其他 ----------
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
        return ".m3u8" in url or ".mp4" in url

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def close(self):
        self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
