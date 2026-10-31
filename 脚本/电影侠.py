# coding=utf-8
"""
电影侠 dyx00.com | TVBox Python 爬虫 
域名: https://www.dyx00.com  (备用跳转 dyxia.app)

站点要点:
  - 列表卡片:  a.v-item  ->  href=/detail/{id}.html
               封面在第二张 <img data-original>，第一张是占位图，必须跳过
               标题在 div.v-item-title，但夹着隐藏的干扰标题（display:none），需过滤
               右上角角标 "豆瓣:x.x分"，底部 span 是备注（HD中字 / 更新至xx集）
  - 影视库:    /show/{ch}-{类型}-{地区}-{语言}-{年份}-{排序}-{页码}.html
               空位必须留空（连续两个 "-"），中文需整段 urlencode
               排序: 1 综合 / 2 最新 / 3 最热 / 4 评分
  - 详情页:    /detail/{id}.html
               标题在 div.detail-title 的多个 <strong> 里，真标题是偶数位
               简介在 div.detail-desc
               线路: div.source-list-box-main 里的 a.source-item（只有线路名，没有 id）
               剧集: div.episode-list（按索引与线路一一对应，非首条带 display:none）
                     每条 a.episode-item -> /play/{id}-{sid}-{nid}.html
               线路与剧集都是靠"顺序"对应的，所以必须按出现顺序配对
  - 播放页:    /play/{id}-{sid}-{nid}.html
               页面内 gogogo() 里直接写死 const playSource = { src: "https://.../index.m3u8?..." }
               纯静态直链，无需二次解析（部分影片 src 为空，此时回退到嗅探播放页）
  - 搜索:      /search?k={关键词}&t={token}
               token 由服务端下发到每个页面的搜索结果链接里（a[href^="/search?k="] 的 t 参数）
               直接请求不带 t 会返回空结果，所以要先抓首页/详情页把 token 缓存下来
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
                print("[dyx00]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


# ===================== 站点常量 =====================
HOST = "https://www.dyx00.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 封面兜底图（站点占位图）
DEFAULT_PIC = "https://vf.wkcyvs.cn/vod_pc_static_dyxia/images/p/logo_placeholder_vertical.png?ver=123456666"

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

# 站点真实导航（/channel/{id}.html）
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "连续剧"},
    {"type_id": "3", "type_name": "动漫"},
    {"type_id": "4", "type_name": "综艺纪录"},
    {"type_id": "6", "type_name": "短剧"},
    # 站点自带的其它聚合页
    {"type_id": "new", "type_name": "今日更新"},
    {"type_id": "rank", "type_name": "排行榜"},
]

# 影视库 /show 的第 2~6 段固定顺序：类型 - 地区 - 语言 - 年份 - 排序 - 页码
# 下面是各频道的静态兜底（与站点 2024 版一致），运行时优先从页面动态抓取
_FILTER_TYPES = {
    "1": ["全部", "剧情", "喜剧", "动作", "爱情", "恐怖", "惊悚", "犯罪", "科幻",
          "悬疑", "奇幻", "冒险", "战争", "历史", "古装", "家庭", "传记", "武侠",
          "歌舞", "短片", "动画", "儿童", "职场"],
    "2": ["全部", "剧情", "爱情", "喜剧", "犯罪", "悬疑", "古装", "动作", "家庭",
          "惊悚", "奇幻", "美剧", "科幻", "历史", "战争", "韩剧", "武侠", "言情",
          "恐怖", "冒险", "都市", "职场"],
    "3": ["全部", "动态漫画", "剧情", "动画", "喜剧", "冒险", "动作", "奇幻", "科幻",
          "儿童", "搞笑", "爱情", "家庭", "短片", "热血", "益智", "悬疑", "经典",
          "校园", "Anime", "运动", "亲子", "青春", "恋爱", "武侠", "惊悚"],
    "4": ["全部", "纪录", "真人秀", "记录", "脱口秀", "剧情", "历史", "喜剧", "传记",
          "相声", "节目", "歌舞", "冒险", "运动", "Season", "犯罪", "短片", "搞笑",
          "晚会"],
    "6": ["全部", "王爷太子", "霸道总裁", "屌丝逆袭", "赘婿系列", "重生系列", "穿越短剧",
          "美女总裁", "娇妻系列", "龙王系列", "都市言情", "逆袭", "甜宠", "虐恋",
          "穿越", "重生", "剧情", "科幻", "武侠", "爱情", "动作", "战争", "冒险", "其它"],
}

# 地区：显示名 -> 站点真实参数（站点界面显示"大陆"，URL 里实际是"中国大陆"！）
_AREA_ITEMS = [("全部", ""), ("大陆", "中国大陆"), ("香港", "中国香港"),
               ("台湾", "中国台湾"), ("美国", "美国"), ("日本", "日本"),
               ("韩国", "韩国"), ("英国", "英国"), ("法国", "法国"),
               ("德国", "德国"), ("印度", "印度"), ("泰国", "泰国"),
               ("丹麦", "丹麦"), ("瑞典", "瑞典"), ("巴西", "巴西"),
               ("加拿大", "加拿大"), ("俄罗斯", "俄罗斯"), ("意大利", "意大利"),
               ("比利时", "比利时"), ("爱尔兰", "爱尔兰"), ("西班牙", "西班牙"),
               ("澳大利亚", "澳大利亚"), ("其他", "其他")]

# 综艺纪录的地区少一些
_AREA_ITEMS_MIN = [("全部", ""), ("大陆", "中国大陆"), ("香港", "中国香港"),
                   ("台湾", "中国台湾"), ("美国", "美国"), ("日本", "日本"),
                   ("韩国", "韩国"), ("其他", "其他")]

_FILTER_LANGS = ["全部", "国语", "粤语", "英语", "日语", "韩语", "法语", "其他"]

_FILTER_YEARS = ["全部"] + [str(y) for y in range(2026, 2019, -1)] + \
                ["10年代", "00年代", "90年代", "80年代", "更早"]

# 年份中文标签 -> 站点真实参数
_YEAR_VALUE = {
    "10年代": "2010_2019", "00年代": "2000_2009", "90年代": "1990_1999",
    "80年代": "1980_1989", "更早": "0_1979",
}

_FILTER_SORTS = [("综合", "1"), ("最新", "2"), ("最热", "3"), ("评分", "4")]

# 动态抓取的筛选缓存 {ch: {...}}
_DYN_FILTERS = {}

# ==========================================================================
# 图片资源域（关键！）
# 站点封面主域 www.dyx00.com/vod1/... 有防盗链（任何直连都是 403 openresty），
# 真实图片走 rdul.js 下发的资源镜像域（window.RDUL），同一 /vod1/ 路径直接 200。
# 实测可用: https://vres.wkcyvs.cn / https://103.39.111.180:51050 / ...:51050
# ==========================================================================
_RDUL_JS = "https://vf.wkcyvs.cn/vod_pc_static_dyxia/js/rdul.js?ver=123456666"
_RDUL_DOMAINS = ["https://vres.wkcyvs.cn",
                 "https://103.39.111.180:51050",
                 "https://103.39.111.184:51050"]
_RDUL_TS = 0
_RDUL_IDX = 0


def _load_rdul(fetch_fn=None):
    """从站点 rdul.js 里刷新图片资源域列表（1 小时一次）"""
    global _RDUL_DOMAINS, _RDUL_TS
    now = time.time()
    if now - _RDUL_TS < 3600 or not _RDUL_DOMAINS:
        return
    if fetch_fn is None:
        return
    try:
        js = fetch_fn(_RDUL_JS, timeout=10)
        domains = re.findall(r'"(https?://[^"]+)"', js or "")
        domains = [d for d in domains if "http" in d]
        if domains:
            _RDUL_DOMAINS = domains
        _RDUL_TS = now
    except Exception:
        _RDUL_TS = now


def _pic_domain():
    global _RDUL_IDX
    return _RDUL_DOMAINS[_RDUL_IDX % len(_RDUL_DOMAINS)]


def _rotate_pic_domain():
    global _RDUL_IDX
    _RDUL_IDX += 1
    return _pic_domain()


def _build_filters():
    out = {}
    for c in CLASSES:
        tid = c["type_id"]
        if tid not in _FILTER_TYPES:
            out[tid] = []
            continue
        has_area = tid != "6"
        out[tid] = [
            {"key": "class", "name": "类型",
             "value": [{"n": x, "v": "" if x == "全部" else x}
                       for x in _FILTER_TYPES[tid]]},
            {"key": "area", "name": "地区",
             "value": [{"n": n, "v": v} for n, v in
                       (_AREA_ITEMS_MIN if tid == "4" else _AREA_ITEMS)]},
            {"key": "lang", "name": "语言",
             "value": [{"n": x, "v": "" if x == "全部" else x}
                       for x in _FILTER_LANGS]},
            {"key": "year", "name": "年份",
             "value": [{"n": x, "v": _YEAR_VALUE.get(x, "" if x == "全部" else x)}
                       for x in _FILTER_YEARS]},
            {"key": "sort", "name": "排序",
             "value": [{"n": n, "v": v} for n, v in _FILTER_SORTS]},
        ]
        if not has_area:
            # 短剧频道只有 类型/排序 两个维度
            out[tid] = [
                {"key": "class", "name": "类型",
                 "value": [{"n": x, "v": "" if x == "全部" else x}
                           for x in _FILTER_TYPES[tid]]},
                {"key": "sort", "name": "排序",
                 "value": [{"n": n, "v": v} for n, v in _FILTER_SORTS[:3]]},
            ]
    return out


FILTERS = _build_filters()


# ===================== 正则 =====================
# 卡片：<a href="/detail/xxx.html" class="v-item"> ... </a>（section 级）
_RE_CARD_BLOCK = re.compile(
    r'<a\s+href="(/detail/\d+\.html)"\s+class="v-item"[^>]*>([\s\S]*?)</a>\s*</div>',
    re.I)
# 搜索结果块：<a href="/detail/xxx.html" class="search-result-item"> ... </a>
_RE_SEARCH_BLOCK = re.compile(
    r'<a\s+href="(/detail/\d+\.html)"\s+class="search-result-item"[^>]*>([\s\S]*?)</a>',
    re.I)
# 排行榜行：<a href="/detail/xxx.html" class="rank-row">
_RE_RANK_BLOCK = re.compile(
    r'<a\s+href="(/detail/\d+\.html)"\s+class="rank-row"[^>]*>([\s\S]*?)</a>',
    re.I)

_RE_IMG_TAG = re.compile(r'<img\b[^>]*>', re.I)
_RE_DATA_ORIGINAL = re.compile(r'data-original="([^"]+)"', re.I)
_RE_SRC = re.compile(r'\bsrc="([^"]+)"', re.I)
_RE_NONE_COVER = re.compile(r'id="noneCoverImg"', re.I)

# 标题：<div class="v-item-title">xxxx</div>，需要剔除 style="display: none" 的干扰项
_RE_TITLE_DIV = re.compile(
    r'<div\s+class="v-item-title"([^>]*)>([\s\S]*?)</div>', re.I)
_RE_STYLE_HIDE = re.compile(r'display\s*:\s*none', re.I)

_RE_CARD_SCORE = re.compile(r'豆瓣[::]\s*([\d.]+)\s*分', re.I)
_RE_CARD_REMARK = re.compile(
    r'<div\s+class="v-item-bottom"[^>]*>\s*<span>\s*([\s\S]*?)\s*</span>', re.I)

# 搜索
_RE_SEARCH_TITLE = re.compile(r'<div\s+class="title"[^>]*>([\s\S]*?)</div>', re.I)
_RE_SEARCH_CAT = re.compile(
    r'<div\s+class="search-result-item-header"[^>]*>\s*<div>\s*([\s\S]*?)\s*</div>',
    re.I)
# 搜索结果链接里带的校验 token
_RE_SEARCH_TOKEN = re.compile(
    r'href="/search\?k=[^"]*?&amp;t=([^"&]+)"', re.I)
_RE_SEARCH_TOKEN2 = re.compile(
    r'href="/search\?k=[^"]*?&t=([^"&]+)"', re.I)

# 分页
_RE_HAS_NEXT = re.compile(r'class="page-item-next"', re.I)

# 详情页
_RE_DETAIL_TITLE = re.compile(
    r'<div\s+class="detail-title"[^>]*>([\s\S]*?)</div>', re.I)
_RE_STRONG = re.compile(r'<strong[^>]*>([\s\S]*?)</strong>', re.I)
_RE_DETAIL_PIC = re.compile(
    r'<div\s+class="detail-pic"[^>]*>[\s\S]{0,400}?data-original="([^"]+)"', re.I)
_RE_DETAIL_DESC = re.compile(
    r'<div\s+class="detail-desc"[^>]*>([\s\S]*?)</div>', re.I)
_RE_INFO_ROW = re.compile(
    r'<div\s+class="detail-info-row-side">\s*([^<:：]+)[::]\s*</div>\s*'
    r'<div\s+class="detail-info-row-main">([\s\S]*?)</div>\s*</div>', re.I)

# 线路 / 剧集（严格按顺序配对）
_RE_SOURCE_ITEM = re.compile(
    r'<a\s+href="[^"]*"\s+class="source-item[^"]*"[^>]*>([\s\S]*?)</a>', re.I)
_RE_SOURCE_LABEL = re.compile(
    r'<span\s+class="source-item-label"[^>]*>([\s\S]*?)</span>', re.I)
_RE_SOURCE_SUB = re.compile(
    r'<span\s+class="source-item-sublabel"[^>]*>([\s\S]*?)</span>', re.I)
_RE_SOURCE_NUM = re.compile(
    r'<i\s+class="source-item-num"[^>]*>\s*(\d+)\s*</i>', re.I)

_RE_EP_ITEM = re.compile(
    r'<a\s+href="(/play/[^"]+\.html)"\s+class="episode-item"[^>]*>([\s\S]*?)</a>',
    re.I)
_RE_SPAN = re.compile(r'<span[^>]*>([\s\S]*?)</span>', re.I)

# 播放页
_RE_PLAY_SRC = re.compile(
    r'const\s+playSource\s*=\s*\{[\s\S]{0,300}?src\s*:\s*"([^"]*)"', re.I)
_RE_PLAY_SRC2 = re.compile(r'src\s*:\s*"(https?://[^"]+\.m3u8[^"]*)"', re.I)

_RE_SITE_TITLE = re.compile(r'<title>([\s\S]*?)</title>', re.I)
_RE_H1 = re.compile(r'<h1[^>]*>([\s\S]*?)</h1>', re.I)
_RE_META_DESC = re.compile(
    r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', re.I)
_RE_SID = re.compile(r'/play/\d+-(\d+)-\d+\.html', re.I)

# 站点水印（详情页标题、列表标题里都会掺杂）
_WATERMARK_WORDS = ("kekys", "可可影视", "dyxia", "dyx00", "dyx")


def _is_watermark(text):
    if not text:
        return True
    low = text.lower()
    for w in _WATERMARK_WORDS:
        if w in low:
            return True
    # 形如 𝕜𝕜𝕪𝕤𝟘𝟙.𝕔𝕠𝕞 / ｋｅｋｙｓ.ｃｏｍ 这种被"美化"过的域名：
    # 归一化后只剩字母数字和点，且长度很短
    norm = re.sub(r'[\s\-_.·]', '', text)
    if norm and len(norm) <= 16 and not re.search(r'[\u4e00-\u9fff]', norm):
        if re.search(r'[^\x00-\x7f]', text) and re.search(r'\.', text):
            return True
    # 纯 ASCII 的裸域名
    if re.match(r'^[a-z0-9.\-]{3,30}$', low) and '.' in low and \
            not re.search(r'[\u4e00-\u9fff]', text):
        return True
    return False


class Spider(Spider):

    def getName(self):
        return "电影侠"

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
        self._search_token = ""
        self._search_token_ts = 0
        self._play_cache = {}
        self._warmed = False
        self.log("init: site=%s" % self.site_url)

    # ------------------------------------------------------------------
    # 基础工具
    # ------------------------------------------------------------------
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
        if not url:
            return ""
        url = url.strip().replace("&amp;", "&")
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith("http"):
            if not url.startswith("/"):
                url = "/" + url
            url = self.site_url + url
        return url

    def _pic_url(self, url):
        """封面地址改写：主域 /vod1/ 图片有防盗链(403)，
        必须换成 rdul.js 下发的资源镜像域，才能正常显示"""
        if not url:
            return ""
        url = self._fix_url(url)
        m = re.match(r'^https?://[^/]+(/vod1/.+)$', url, re.I)
        if m:
            return _pic_domain() + m.group(1)
        return url

    def _clean(self, s):
        if not s:
            return ""
        s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&lt;br&gt;", "\n").replace("&lt;", "<")
              .replace("&gt;", ">").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&amp;", "&"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    def _warm_up(self):
        """预热 + 顺便抓取搜索 token + 刷新图片资源域"""
        if self._warmed:
            return
        html = self._fetch(self.site_url + "/", timeout=20)
        if html:
            self._warmed = True
            self._dump_search_token(html)
            _load_rdul(self._fetch)
            self.log("预热完成, token=%s, 图片域=%s" %
                     (self._search_token[:12] or "NONE", _pic_domain()))

    def _dump_search_token(self, html):
        """从页面中任意 /search?k=xxx&amp;t=yyy 链接里取 token"""
        if not html:
            return
        for reg in (_RE_SEARCH_TOKEN, _RE_SEARCH_TOKEN2):
            m = reg.search(html)
            if m:
                self._search_token = m.group(1).replace("&amp;", "&")
                self._search_token_ts = int(time.time())
                return

    def _get_search_token(self, force=False):
        now = int(time.time())
        if not force and self._search_token and now - self._search_token_ts < 1800:
            return self._search_token
        if force:
            self._search_token = ""
        # 首页 + 最近更新的详情页（详情页的导演/演员/影评链接里一定有 token）
        html = self._fetch(self.site_url + "/")
        self._dump_search_token(html)
        if not self._search_token and html:
            ids = re.findall(r'/detail/(\d+)\.html', html)
            if ids:
                d = self._fetch(self.site_url + "/detail/%s.html" % ids[0])
                self._dump_search_token(d)
        if not self._search_token:
            # 离线兜底：站点默认 token（发现变化时会被自动刷新）
            self._search_token = "q0IwiO0HewIRRhj6stLhCg=="
            self._search_token_ts = now
        return self._search_token

    # ------------------------------------------------------------------
    # 列表解析
    # ------------------------------------------------------------------
    def _pick_cover(self, block):
        """卡片里有 2 张 img：第 1 张是占位兜底（id=noneCoverImg），取第 2 张"""
        imgs = _RE_IMG_TAG.findall(block)
        if not imgs:
            return ""
        cand = []
        for tag in imgs:
            mo = _RE_DATA_ORIGINAL.search(tag)
            u = mo.group(1) if mo else ""
            if not u:
                ms = _RE_SRC.search(tag)
                u = ms.group(1) if ms else ""
            if not u or "logo_placeholder" in u:
                continue
            if _RE_NONE_COVER.search(tag):
                continue
            cand.append(u)
        return self._pic_url(cand[0]) if cand else ""

    def _pick_title(self, block):
        """v-item-title 里有隐藏的干扰标题（display:none），只取可见那个"""
        best = ""
        for m in _RE_TITLE_DIV.finditer(block):
            attrs, txt = m.group(1), m.group(2)
            if _RE_STYLE_HIDE.search(attrs):
                continue
            t = self._clean(txt)
            if not t:
                continue
            # 过滤站点自己的水印标题
            if "可可影视" in t or "kekys" in t.lower():
                continue
            if not best:
                best = t
        return best

    def _extract_videos(self, html):
        videos = []
        seen = set()
        if not html:
            return videos

        # 1) 普通列表卡片
        for m in _RE_CARD_BLOCK.finditer(html):
            href, block = m.group(1), m.group(2)
            if href in seen:
                continue
            seen.add(href)
            name = self._pick_title(block)
            if not name:
                continue
            remark = ""
            mr = _RE_CARD_REMARK.search(block)
            if mr:
                remark = self._clean(mr.group(1))
            ms = _RE_CARD_SCORE.search(block)
            if ms:
                remark = ("豆瓣%s分" % ms.group(1)) + \
                         ((" " + remark) if remark else "")
            videos.append({
                "vod_id": href,
                "vod_name": name[:120],
                "vod_pic": self._pick_cover(block) or self.default_pic,
                "vod_remarks": remark[:40],
            })

        # 2) 搜索结果卡片
        if not videos:
            for m in _RE_SEARCH_BLOCK.finditer(html):
                href, block = m.group(1), m.group(2)
                if href in seen:
                    continue
                seen.add(href)
                mt = _RE_SEARCH_TITLE.search(block)
                name = self._clean(mt.group(1)) if mt else ""
                if not name:
                    name = href
                mc = _RE_SEARCH_CAT.search(block)
                remark = self._clean(mc.group(1)) if mc else ""
                videos.append({
                    "vod_id": href,
                    "vod_name": name[:120],
                    "vod_pic": self._pick_cover(block) or self.default_pic,
                    "vod_remarks": remark[:20],
                })

        # 3) 排行榜行
        if not videos:
            for m in _RE_RANK_BLOCK.finditer(html):
                href, block = m.group(1), m.group(2)
                if href in seen:
                    continue
                seen.add(href)
                mt = re.search(r'class="rank-row-title"[^>]*>([\s\S]*?)</div>', block, re.I)
                name = self._clean(mt.group(1)) if mt else ""
                if not name:
                    continue
                ms = re.search(r'class="rank-row-sub-title"[^>]*>([\s\S]*?)</div>', block, re.I)
                videos.append({
                    "vod_id": href,
                    "vod_name": name[:120],
                    "vod_pic": self.default_pic,
                    "vod_remarks": self._clean(ms.group(1))[:30] if ms else "",
                })

        # 4) 最后兜底：裸 href
        if not videos:
            for href in re.findall(r'href="(/detail/\d+\.html)"', html):
                if href in seen:
                    continue
                seen.add(href)
                videos.append({
                    "vod_id": href,
                    "vod_name": href.split("/")[-1].replace(".html", ""),
                    "vod_pic": self.default_pic,
                    "vod_remarks": "",
                })
        return videos

    def _page_count(self, html, page):
        """站点没有总页数，只看有没有"下一页" """
        if not html:
            return page
        if _RE_HAS_NEXT.search(html):
            return max(page + 1, 9999)
        return page

    # ------------------------------------------------------------------
    # 首页
    # ------------------------------------------------------------------
    def homeContent(self, filter=False):
        # TVBox 首次加载时只有 1~2 秒，这里不联网；筛选选项先用静态兜底，
        # 进过一次分类页后会用站点真实选项覆盖（见 _sync_filters）
        return {"class": CLASSES, "filters": dict(FILTERS)}

    def _sync_filters(self, html, ch):
        """从 /show 页面里抓站点真实的筛选选项，保证和网站一模一样"""
        if not html or ch in _DYN_FILTERS:
            return
        rows = re.findall(r'<div\s+class="filter-row">([\s\S]*?)</div>\s*</div>', html)
        if not rows:
            return
        parsed = {}
        for r in rows:
            ml = re.search(r'<strong>([^<]+)</strong>', r)
            if not ml:
                continue
            label = ml.group(1).strip().strip(":：")
            items = re.findall(
                r'<a\s+href="([^"]+)"\s+class="filter-item[^"]*">([^<]*)<', r)
            vals = []
            for href, txt in items:
                txt = txt.strip()
                if not txt:
                    continue
                # 站点偶尔把行标题当成一个选项塞进来（如 "地区"/"类型"），跳过
                if txt == label:
                    continue
                # 从 href 里还原该选项的真实参数值
                seg = href.split("/show/")[-1].replace(".html", "").split("-")
                key_map = {"类型": ("class", 1), "地区": ("area", 2),
                           "语言": ("lang", 3), "年份": ("year", 4),
                           "排序": ("sort", 5)}
                if label not in key_map:
                    continue
                k, idx = key_map[label]
                try:
                    raw = seg[idx]
                except Exception:
                    raw = ""
                v = urllib.parse.unquote(raw).strip()
                if txt in ("全部",) and not v:
                    vals.append({"n": txt, "v": ""})
                else:
                    vals.append({"n": txt, "v": v})
            if vals:
                k = key_map[label][0]
                parsed[k] = vals

        if parsed.get("class") or parsed.get("area"):
            order = ["class", "area", "lang", "year", "sort"]
            filt = [{"key": k, "name": {"class": "类型", "area": "地区",
                                        "lang": "语言", "year": "年份",
                                        "sort": "排序"}[k],
                     "value": parsed[k]} for k in order if k in parsed]
            if filt:
                _DYN_FILTERS[ch] = filt
                FILTERS[ch] = filt
                self.log("筛选已同步: %s -> %s" % (ch, [f["key"] for f in filt]))

    def homeVideoContent(self):
        self._warm_up()
        html = self._fetch(self.site_url + "/")
        videos = self._extract_videos(html)
        self.log("home: %d 条" % len(videos))
        return {"list": videos}

    # ------------------------------------------------------------------
    # 分类
    # ------------------------------------------------------------------
    def _show_url(self, ch, cls, area, lang, year, sort, page):
        q = lambda s: urllib.parse.quote(str(s), safe="") if s else ""
        return "%s/show/%s-%s-%s-%s-%s-%s-%s.html" % (
            self.site_url, ch, q(cls), q(area), q(lang), q(year), sort or "3", page)

    def categoryContent(self, tid, pg, filter, extend):
        self._warm_up()
        page = int(pg) if str(pg).isdigit() else 1
        tid = str(tid or "1")

        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}

        for k in list(extend.keys()):
            if extend[k] in ("", None, "全部"):
                del extend[k]

        cls = extend.get("class") or ""
        area = extend.get("area") or ""
        lang = extend.get("lang") or ""
        year = extend.get("year") or ""
        sort = extend.get("sort") or "3"

        # 保险：兼容旧版 UI 缓存传回"显示名"而不是真实值
        _area_alias = {"大陆": "中国大陆", "香港": "中国香港", "台湾": "中国台湾"}
        if area in _area_alias:
            area = _area_alias[area]

        # 聚合页
        if tid == "new":
            url = "%s/new/%d.html" % (self.site_url, page)
        elif tid == "rank":
            url = "%s/ranking/index.html" % self.site_url
        elif tid in _FILTER_TYPES or tid in ("1", "2", "3", "4", "6"):
            url = self._show_url(tid, cls, area, lang, year, sort, page)
        else:
            # 频道首页（站点原生 /channel/x.html）
            url = "%s/channel/%s.html" % (self.site_url, tid)
            if page > 1:
                url = self._show_url(tid, cls, area, lang, year, sort, page)

        self.log("category: %s" % url)
        html = self._fetch(url)
        if page == 1:
            self._sync_filters(html, tid)
        videos = self._extract_videos(html)
        pagecount = self._page_count(html, page)
        self.log("  -> %d 条, pagecount=%s" % (len(videos), pagecount))

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": (pagecount * 24) if pagecount != 9999 else 999999,
        }

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def _do_search(self, key, page):
        token = self._get_search_token()
        kw = urllib.parse.quote(key)
        url = "%s/search?k=%s&t=%s" % (self.site_url, kw, token)
        if page > 1:
            # 站点的搜索结果也支持翻页（?k=..&t=..&page=n）
            url += "&page=%d" % page
        self.log("search: %s" % url)
        html = self._fetch(url)

        # token 失效时页面里不会出现结果，重新取一次 token 再试
        if not re.search(r'class="search-result-item"', html or "", re.I):
            new_token = self._get_search_token(force=True)
            if new_token and new_token != token:
                url = "%s/search?k=%s&t=%s" % (self.site_url, kw, new_token)
                if page > 1:
                    url += "&page=%d" % page
                self.log("search retry: %s" % url)
                html = self._fetch(url)
        return html

    def searchContent(self, key, quick, pg="1"):
        self._warm_up()
        page = int(pg) if str(pg).isdigit() else 1
        html = self._do_search(key, page)
        videos = self._extract_videos(html)
        self.log("  -> %d 条" % len(videos))
        return {
            "list": videos,
            "page": page,
            "pagecount": self._page_count(html, page),
            "limit": 24,
            "total": 9999,
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    def _parse_sources(self, html):
        """返回 [(线路名, [ (集名, 播放页url), ... ]), ...]

        站点结构：source-list 里的 a.source-item（只有线路名 + 集数角标）
                  与 episode-list-box 里的 div.episode-list（剧集）按"出现顺序"一一对应。
        这里不按 div 边界切（容易把结尾的标签吃掉），而是：
          1. 取线路名列表
          2. 取全部 episode-item（保持页面顺序）
          3. 按线路的集数角标（i.source-item-num）切分；角标缺失时按均分兜底
        """
        names, counts = [], []
        block = html
        i0 = html.find('source-list-box-main')
        i1 = html.find('episode-list-box-main')
        if i0 > 0 and i1 > i0:
            block = html[i0:i1]
        for sm in _RE_SOURCE_ITEM.finditer(block):
            inner = sm.group(1)
            ml = _RE_SOURCE_LABEL.search(inner)
            label = self._clean(ml.group(1)) if ml else ""
            if not label:
                continue
            sub = _RE_SOURCE_SUB.search(inner)
            sub_t = self._clean(sub.group(1)) if sub else ""
            mn = _RE_SOURCE_NUM.search(inner)
            names.append(label + (("·" + sub_t) if sub_t else ""))
            try:
                counts.append(int(mn.group(1)) if mn else 0)
            except Exception:
                counts.append(0)

        eps = []
        for em in _RE_EP_ITEM.finditer(html):
            href = em.group(1).replace("&amp;", "&")
            span = _RE_SPAN.search(em.group(2))
            ep_name = self._clean(span.group(1)) if span else ""
            eps.append((ep_name, href))

        if not names:
            if not eps:
                return []
            by_sid, order = {}, []
            for _, href in eps:
                ms = _RE_SID.search(href)
                sid = ms.group(1) if ms else "0"
                if sid not in by_sid:
                    by_sid[sid] = []
                    order.append(sid)
                by_sid[sid].append(("第%d集" % (len(by_sid[sid]) + 1), href))
            return [("线路" + str(i + 1), by_sid[s]) for i, s in enumerate(order)]

        # 校验角标总数，不合理就均分
        if sum(counts) != len(eps):
            n, base = len(names), len(eps) // max(len(names), 1)
            counts = [base] * n
            for k in range(len(eps) - base * n):
                counts[k] += 1

        out, pos = [], 0
        for i, name in enumerate(names):
            cnt = counts[i]
            chunk = eps[pos:pos + cnt]
            pos += cnt
            if not chunk:
                continue
            out.append((name, chunk))
        return out

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        self.log("detail: %s" % url)

        html = self._fetch(url)
        if not html:
            return {"list": []}
        self._dump_search_token(html)

        # 标题：detail-title 里多个 strong，真标题在偶数位（奇数位是站点水印）
        # 水印样式由 CSS 控制（.detail-title strong:nth-child(odd){display:none}），
        # 所以按"是否像水印"来挑：含 kekys / 全角/数学字符域名 / 纯域名
        name = ""
        m = _RE_DETAIL_TITLE.search(html)
        if m:
            cand = []
            for sm in _RE_STRONG.finditer(m.group(1)):
                t = self._clean(sm.group(1))
                if t:
                    cand.append(t)
            real = [t for t in cand if not _is_watermark(t)]
            name = real[0] if real else (cand[0] if cand else "")
        if not name:
            mt = _RE_H1.search(html)
            if mt:
                name = self._clean(mt.group(1))
        if not name:
            mt = _RE_SITE_TITLE.search(html)
            if mt:
                name = self._clean(mt.group(1).split("_")[0].split("-")[0])
        name = re.sub(r"\s*\(\d{4}\)\s*$", "", name).strip() or vod_id

        # 封面
        pic = self.default_pic
        mp = _RE_DETAIL_PIC.search(html)
        if mp and mp.group(1):
            pic = self._pic_url(mp.group(1))

        # 简介
        content = ""
        md = _RE_DETAIL_DESC.search(html)
        if md:
            content = self._clean(md.group(1))
        if not content:
            mm = _RE_META_DESC.search(html)
            if mm:
                content = self._clean(mm.group(1))
        content = INTRO_PREFIX + ("\n" + content if content else "")

        # 元信息行：导演 / 演员 / 首映 / 片长 / 备注
        info = {}
        for im in _RE_INFO_ROW.finditer(html):
            k = self._clean(im.group(1)).replace(":", "").replace("：", "").strip()
            v = self._clean(im.group(2))
            if k and v and k not in info:
                info[k] = v
        director = info.get("导演", "")
        actor = re.sub(r"\s*/\s*", ", ", info.get("演员", ""))
        actor = re.sub(r"\s*,\s*", ", ", actor).strip(", ")
        remark = info.get("备注", "") or info.get("片长", "")
        year = info.get("首映", "")
        area = ""
        ma = re.search(r'<a\s+href="/show/[^"]*"\s+class="detail-tags-item"[^>]*>([^<]+)</a>[\s\S]{0,200}?'
                       r'<a\s+href="/show/[^"]*"\s+class="detail-tags-item"[^>]*>([^<]+)</a>', html)
        if ma:
            a1, a2 = self._clean(ma.group(1)), self._clean(ma.group(2))
            area = a2 if re.match(r'^\d{4}$', a1) else a1

        # 线路 + 剧集
        groups = self._parse_sources(html)
        self.log("  线路: %s" % [g[0] for g in groups])
        if not groups:
            return {"list": []}

        play_from = []
        play_url = []
        for lname, eps in groups:
            play_from.append(lname)
            play_url.append("#".join("%s$%s" % (n, self._fix_url(h)) for n, h in eps))

        vod = {
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_area": area,
            "vod_year": year,
            "vod_remarks": remark or ("%d条线路" % len(groups)),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return {"list": [vod]}

    # ------------------------------------------------------------------
    # 播放
    # ------------------------------------------------------------------
    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        self.log("player: %s" % play_page)

        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 300:
                return res

        html = self._fetch(play_page)
        url = ""
        if html:
            mv = _RE_PLAY_SRC.search(html)
            if mv:
                url = mv.group(1).strip()
            if not url:
                mv = _RE_PLAY_SRC2.search(html)
                if mv:
                    url = mv.group(1).strip()

        if url:
            url = url.replace("\\/", "/").replace("&amp;", "&")
            if url.startswith("//"):
                url = "https:" + url
            self.log("  => 直链: %s" % url[:160])
            res = {
                "parse": 0,
                "playUrl": "",
                "url": url,
                "header": {
                    "User-Agent": UA,
                    "Referer": self.site_url + "/",
                    "Origin": self.site_url,
                },
            }
            self._play_cache[play_page] = (now, res)
            return res

        # 部分影片页面里 src 为空（直链没下发），交给 TVBox 嗅探
        self.log("  => 无直链，回退嗅探")
        res = {
            "parse": 1,
            "playUrl": "",
            "url": play_page,
            "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
        }
        self._play_cache[play_page] = (now, res)
        return res

    # ------------------------------------------------------------------
    # 可选接口
    # ------------------------------------------------------------------
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
