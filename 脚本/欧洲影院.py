# coding=utf-8
"""
欧洲影院 51shuoshuo.com | TVBox Python 爬虫 
关键:
  - 列表页(vod_remarks): 彻底解决副标题抓不到的问题，使用卡片级切割
  - 详情页(vod_content): 分类/地区/年份强制排版到简介开头，完美契合原生网页
  - 详情页(vod_remarks): 全局兜底状态文字
  - 独立分离：电影、电视剧、综艺、动漫、短剧的筛选参数
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
                print("[51shuoshuo]", *a)
            except Exception:
                pass

    Spider = _BaseSpider

HOST = "https://www.51shuoshuo.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/template/ewave-orange/images/load.gif"
INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

CLASSES = [
    {"type_id": "1",  "type_name": "电影"},
    {"type_id": "2",  "type_name": "电视剧"},
    {"type_id": "3",  "type_name": "综艺片"},
    {"type_id": "4",  "type_name": "动漫"},
    {"type_id": "24", "type_name": "短剧"},
]

_SUB_CLASS = {
    "1": [("全部", ""), ("动作片", "6"), ("喜剧片", "7"), ("爱情片", "8"), ("科幻片", "9"), ("剧情片", "10"), ("战争片", "11"), ("动画片", "41"), ("记录片", "12"), ("恐怖片", "39")],
    "2": [("全部", ""), ("国产剧", "13"), ("香港剧", "14"), ("韩国剧", "15"), ("欧美剧", "16"), ("台湾剧", "22"), ("日本剧", "21"), ("泰国剧", "20"), ("海外剧", "23")],
    "3": [("全部", ""), ("大陆综艺", "25"), ("日韩综艺", "26"), ("港台综艺", "27"), ("欧美综艺", "28")],
    "4": [("全部", ""), ("国产动漫", "29"), ("日本动漫", "30"), ("港台动漫", "42"), ("欧美动漫", "31"), ("海外动漫", "43")],
    "24": [("全部", ""), ("短剧大全", "40"), ("AI漫剧", "44")],
}

# ================= 完美还原所有频道的独立筛选 =================

# 电影
_GENRES_MOVIE = ["全部", "喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争", "警匪", "犯罪", "动画", "奇幻", "武侠", "冒险", "枪战", "悬疑", "惊悚", "经典", "青春", "文艺", "微电影", "古装", "历史", "运动", "农村", "儿童", "网络电影"]
_LANGS_MOVIE  = ["全部", "国语", "英语", "粤语", "闽南语", "韩语", "日语", "法语", "德语", "其它"]
_AREAS_MOVIE  = ["全部", "大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国", "德国", "泰国", "印度", "意大利", "西班牙", "加拿大", "其他"]

# 电视剧
_GENRES_TV    = ["全部", "古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作", "奇幻", "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他"]
_LANGS_TV     = ["全部", "国语", "英语", "粤语", "闽南语", "韩语", "日语", "其它"]
_AREAS_TV     = ["全部", "内地", "韩国", "香港", "台湾", "日本", "美国", "泰国", "英国", "新加坡", "其他"]

# 综艺
_GENRES_SHOW  = ["全部", "选秀", "情感", "访谈", "播报", "旅游", "音乐", "美食", "纪实", "曲艺", "生活", "游戏互动", "财经", "求职"]
_LANGS_SHOW   = ["全部", "国语", "英语", "粤语", "闽南语", "韩语", "日语", "其它"]
_AREAS_SHOW   = ["全部", "内地", "港台", "日韩", "欧美"]

# 动漫
_GENRES_ANIME = ["全部", "情感", "科幻", "热血", "推理", "搞笑", "冒险", "萝莉", "校园", "动作", "机战", "运动", "战争", "少年", "少女", "社会", "原创", "亲子", "益智", "励志", "其他"]
_LANGS_ANIME  = ["全部", "国语", "英语", "粤语", "闽南语", "韩语", "日语", "其它"]
_AREAS_ANIME  = ["全部", "国产", "日本", "欧美", "其他"]

# 短剧
_GENRES_DUANJU = ["全部", "爱情", "动作", "喜剧", "战争", "科幻", "剧情", "武侠", "冒险", "枪战", "恐怖", "微电影", "其它"]
_LANGS_DUANJU  = ["全部", "国语", "英语", "粤语", "闽南语", "韩语", "日语", "法语", "德语", "其它"]
_AREAS_DUANJU  = ["全部", "大陆", "香港", "台湾", "美国", "韩国", "日本", "泰国", "新加坡", "马来西亚", "印度", "英国", "法国", "加拿大", "西班牙", "俄罗斯", "其它"]

_YEARS = [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]
_LETTERS = ["全部"] + [chr(i) for i in range(65, 91)]
_SORTS = [{"n": "最近更新", "v": "time"}, {"n": "最多播放", "v": "hits"}, {"n": "最好评", "v": "score"}]

FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    
    if tid == "1":
        g_list, l_list, a_list = _GENRES_MOVIE, _LANGS_MOVIE, _AREAS_MOVIE
    elif tid == "2":
        g_list, l_list, a_list = _GENRES_TV, _LANGS_TV, _AREAS_TV
    elif tid == "3":
        g_list, l_list, a_list = _GENRES_SHOW, _LANGS_SHOW, _AREAS_SHOW
    elif tid == "4":
        g_list, l_list, a_list = _GENRES_ANIME, _LANGS_ANIME, _AREAS_ANIME
    else: # 24 短剧
        g_list, l_list, a_list = _GENRES_DUANJU, _LANGS_DUANJU, _AREAS_DUANJU

    FILTERS[tid] = [
        {"key": "class", "name": "分类", "value": [{"n": n, "v": v} for n, v in _SUB_CLASS.get(tid, [("全部", "")])]},
        {"key": "area",  "name": "地区", "value": [{"n": a, "v": "" if a=="全部" else a} for a in a_list]},
        {"key": "genre", "name": "剧情", "value": [{"n": g, "v": "" if g=="全部" else g} for g in g_list]},
        {"key": "lang",  "name": "语言", "value": [{"n": l, "v": "" if l=="全部" else l} for l in l_list]},
        {"key": "year",  "name": "年份", "value": _YEARS},
        {"key": "letter","name": "字母", "value": [{"n": l, "v": "" if l=="全部" else l} for l in _LETTERS]},
        {"key": "by",    "name": "排序", "value": _SORTS},
    ]

# ===================== 正则 =====================
_RE_CARD = re.compile(
    r'<a\s+href="(/p/\d+\.html)"\s+title="([^"]*)"[^>]*>'
    r'[\s\S]{0,300}?(?:data-original|data-src|src)="([^"]*)"', re.S | re.I)
_RE_CARD_STATUS = re.compile(r'<p class="[^"]*item-status[^"]*">([^<]*)</p>', re.I)

_RE_PAGE_NUM = re.compile(r'num">(\d+)/(\d+)<')
_RE_H3_TITLE = re.compile(r'<h3[^>]*>\s*<a[^>]*>([\s\S]*?)</a>', re.I)
_RE_PIC = re.compile(r'<div class="pic">[\s\S]{0,200}?(?:data-original|data-src|src)="([^"]+)"', re.I)

# 详情元信息
_RE_META_BLOCK = re.compile(r'<p class="row">([\s\S]*?)</p>', re.I)
_RE_CAT = re.compile(r'分类：([\s\S]*?)</span>', re.I)
_RE_AREA = re.compile(r'地区：<a[^>]*>([^<]+)</a>', re.I)
_RE_YEAR = re.compile(r'年份：<a[^>]*>([^<]+)</a>', re.I)
_RE_DIR = re.compile(r'导演：([^<]+)', re.I)
_RE_ACT = re.compile(r'主演：([^<]+)', re.I)
_RE_STAT = re.compile(r'状态：([^<\s]+)', re.I)

# 简介多级兜底
_RE_INTRO_LONG = re.compile(r'<h2>[^<]*?(?:剧情|简介)[^<]*?</h2>[\s\S]{0,300}?<p[^>]*>([\s\S]*?)</div>', re.I)
_RE_INTRO_SHORT = re.compile(r'<div class="text text-row[^"]*">\s*简介：([\s\S]*?)</div>', re.I)

# 剧集列表
_RE_TAB = re.compile(r'<li class="[^"]*ewave-tab[^"]*"\s+data-target="#ewave-playlist-(\d+)">\s*([^<]*?)\s*<em>', re.I)
_RE_PLAYLIST_UL = re.compile(r'<ul[^>]*id="ewave-playlist-(\d+)"[^>]*>([\s\S]*?)</ul>', re.I)
_RE_EP_A = re.compile(r'<a[^>]*href="(/player/\d+/\d+/\d+\.html)"[^>]*>([^<]*)</a>', re.I)
_RE_PLAYER = re.compile(r'var\s+player_aaaa\s*=\s*(\{[\s\S]*?\});?\s*</script>', re.I)


class Spider(Spider):

    def getName(self):
        return "欧洲影院"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}

        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": self.site_url + "/",
        }
        self.default_pic = DEFAULT_PIC
        self._play_cache = {}
        self.log("init: site=%s" % self.site_url)

    def _fetch(self, url, timeout=30, headers=None):
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
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    def _extract_videos(self, html):
        videos, seen = [], set()
        if not html: return videos
        
        blocks = re.split(r'<li[^>]*>', html)
        for block in blocks:
            m_card = _RE_CARD.search(block)
            if m_card:
                href, title, pic = m_card.groups()
                href = href.replace("&amp;", "&")
                if href in seen: continue
                seen.add(href)
                
                remarks = ""
                m_st = _RE_CARD_STATUS.search(block)
                if m_st:
                    remarks = self._clean(m_st.group(1))
                
                videos.append({
                    "vod_id":      href,
                    "vod_name":    self._clean(title)[:100],
                    "vod_pic":     self._fix_url(pic) or self.default_pic,
                    "vod_remarks": remarks,
                })
        return videos

    def _page_count(self, html):
        m = _RE_PAGE_NUM.search(html or "")
        if m:
            try: return int(m.group(2))
            except Exception: pass
        return 1

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

        def _v(k):
            v = extend.get(k)
            return "" if v in ("", None, "全部") else v

        area, cls, by, year = _v("area"), _v("class"), _v("by") or "time", _v("year")
        genre, lang, letter = _v("genre"), _v("lang"), _v("letter")

        cat_id = tid
        if cls:
            if cls.isdigit(): cat_id = cls
            else:
                for n, v in _SUB_CLASS.get(tid, []):
                    if v and (cls == n or cls == v):
                        cat_id = v
                        break

        seg = ["set"]
        if area:   seg += ["area", urllib.parse.quote(area)]
        if genre:  seg += ["class", urllib.parse.quote(genre)]
        if by:     seg += ["by", by]
        seg += ["id", cat_id]
        if lang:   seg += ["lang", urllib.parse.quote(lang)]
        if letter: seg += ["letter", letter]
        if page > 1: seg += ["page", str(page)]
        if year:   seg += ["year", str(year)]
        
        url = self.site_url + "/" + "/".join(seg) + ".html"
        self.log("category: %s" % url)
        html = self._fetch(url)
        
        return {
            "list": self._extract_videos(html), 
            "page": page, 
            "pagecount": self._page_count(html),
            "limit": 24, 
            "total": 9999,
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        url = "%s/scan2.html?wd=%s" % (self.site_url, urllib.parse.quote(key))
        if page > 1: url += "&page=%d" % page
        html = self._fetch(url)
        return {
            "list": self._extract_videos(html), "page": page,
            "pagecount": self._page_count(html), "limit": 24, "total": 999
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    def detailContent(self, ids):
        if not ids: return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        html = self._fetch(url)
        if not html: return {"list": []}

        # 标题
        name = ""
        m = _RE_H3_TITLE.search(html)
        if m: name = self._clean(m.group(1))
        if not name:
            m = re.search(r"<title>(.*?)</title>", html, re.S)
            if m: name = self._clean(m.group(1).split("_")[0].split("-")[0])
        name = re.sub(r"\s*\(\d{4}\)\s*$", "", name).strip() or vod_id

        # 封面
        pic = self.default_pic
        m = _RE_PIC.search(html)
        if m: pic = self._fix_url(m.group(1)) or self.default_pic

        # 提取元信息
        meta_html = _RE_META_BLOCK.search(html)
        target_html = meta_html.group(1) if meta_html else html

        c_text, a_text, y_text = "", "", ""
        d_text, act_text, s_text = "", "", ""
        
        m = _RE_CAT.search(target_html)
        if m: c_text = " ".join(re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1)))
        m = _RE_AREA.search(target_html)
        if m: a_text = self._clean(m.group(1))
        m = _RE_YEAR.search(target_html)
        if m: y_text = self._clean(m.group(1))
        m = _RE_DIR.search(target_html)
        if m: d_text = self._clean(m.group(1))
        m = _RE_ACT.search(target_html)
        if m: act_text = re.sub(r"\s*,\s*", ", ", self._clean(m.group(1)))
        
        # 副标题
        m = _RE_STAT.search(html)
        if m: s_text = self._clean(m.group(1))
        if not s_text:
            m2 = re.search(r'(更新至[^<]+|全\d+集|已完结|HD[^<\s]*)', html)
            if m2: s_text = self._clean(m2.group(1))

        # 简介
        content = ""
        m = _RE_INTRO_LONG.search(html)
        if m: content = self._clean(m.group(1))
        if not content:
            m = _RE_INTRO_SHORT.search(html)
            if m: content = self._clean(m.group(1))
        if not content:
            m = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', html, re.I)
            if m: content = self._clean(m.group(1))
        
        if content:
            content = INTRO_PREFIX + "\n" + content
        else:
            content = INTRO_PREFIX

        # 完美微调版：只拼接地区和年份
        ui_director = d_text
        extra = []
        if a_text: extra.append(a_text)
        if y_text: extra.append(y_text)
        if extra:
            ui_director = f"{ui_director} [{' / '.join(extra)}]" if ui_director else f"[{' / '.join(extra)}]"

        # 剧集线路
        tab_names = {}
        for sid, tname in _RE_TAB.findall(html):
            tab_names[sid] = self._clean(tname) or ("线路%s" % sid)

        groups = {}
        for sid, body in _RE_PLAYLIST_UL.findall(html):
            eps = []
            for href, ep in _RE_EP_A.findall(body):
                href = href.replace("&amp;", "&")
                ep = self._clean(ep) or ("第%d集" % (len(eps) + 1))
                eps.append((ep, href))
            if eps: groups[sid] = eps

        if not groups: return {"list": []}

        ordered_sids = [sid for sid in tab_names.keys() if sid in groups]
        for sid in groups:
            if sid not in ordered_sids: ordered_sids.append(sid)

        play_from, play_url = [], []
        for sid in ordered_sids:
            alias = tab_names.get(sid) or ("线路%s" % sid)
            play_from.append(alias)
            play_url.append("#".join("%s$%s" % (n, h) for n, h in groups[sid]))

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": act_text,
            "vod_director": ui_director,
            "vod_remarks": s_text or ("%d条线路" % len(groups)), 
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url":  "$$$".join(play_url),
        }]}

    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600: return res

        html = self._fetch(play_page)
        m3u8 = ""
        if html:
            m = _RE_PLAYER.search(html)
            if m:
                try:
                    aa = json.loads(m.group(1))
                    if int(aa.get("encrypt", 0) or 0) == 0:
                        m3u8 = (aa.get("url", "") or "").replace("\\/", "/")
                except Exception as e:
                    self.log("player_aaaa 解析失败: %s" % e)

        if m3u8:
            res = {"parse": 0, "playUrl": "", "url": m3u8, "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}
            self._play_cache[play_page] = (now, res)
            return res

        res = {"parse": 1, "playUrl": "", "url": play_page, "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}
        self._play_cache[play_page] = (now, res)
        return res

    def localProxy(self, param): return [200, "image/jpeg", b"", ""]
    def isVideoFormat(self, url): return ".m3u8" in url or ".mp4" in url or url.startswith("http")
    def manualVideoCheck(self): return False
    def destroy(self): pass
    def close(self): self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
