# coding=utf-8
# !/usr/bin/python
# -*- coding: utf-8 -*-
"""
TVBox 影视爬虫 —— 低端影视 (https://www.ddys24.com/)
======================================================
网站真实结构编写（全部 url / class / 字段均来自真实网页源码，
仅参考 TVBox 通用接口规范）。

【真实结构】
  分类:   /ddvodshow/{tid}-----------.html
  分页:   /ddvodshow/{tid}--------{page}---.html
  详情:   /ddvoddetail/{id}.html
  播放页: /ddvodplay/{id}-{线路}-{集数}.html
  搜索:   /ddvodsearch/{关键词}-------------.html
  卡片锚点: <a class="...stui-vodlist_ddy1102-cthumb ..." href="/ddvoddetail/{id}.html"
              title="名称" data-original="图片">
  播放地址: 播放页内  var player_aaaa={...,"url":"xxx.m3u8","encrypt":0,...}
            encrypt=0 表示直链未加密，直接取 url 即可。
"""

import sys
import re
import json
import base64
import time
import urllib.parse
from urllib.parse import urljoin, quote, unquote

# 双保险引入 Spider 基类：
#   1) 优先使用影视仓/FongMi 注入的 base.spider.Spider（提供 self.fetch / self.log）
#   2) 导入失败时，用自带兜底基类（内部用 requests 实现 fetch），
#      避免因基类 import 失败导致整个爬虫不可用（分类显示不出来的重要原因）。
try:
    from base.spider import Spider
except Exception:
    import requests as _rq
    try:
        _rq.packages.urllib3.disable_warnings()
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
            r.encoding = 'utf-8'
            return r

        def log(self, *a, **kw):
            try:
                print("[ddys24]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


# ============================== 常量配置 ==============================

HOST = "https://www.ddys24.com"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 顶部一级分类（真实取自导航：/ddvodtype/*.html）
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
    {"type_id": "42", "type_name": "豆瓣Top250"},
]

# 二级分类（真实取自首页板块链接 /ddvodshow/{tid}-----------.html）
SUB_CLASSES = {
    "1": [
        {"type_id": "6", "type_name": "动作片"},
        {"type_id": "7", "type_name": "喜剧片"},
        {"type_id": "8", "type_name": "爱情片"},
        {"type_id": "9", "type_name": "科幻片"},
        {"type_id": "10", "type_name": "恐怖片"},
        {"type_id": "11", "type_name": "剧情片"},
        {"type_id": "12", "type_name": "战争片"},
        {"type_id": "20", "type_name": "纪录片"},
        {"type_id": "29", "type_name": "犯罪片"},
        {"type_id": "39", "type_name": "动漫片"},
    ],
    "2": [
        {"type_id": "13", "type_name": "国产剧"},
        {"type_id": "43", "type_name": "抖音短剧"},
        {"type_id": "16", "type_name": "美剧"},
        {"type_id": "14", "type_name": "港剧"},
        {"type_id": "15", "type_name": "韩剧"},
        {"type_id": "21", "type_name": "泰剧"},
        {"type_id": "35", "type_name": "海外剧"},
        {"type_id": "40", "type_name": "日剧"},
        {"type_id": "41", "type_name": "台剧"},
    ],
    "3": [
        {"type_id": "22", "type_name": "内地综艺"},
        {"type_id": "23", "type_name": "港台综艺"},
        {"type_id": "24", "type_name": "日韩综艺"},
        {"type_id": "25", "type_name": "欧美综艺"},
    ],
    "4": [
        {"type_id": "26", "type_name": "国漫"},
        {"type_id": "27", "type_name": "日韩动漫"},
        {"type_id": "28", "type_name": "欧美动漫"},
        {"type_id": "34", "type_name": "海外动漫"},
    ],
}

# 筛选维度（真实取自分类页：按剧情/地区/语言/年份/字母/排序）
FILTER_OPTIONS = {
    "剧情": ["喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争", "警匪",
           "犯罪", "动画", "奇幻", "武侠", "冒险", "枪战", "悬疑",
           "惊悚", "经典", "青春", "文艺", "微电影", "古装", "历史", "运动",
           "农村", "儿童", "网络电影", "其它"],
    "地区": ["大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国",
           "德国", "泰国", "印度", "意大利", "西班牙", "加拿大", "其他", "其它"],
    "语言": ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "法语", "德语",
           "其它"],
    "年份": ["2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017",
           "2016", "2015", "2014", "2013", "2012", "2011", "2010"],
    "字母": list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    "排序": ["按最新", "按人气", "按评分"],
}

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"


def _clean(t):
    """去除 html 标签与多余空白，解码实体"""
    if not t:
        return ""
    t = re.sub(r'<[^>]+>', '', t)
    t = t.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"') \
         .replace('&#39;', "'").replace('&lt;', '<').replace('&gt;', '>')
    return re.sub(r'\s+', ' ', t).strip()


class Spider(Spider):

    # ---------------------------------------------------------- 基础
    def getName(self):
        return "低端影视"

    def init(self, extend=""):
        # 读取配置（影视仓里可在接口末尾追加 {"site":"..."} 覆盖域名）
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}

        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        self.headers = {
            "User-Agent": UA,
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                       "image/avif,image/webp,*/*;q=0.8"),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.site_url + "/",
        }
        self.log("init: site=%s" % self.site_url)

    def log(self, msg):
        try:
            print("[ddys24] %s" % msg)
        except Exception:
            pass

    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return False

    def homeVideoContent(self):
        """首页推荐列表（最近更新板块），独立于 homeContent，避免互相拖垮"""
        result = {"list": []}
        try:
            html = self._get(self.site_url + "/")
            result["list"] = self._extract_videos(html)
        except Exception as e:
            print("homeVideoContent error:", e)
        return result

    def localProxy(self, param):
        return None

    def destroy(self):
        pass

    # ---------------------------------------------------------- 通用请求
    def _get(self, url, referer=None, timeout=15):
        """
        统一请求：优先使用 TVBox 注入的 self.fetch（影视仓/FongMi 标准做法）；
        若环境无 fetch（本地调试），回退到 urllib。
        """
        h = dict(getattr(self, "headers", {}))
        if referer:
            h["Referer"] = referer
        for _ in range(3):
            try:
                rsp = self.fetch(url, headers=h, timeout=timeout)
                if hasattr(rsp, "text"):
                    return rsp.text or ""
                if hasattr(rsp, "content"):
                    return (rsp.content or b"").decode("utf-8", "ignore")
                return str(rsp)
            except Exception as e:
                self.log("fetch FAIL %s -> %s" % (url, e))
                time.sleep(0.4)
        return ""

    # ---------------------------------------------------------- 解析卡片
    def _extract_videos(self, html):
        """统一锚点解析：首页 / 分类 / 搜索 卡片结构一致"""
        videos = []
        seen = set()
        # 卡片锚点：<a class="...stui-vodlist_ddy1102-cthumb..." href="/ddvoddetail/{id}.html"
        #            title="名称" data-original="图片">
        pat = re.compile(
            r'<a[^>]*class="[^"]*stui-vodlist_ddy1102-cthumb[^"]*"[^>]*'
            r'href="(/ddvoddetail/(\d+)\.html)"[^>]*'
            r'title="([^"]*)"[^>]*'
            r'data-original="([^"]*)"',
            re.S)
        for m in pat.finditer(html):
            vid = m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            name = _clean(m.group(3))
            pic = m.group(4).strip()
            if pic.startswith('//'):
                pic = "https:" + pic
            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": "",
            })

        # 补备注：<span class="pic-text text-right">HD国语</span>
        rems = re.findall(
            r'<a[^>]*class="[^"]*stui-vodlist_ddy1102-cthumb[^"]*"[^>]*'
            r'href="(/ddvoddetail/\d+\.html)"[^>]*>.*?'
            r'<span class="pic-text[^"]*">([^<]*)</span>', html, re.S)
        rem_map = {m[0]: _clean(m[1]) for m in rems}
        for v in videos:
            r = rem_map.get("/ddvoddetail/%s.html" % v["vod_id"], "")
            if r:
                v["vod_remarks"] = r
        return videos

    def _total_page(self, html):
        """从分页区取总页数：<span class="num">1/203</span>"""
        m = re.search(r'<span class="num">\d+\s*/\s*(\d+)</span>', html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        # 兜底：尾页链接 /ddvodshow/6--------203---.html
        m = re.search(r'/ddvodshow/\d+-{8}(\d+)-{3}\.html">尾页', html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        return 1

    # ---------------------------------------------------------- 首页
    def homeContent(self, filter=True):
        """
        分类只保留网站导航的 5 个大类：电影 / 电视剧 / 综艺 / 动漫 / 豆瓣Top250。
        二级分类（动作片、喜剧片…）不单独占分类位，而是放进各分类的“分类”筛选项里。
        分类/筛选为纯静态数据，不依赖网络。
        """
        result = {"class": [], "filters": {}}
        for c in CLASSES:
            result["class"].append({
                "type_id": c["type_id"],
                "type_name": c["type_name"],
            })

        if filter:
            for c in CLASSES:
                tid = c["type_id"]
                result["filters"][tid] = self._build_filters(tid)
        return result

    def _build_filters(self, tid=None):
        """
        筛选维度（真实取自分类页筛选栏）：
          分类：该大类下的二级分类（选中后替换 URL 首段 tid）
          剧情 / 地区 / 语言 / 年份 / 字母 / 排序
        真实 URL 分段：{tid}-{剧情}-{地区}-{语言}-{年份}-{字母}-{排序}-{页}...
        """
        def group(name, values):
            opts = [{"n": "全部", "v": ""}]
            for v in values:
                opts.append({"n": v, "v": v})
            return {"key": name, "name": name, "value": opts}

        filters = []
        # 分类（二级分类；仅当该大类有二级时显示）
        subs = SUB_CLASSES.get(str(tid), [])
        if subs:
            opts = [{"n": "全部", "v": ""}]
            for s in subs:
                opts.append({"n": s["type_name"], "v": s["type_id"]})
            filters.append({"key": "分类", "name": "分类", "value": opts})

        filters += [
            group("剧情", FILTER_OPTIONS["剧情"]),
            group("地区", FILTER_OPTIONS["地区"]),
            group("语言", FILTER_OPTIONS["语言"]),
            group("年份", FILTER_OPTIONS["年份"]),
            group("字母", FILTER_OPTIONS["字母"]),
            {
                "key": "排序", "name": "排序",
                "value": [
                    {"n": "按最新", "v": ""},
                    {"n": "按人气", "v": "hits"},
                    {"n": "按评分", "v": "score"},
                ]
            },
        ]
        return filters

    # ---------------------------------------------------------- 分类
    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": int(pg), "pagecount": 1,
                  "limit": 24, "total": 999999}
        try:
            pg = int(pg) if str(pg).isdigit() else 1
            tid = str(tid)

            # extend 可能是 dict，也可能是 JSON 字符串（影视仓/FongMi 实际传字符串）
            if isinstance(extend, str):
                try:
                    extend = json.loads(extend) if extend.strip() else {}
                except Exception:
                    extend = {}
            if not isinstance(extend, dict):
                extend = {}

            # “分类”筛选：选中二级分类时，替换 URL 首段的 tid
            sub_tid = extend.get("分类", "") or ""
            if sub_tid:
                tid = str(sub_tid)

            # 真实分段结构（实测归纳，tid 后固定 12 段，用 '-' 连接）：
            #   索引: 0(空) 1(地区) 2(排序) 3(剧情) 4(语言) 5(字母) 6(空) 7(空)
            #         8(页) 9(空) 10(空) 11(年份)
            # 例：/ddvodshow/6--------2---.html  -> 第2页
            #     /ddvodshow/6---喜剧--------.html -> 剧情=喜剧
            plot = extend.get("剧情", "") or ""
            area = extend.get("地区", "") or ""
            lang = extend.get("语言", "") or ""
            year = extend.get("年份", "") or ""
            letter = extend.get("字母", "") or ""
            order = extend.get("排序", "") or ""

            def seg(x):
                return quote(x, safe='') if x else ""

            page_seg = "" if (pg <= 1) else str(pg)
            segs = ["", seg(area), seg(order), seg(plot), seg(lang), seg(letter),
                    "", "", page_seg, "", "", seg(year)]
            url = "%s/ddvodshow/%s%s.html" % (self.site_url, tid, "-".join(segs))

            html = self._get(url, referer=self.site_url + "/")
            result["list"] = self._extract_videos(html)
            result["pagecount"] = self._total_page(html)
            result["page"] = pg
        except Exception as e:
            self.log("categoryContent error: %s" % e)
        return result

    # ---------------------------------------------------------- 搜索
    def searchContent(self, key, quick, pg="1"):
        result = {"list": [], "page": int(pg) if str(pg).isdigit() else 1}
        try:
            kw = quote(key, safe='')
            url = "%s/ddvodsearch/%s-------------.html" % (self.site_url, kw)
            html = self._get(url, referer=self.site_url + "/")
            result["list"] = self._extract_videos(html)
        except Exception as e:
            print("searchContent error:", e)
        return result

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ---------------------------------------------------------- 详情
    def detailContent(self, array):
        try:
            tid = array[0]
            url = "%s/ddvoddetail/%s.html" % (self.site_url, tid)
            html = self._get(url, referer=self.site_url + "/")
            if not html:
                return {"list": []}

            vod = {
                "vod_id": str(tid),
                "vod_name": "",
                "vod_pic": "",
                "type_name": "",
                "vod_year": "",
                "vod_area": "",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": "",
                "vod_play_from": "",
                "vod_play_url": "",
            }

            # 名称
            m = re.search(r'<h1 class="title">\s*([^<]+?)\s*</h1>', html)
            if m:
                vod["vod_name"] = _clean(m.group(1))
            if not vod["vod_name"]:
                m = re.search(r'<title>\s*《?([^《》<]+?)》?[^<]*</title>', html)
                if m:
                    vod["vod_name"] = _clean(m.group(1))

            # 封面（懒加载 data-original）
            m = re.search(
                r'<a[^>]*class="[^"]*picture[^"]*"[^>]*>.*?'
                r'<img[^>]*data-original="([^"]+)"', html, re.S)
            if not m:
                m = re.search(r'<img[^>]*class="lazyload"[^>]*data-original="([^"]+)"', html)
            if m:
                pic = m.group(1).strip()
                if pic.startswith('//'):
                    pic = "https:" + pic
                vod["vod_pic"] = pic

            # 备注 / 评分
            m = re.search(r'<span class="pic-text text-right">([^<]*)</span>', html)
            if m:
                vod["vod_remarks"] = _clean(m.group(1))

            # 类型 / 地区 / 年份 / 语言 / 主演 / 导演 / 更新
            # 真实结构（来源网页源码，字段值均为 <a> 链接，可能多个）：
            #   <p class="data hidden-xs">
            #     <span class="text-ddy1102-muted">类型：</span>
            #       <a ...>剧情</a>&nbsp;<a ...>爱情</a>...<span class="split-ddy1102-line"></span>
            #     <span...>地区：</span><a ...>中国大陆</a>...
            #   </p>
            #   <p class="data"><span...>主演：</span><a...>李梦</a>...</p>
            # 做法：遍历所有 <p class="data..."> 块，按 label 切出内容段再清洗标签
            _field_map = [("类型：</span>", "type_name"), ("地区：</span>", "vod_area"),
                          ("年份：</span>", "vod_year"),
                          ("主演：</span>", "vod_actor"), ("导演：</span>", "vod_director")]
            for pm in re.finditer(r'<p class="data[^"]*">(.*?)</p>', html, re.S):
                block = pm.group(1)
                for label, key in _field_map:
                    if vod.get(key):
                        continue
                    if label not in block:
                        continue
                    seg = block.split(label, 1)[1]
                    # 字段值后面有分隔线，只取分隔线之前的内容
                    if 'split-ddy1102-line' in seg:
                        seg = seg.split('<span class="split-ddy1102-line">')[0]
                    vod[key] = _clean(seg)

            # 简介（真实：含 "剧情：" 的 span）
            cm = re.search(r'剧情：</b>\s*([^<]*)</span>', html)
            if cm:
                vod["vod_content"] = INTRO_PREFIX + _clean(cm.group(1))

            # ---------- 播放线路 ----------
            # 真实结构：每个线路块内 <h3 class="title">线路名</h3> ... 之后紧跟
            #           <ul class="stui-content_ddy1102-cplaylist ..."> 剧集列表 </ul>
            # 注意：线路名不一定是"线路X"，也可能是"高清线路"，故不能只按名称匹配。
            # 采用锚点法：以 cplaylist 的 <ul> 为锚，向前回溯最近的 h3.title 取线路名。
            play_from = []
            play_url = []
            for um in re.finditer(
                    r'<ul class="stui-content_ddy1102-cplaylist[^"]*">(.*?)</ul>',
                    html, re.S):
                body = um.group(1)
                # 向前找最近的 h3.title 作为线路名
                head = html[:um.start()]
                hm = None
                for hm in re.finditer(r'<h3 class="title">\s*(.*?)\s*</h3>', head, re.S):
                    pass
                line_name = ""
                if hm:
                    line_name = _clean(hm.group(1))
                # 剔除注释掉的链接
                body = re.sub(r'<!--.*?-->', '', body, flags=re.S)
                links = re.findall(
                    r'<a[^>]*href="(/ddvodplay/(\d+)-(\d+)-(\d+)\.html)"[^>]*>([^<]+)</a>',
                    body)
                if not links:
                    continue
                eps = []
                seen_ep = set()
                for href, vid, line, ep, label in links:
                    n = _clean(label) or ("第%s集" % ep)
                    if href in seen_ep:
                        continue
                    seen_ep.add(href)
                    eps.append("%s$%s" % (n, urljoin(self.site_url, href)))
                if eps:
                    play_from.append(line_name or ("线路%d" % (len(play_from) + 1)))
                    play_url.append("#".join(eps))

            vod["vod_play_from"] = "$$$".join(play_from)
            vod["vod_play_url"] = "$$$".join(play_url)
            return {"list": [vod]}
        except Exception as e:
            print("detailContent error:", e)
            return {"list": []}

    # ---------------------------------------------------------- 播放
    def playerContent(self, flag, id, vipFlags):
        result = {"parse": 0, "playUrl": "", "url": id,
                  "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}
        try:
            # id 即播放页地址 /ddvodplay/{id}-{line}-{ep}.html
            pu = id if id.startswith("http") else self.site_url + id
            html = self._get(pu, referer=self.site_url + "/")

            # 真实：var player_aaaa={...,"url":"xxx.m3u8","encrypt":0,...}
            m = re.search(r'var player_aaaa=(\{.*?\})</script>', html, re.S)
            if not m:
                m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*;?\s*</script>', html, re.S)
            if not m:
                m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*<', html, re.S)

            real = ""
            encrypt = 0
            from_ = ""
            if m:
                try:
                    data = json.loads(m.group(1))
                    real = data.get("url", "") or ""
                    encrypt = int(data.get("encrypt", 0) or 0)
                    from_ = data.get("from", "") or ""
                except Exception:
                    # json 解析失败用粗暴提取
                    u = re.search(r'"url"\s*:\s*"([^"]+)"', m.group(1))
                    if u:
                        real = u.group(1)
                    e = re.search(r'"encrypt"\s*:\s*(\d+)', m.group(1))
                    if e:
                        encrypt = int(e.group(1))

            real = real.replace('\\/', '/').strip()
            if not real:
                # 兜底：正则直接抓 m3u8
                u = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
                if u:
                    real = u.group(1)

            if real and real.startswith('//'):
                real = "https:" + real
            if real and not real.startswith('http'):
                real = urljoin(pu, real)

            if not real:
                result["url"] = id
                return result

            # encrypt 非 0 时尝试 base64/unquote 解密（兼容可能出现的加密线路）
            if encrypt != 0:
                real = self._decode(real)

            # 直接使用网页 player_aaaa 里给出的原始地址（与网页播放完全一致）。
            # 注意：不要再把 master 主列表降级为子列表——本站多条 CDN 线路的
            #       子列表分片位于不同域名，降级后播放器可能因跨域/Referer 问题黑屏。
            #       网页播放器也是直接播这个地址，故保持一致最稳。
            final_url = real

            result["parse"] = 0
            result["playUrl"] = ""
            result["url"] = final_url
            # header：默认不带 Referer（CDN 实测不校验防盗链；
            #         带站点 Referer 反而可能在跨域分片时被拒，导致黑屏）。
            result["header"] = {"User-Agent": UA}
        except Exception as e:
            self.log("playerContent error: %s" % e)
        return result

    def _decode(self, s):
        """兼容性解密：base64 -> url decode"""
        try:
            t = s
            for _ in range(2):
                try:
                    pad = t + "=" * (-len(t) % 4)
                    d = base64.b64decode(pad).decode('utf-8', 'ignore')
                    if d.startswith('http'):
                        t = d
                    else:
                        break
                except Exception:
                    break
            t = unquote(t)
            return t
        except Exception:
            return s

    def _resolve_master(self, url):
        """
        若为 master playlist（含 EXT-X-STREAM-INF），取最低码率子列表地址。
        低端影视的 url 多为 v.gsuus.com/play/xxx/index.m3u8 这种主列表，
        返回子 m3u8 可让 TVBox 直接播放、减少卡顿。
        """
        try:
            if '.m3u8' not in url:
                return ""
            txt = self._get(url, referer=self.site_url + "/")
            if 'EXT-X-STREAM-INF' not in txt:
                return ""
            lines = [l.strip() for l in txt.splitlines() if l.strip()]
            subs = []
            for i, l in enumerate(lines):
                if l.startswith('#EXT-X-STREAM-INF'):
                    bw = re.search(r'BANDWIDTH=(\d+)', l)
                    if i + 1 < len(lines):
                        sub = lines[i + 1]
                        subs.append((int(bw.group(1)) if bw else 0, sub))
            if not subs:
                return ""
            subs.sort(key=lambda x: x[0])
            sub = subs[0][1]
            if sub.startswith('http'):
                return sub
            return urljoin(url, sub)
        except Exception:
            return ""

    # ---------------------------------------------------------- 其它
    def action(self, action):
        return {}

    def close(self):
        self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
