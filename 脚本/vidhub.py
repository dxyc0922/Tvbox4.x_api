# coding=utf-8
"""
Vidhub视频库 vidhub.tv | TVBox Python 爬虫
网站结构 (MacCMS 自定义 mx 模板) :
  - 分类聚合页 /vodtype/{id}.html(无分页), 真正片库列表 /vodshow/{id}-{地区}-{排序}-{类型}-{语言}-{字母}---{页码}---{年份}.html
  - 详情页 /voddetail/{id}.html, 播放页 /vodplay/{id}-{sid}-{nid}.html
  - 播放页内 iframe /player/?u=... , 其返回页 var config={"url": 真实 m3u8} 明文
  - 搜索结果页有验证码, 改用 MacCMS 官方 JSON 接口 /index.php/ajax/suggest?mid=1&wd=&limit=
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
                print("[vidhub]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://vidhub.tv"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/mxstatic/image/logo2.png"

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

# 主导航(真实 tid)
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "连续剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
]

_YEARS = [{"n": "全部", "v": ""}] + \
         [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]

_SORTS = [
    {"n": "最新", "v": "time"},
    {"n": "人气", "v": "hits"},
    {"n": "评分", "v": "score"},
]

_LETTERS = [{"n": "全部", "v": ""}] + \
           [{"n": x, "v": x} for x in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] + \
           [{"n": "0-9", "v": "0-9"}]

# 筛选字典，按照真实网页结构精确构建
_AREAS_ALL = ["大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国", "德国", "泰国", "印度", "意大利", "西班牙", "加拿大", "其他"]
_LANGS_ALL = ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "法语", "德语", "其它", "汉语普通话"]

# 电影分类的子类别 (映射真实的type_id)
_CLASS_MAP_MOVIE = {
    "动作片": "6", "喜剧片": "7", "爱情片": "8", "科幻片": "9", "恐怖片": "10", 
    "剧情片": "11", "战争片": "12", "犯罪片": "20", "惊悚片": "21", "冒险片": "22", 
    "悬疑片": "23", "武侠片": "25", "奇幻片": "26", "纪录片": "30", "动画电影": "27"
}

# 剧集分类的子类别 (映射真实的type_id)
_SUB_CLASS_MAP_TV = {
    "内地剧": "13", "港台剧": "14", "日韩剧": "15", "欧美剧": "16", "泰国剧": "28", "短剧": "29"
}

# 综艺分类的子类别 (映射真实的type_id，此处假设根据综艺页面的类型，如果选访谈，真实分类ID应为3本身，因为在源码里综艺是总分类，访谈是子参数。但为了安全，我们直接使用参数3)
# 在源码中，/vodshow/3---访谈--------2026.html 证明了综艺的总分类ID是3，访问它需要3，而类型是访谈
_CLASS_MAP_VARIETY = ["选秀", "情感", "访谈", "播报", "旅游", "音乐", "美食", "纪实", "曲艺", "生活", "游戏互动", "财经", "求职"]

# 动漫分类的子类别 (映射真实的type_id，同理，动漫总分类是4，子类型是参数)
_CLASS_MAP_ANIME = ["情感", "科幻", "热血", "推理", "搞笑", "冒险", "萝莉", "校园", "动作", "机战", "运动", "战争", "少年", "少女", "社会", "原创", "亲子", "益智", "励志", "其他"]

def _opt(values):
    return [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in values]


FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    filters = []
    
    if tid == "1":  # 电影
        filters.append({"key": "subtype", "name": "电影类型", "value": _opt(list(_CLASS_MAP_MOVIE.keys()))})
        filters.append({"key": "area", "name": "地区", "value": _opt(_AREAS_ALL)})
        filters.append({"key": "lang", "name": "语言", "value": _opt(_LANGS_ALL)})
    elif tid == "2":  # 连续剧
        filters.append({"key": "subtype", "name": "剧集分类", "value": _opt(list(_SUB_CLASS_MAP_TV.keys()))})
        filters.append({"key": "area", "name": "地区", "value": _opt(["内地", "韩国", "香港", "台湾", "日本", "美国", "泰国", "英国", "新加坡", "其他"])})
        filters.append({"key": "lang", "name": "语言", "value": _opt(_LANGS_ALL)})
    elif tid == "3":  # 综艺
        filters.append({"key": "class", "name": "类型", "value": _opt(_CLASS_MAP_VARIETY)})
        filters.append({"key": "area", "name": "地区", "value": _opt(["内地", "港台", "日韩", "欧美"])})
        filters.append({"key": "lang", "name": "语言", "value": _opt(_LANGS_ALL)})
    elif tid == "4":  # 动漫
        filters.append({"key": "class", "name": "类型", "value": _opt(_CLASS_MAP_ANIME)})
        filters.append({"key": "area", "name": "地区", "value": _opt(["国产", "日本", "欧美", "其他"])})
        filters.append({"key": "lang", "name": "语言", "value": _opt(_LANGS_ALL)})
        
    filters.extend([
        {"key": "letter", "name": "字母", "value": _LETTERS},
        {"key": "year", "name": "年份", "value": _YEARS},
        {"key": "sort", "name": "排序", "value": _SORTS},
    ])
    FILTERS[tid] = filters


# ===================== 正则 =====================
_RE_ITEM_START = re.compile(r'<div class="module-item">')
_RE_DETAIL_HREF = re.compile(
    r'<div class="module-item-pic">\s*<a[^>]*href="(/voddetail/\d+\.html)"[^>]*'
    r'(?:title="([^"]*)")?', re.S)
_RE_IMG = re.compile(r'<img[^>]*?(?:data-src|data-original|src)="([^"]+)"', re.S)
_RE_TITLEBOX = re.compile(
    r'<div class="module-item-titlebox">\s*<a[^>]*title="([^"]*)"', re.S)
_RE_REMARK = re.compile(r'<div class="module-item-text">([^<]*)</div>', re.S)

# 详情
_RE_H1 = re.compile(r'<h1[^>]*class="page-title"[^>]*>(.*?)</h1>', re.S | re.I)
_RE_TITLE_GEN = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S | re.I)
_RE_COVER = re.compile(r'<div class="video-cover">[\s\S]{0,800}?<img[^>]*?'
                       r'(?:data-src|data-original|src)="([^"]+)"', re.S)
_RE_OG_IMG = re.compile(r'property="og:image"[^>]*content="([^"]+)"', re.I)
_RE_INFO_ITEM = re.compile(
    r'<span class="video-info-itemtitle">([^<]*)：</span>'
    r'<div class="video-info-item[^"]*">(.*?)</div></div>', re.S)
_RE_META_DESC = re.compile(
    r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', re.I)
_RE_AUX = re.compile(r'class="video-info-aux[^"]*"[^>]*>(.*?)</div>\s*</div>',
                     re.S)
_RE_TAB_ITEM = re.compile(
    r'<div class="module-tab-item tab-item"[^>]*data-dropdown-value="([^"]+)"',
    re.S)
_RE_GLIST_HEAD = re.compile(r'id="glist-(\d+)"')
_RE_EP = re.compile(
    r'<a[^>]*href="(/vodplay/(\d+)-(\d+)-(\d+)\.html)"[^>]*>(.*?)</a>', re.S)

# 播放页 iframe
_RE_IFRAME = re.compile(r'<iframe[^>]*id="player_if"[^>]*src="([^"]+)"', re.I)
# /player/ 页 config
_RE_CONFIG_URL = re.compile(r'"url"\s*:\s*"([^"]+)"')


def _parse_config_url(raw):
    if not raw:
        return ""
    s = raw.strip()
    m = re.search(r'var\s+config\s*=\s*(\{.*?\})\s*;', s, re.S)
    target = m.group(1) if m else s
    target = target.replace('\\/', '/')
    mm = _RE_CONFIG_URL.search(target)
    return mm.group(1) if mm else ""


class Spider(Spider):

    def getName(self):
        return "Vidhub视频库"

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
            "Upgrade-Insecure-Requests": "1",
        }
        self.default_pic = DEFAULT_PIC
        self._play_cache = {}
        self.log("init: site=%s" % self.site_url)

    def _fetch(self, url, timeout=30, headers=None, encoding="utf-8"):
        try:
            h = dict(self.headers)
            if headers:
                h.update(headers)
            rsp = self.fetch(url, headers=h, timeout=timeout)
            if hasattr(rsp, "apparent_encoding") and rsp.apparent_encoding:
                try:
                    rsp.encoding = rsp.apparent_encoding
                except Exception:
                    pass
            if hasattr(rsp, "text"):
                return rsp.text or ""
            if hasattr(rsp, "content"):
                return rsp.content.decode(encoding, "ignore")
            return str(rsp)
        except Exception as e:
            self.log("fetch FAIL %s -> %s" % (url, e))
            return ""

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
        s = re.sub(r"<[^>]+>", "", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
        s = re.sub(r"&#(\d+);",
                   lambda m: chr(int(m.group(1)))
                   if int(m.group(1)) < 0x110000 else m.group(0), s)
        s = re.sub(r"&#x([0-9a-fA-F]+);",
                   lambda m: chr(int(m.group(1), 16))
                   if int(m.group(1), 16) < 0x110000 else m.group(0), s)
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    def _extract_videos(self, html):
        videos = []
        seen = set()
        if not html:
            return videos
        starts = [m.start() for m in _RE_ITEM_START.finditer(html)]
        for idx, st in enumerate(starts):
            ed = starts[idx + 1] if idx + 1 < len(starts) else st + 4000
            block = html[st:ed]

            mh = _RE_DETAIL_HREF.search(block)
            if not mh:
                continue
            href = mh.group(1)
            if href in seen:
                continue
            seen.add(href)

            name = ""
            mt = _RE_TITLEBOX.search(block)
            if mt:
                name = self._clean(mt.group(1))
            if not name and mh.group(2):
                name = self._clean(mh.group(2))
            if not name:
                mi = _RE_IMG.search(block)
                if mi:
                    name = self._clean(mi.group(0))

            pic = ""
            mi = _RE_IMG.search(block)
            if mi:
                pic = mi.group(1)
            if "bkimg.cdn.bcebos.com" in pic or "loading" in pic:
                pic = ""
                mm = re.search(r'data-src="([^"]+)"', block)
                if mm:
                    pic = mm.group(1)

            remark = ""
            mr = _RE_REMARK.search(block)
            if mr:
                remark = self._clean(mr.group(1))

            videos.append({
                "vod_id": href,
                "vod_name": name[:100] or href,
                "vod_pic": self._fix_url(pic) or self.default_pic,
                "vod_remarks": remark,
            })
        return videos

    def _max_page(self, html):
        nums = []
        for u in re.findall(r'/vodshow/([^"#\s]+\.html)', html):
            core = u[:-5] if u.endswith('.html') else u
            parts = core.split('-')
            if len(parts) >= 12 and parts[8].isdigit():
                nums.append(int(parts[8]))
        return max(nums) if nums else 1

    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        html = self._fetch(self.site_url + "/")
        videos = self._extract_videos(html)
        return {"list": videos}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        extend = extend or {}

        # --- 智能替换：如果选定了具体的子类型，将主分类ID转换为真实ID ---
        real_tid = str(tid)
        
        if tid == "1" and extend.get("subtype"):
            # 电影的主分类是1，如果选了具体类型，则替换ID
            real_tid = _CLASS_MAP_MOVIE.get(extend["subtype"], "1")
        elif tid == "2" and extend.get("subtype"):
            # 连续剧的主分类是2，如果选了具体类型，则替换ID
            real_tid = _SUB_CLASS_MAP_TV.get(extend["subtype"], "2")
        elif tid == "3" and extend.get("class"):
            # 综艺的主分类是3，类型是参数，不需要替换ID
            real_tid = "3"
        elif tid == "4" and extend.get("class"):
            # 动漫的主分类是4，类型是参数，不需要替换ID
            real_tid = "4"

        # --- 12段 URL 构造 ---
        # [TID] - [地区] - [排序] - [类型] - [语言] - [字母] - [空] - [空] - [页码] - [空] - [空] - [年份]
        seg = [""] * 12
        seg[0] = real_tid
        
        if extend.get("area"):
            seg[1] = urllib.parse.quote(extend["area"])
        if extend.get("sort"):
            seg[2] = extend["sort"]
            
        # 如果选了电影的子类型，因为我们已经替换了ID，所以参数3留空；否则填class（综艺/动漫用）
        if extend.get("class"):
            seg[3] = urllib.parse.quote(extend["class"])
            
        if extend.get("lang"):
            seg[4] = urllib.parse.quote(extend["lang"])
        if extend.get("letter"):
            seg[5] = urllib.parse.quote(extend["letter"])
            
        seg[8] = str(page)
        
        if extend.get("year"):
            seg[11] = str(extend["year"])

        path = "/vodshow/%s.html" % "-".join(seg)
        url = self.site_url + path
        self.log("category: %s" % url)
        html = self._fetch(url)
        videos = self._extract_videos(html)
        pagecount = self._max_page(html)
        self.log("  列表 %d 条, pagecount=%d" % (len(videos), pagecount))
        return {
            "list": videos, "page": page, "pagecount": pagecount,
            "limit": 72, "total": pagecount * 72,
        }

    def _suggest(self, wd, limit=100):
        url = ("%s/index.php/ajax/suggest?mid=1&wd=%s&limit=%d"
               % (self.site_url, urllib.parse.quote(wd), limit))
        txt = self._fetch(url, headers={"X-Requested-With": "XMLHttpRequest"})
        try:
            data = json.loads(txt)
        except Exception:
            return []
        out = []
        for it in (data.get("list") or []):
            pic = it.get("pic") or ""
            out.append({
                "vod_id": "/voddetail/%s.html" % it.get("id"),
                "vod_name": it.get("name") or str(it.get("id")),
                "vod_pic": self._fix_url(pic) or self.default_pic,
                "vod_remarks": "",
            })
        return out

    def searchContent(self, key, quick, pg="1"):
        videos = self._suggest(key)
        self.log("search '%s' -> %d 条" % (key, len(videos)))
        return {"list": videos, "page": 1, "pagecount": 1,
                "limit": len(videos) or 1, "total": len(videos)}

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        html = self._fetch(url)
        if not html:
            return {"list": []}

        name = ""
        m = _RE_H1.search(html)
        if m:
            name = self._clean(m.group(1))
        if not name:
            m = _RE_TITLE_GEN.search(html)
            if m:
                name = self._clean(m.group(1))
        if not name:
            m = re.search(r"<title>(.*?)</title>", html, re.S)
            if m:
                name = self._clean(
                    re.split(r"[-_|]", m.group(1))[0]).strip("《》 ")
        name = name or vod_id

        pic = self.default_pic
        m = _RE_COVER.search(html)
        if m:
            pic = self._fix_url(m.group(1))
        if not pic or pic == self.default_pic:
            m = _RE_OG_IMG.search(html)
            if m:
                pic = self._fix_url(m.group(1))

        director = actor = year = area = type_name = remarks = ""
        content = ""
        for label, body in _RE_INFO_ITEM.findall(html):
            label = label.strip()
            if label in ("剧情", "简介"):
                c = re.sub(r'<a[^>]*>.*?</a>', "", body, flags=re.S)
                c = self._clean(c)
                if c:
                    content = c
                continue
            text = self._clean(body)
            text = re.sub(r"^[/\s]+", "", text)
            text = re.sub(r"\s*/\s*", ", ", text).strip(" /,，")
            if label == "导演":
                director = text
            elif label == "主演":
                actor = text
            elif label in ("上映", "年份"):
                if not year:
                    year = text
            elif label == "地区":
                area = text
            elif label == "类型":
                if not type_name:
                    type_name = text
            elif label == "备注":
                remarks = text

        my = re.search(r"(?:19|20)\d{2}", year)
        year = my.group(0) if my else ""

        maux = _RE_AUX.search(html)
        if maux:
            aux_types, aux_area = [], ""
            for href, txt in re.findall(
                    r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    maux.group(1), re.S):
                t = self._clean(txt)
                if not t or "/vodshow/" not in href:
                    continue
                core = href.split("/vodshow/")[-1].replace(".html", "")
                p = core.split("-")
                if len(p) >= 12:
                    if p[3]:
                        aux_types.append(urllib.parse.unquote(p[3]))
                    if p[1] and not aux_area:
                        aux_area = urllib.parse.unquote(p[1])
                    if p[11] and not year:
                        year = p[11]
            if not type_name and aux_types:
                subs = [x for x in aux_types if x not in
                        ("电影", "连续剧", "电视剧", "综艺", "动漫", "动画")]
                type_name = ",".join(subs or aux_types)
            if not area and aux_area:
                area = aux_area

        if not content or content in ("内详", "暂无"):
            m = _RE_META_DESC.search(html)
            if m:
                dc = self._clean(m.group(1))
                if dc and "为您提供" not in dc:
                    content = dc
        if content and content not in ("内详", "暂无"):
            vod_content = INTRO_PREFIX + "\n" + content
        else:
            vod_content = INTRO_PREFIX

        tab_names = [self._clean(x) for x in _RE_TAB_ITEM.findall(html)]
        heads = [(m.start(), int(m.group(1)))
                 for m in _RE_GLIST_HEAD.finditer(html)]
        groups = {}
        for idx, (st, sid) in enumerate(heads):
            ed = heads[idx + 1][0] if idx + 1 < len(heads) else st + 200000
            seg = html[st:ed]
            eps = []
            seen_ep = set()
            for em in _RE_EP.finditer(seg):
                ep_vid, ep_sid, ep_nid = em.group(2), em.group(3), em.group(4)
                if int(ep_sid) != sid:
                    continue
                ep_href = em.group(1)
                if ep_href in seen_ep:
                    continue
                seen_ep.add(ep_href)
                ep_name = self._clean(em.group(5)) or ("第%s集" % ep_nid)
                eps.append((ep_name, self._fix_url(ep_href)))
            if eps:
                groups[sid] = eps

        play_from, play_url = [], []
        for idx, sid in enumerate(sorted(groups.keys())):
            line = (tab_names[idx] if idx < len(tab_names)
                    else "线路%d" % sid)
            eps = groups[sid]
            play_from.append(line)
            play_url.append("#".join("%s$%s" % (n, h) for n, h in eps))

        vod_remarks = remarks or ("%d条线路" % len(groups))

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic or self.default_pic,
            "vod_content": vod_content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_year": year,
            "vod_area": area,
            "vod_type": type_name,
            "vod_remarks": vod_remarks,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    def playerContent(self, flag, id, vipFlags):
        play_page = id if str(id).startswith("http") else self._fix_url(id)
        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600:
                return res

        res = {"parse": 1, "playUrl": "", "url": play_page,
               "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}

        html = self._fetch(play_page)
        iframe = ""
        if html:
            m = _RE_IFRAME.search(html)
            if m:
                iframe = m.group(1).replace("&amp;", "&")

        if iframe:
            iframe_url = self._fix_url(iframe)
            sub = self._fetch(
                iframe_url,
                headers={"Referer": play_page,
                         "Accept": "text/html,application/xhtml+xml,*/*"})
            real = _parse_config_url(sub)
            if real:
                real = real.replace("\\/", "/")
                real = urllib.parse.unquote(real)
                if real.startswith("http"):
                    res = {
                        "parse": 0,
                        "playUrl": "",
                        "url": real,
                        "header": {
                            "User-Agent": UA,
                            "Referer": self.site_url + "/",
                        },
                    }
        self._play_cache[play_page] = (now, res)
        return res


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
