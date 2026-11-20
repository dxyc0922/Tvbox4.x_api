# -*- coding: utf-8 -*-
# 大米星球 蜘蛛（源自 Hamo 插件 com.butterfly.damixingqiu 的解析逻辑移植）
import base64
import gzip
import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    DEFAULT_HOST = "http://dmxq22.com"
    UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    BAD_PIC_KEYWORDS = ["loading", "load.gif", "icon.png", "frosted.png", "colour-bg", "logo"]
    BAD_SSL_DOMAINS = ["rrcdnbf2.com", "rrcdnbf4.com", "ifznedy1.com", "m3u8.tv", "dmxq"]
    COMMON_BY = [("", "全部排序"), ("time", "时间排序"), ("hits", "人气排序"), ("score", "评分排序")]
    AREA = ["", "大陆", "香港", "台湾", "美国", "日本", "韩国", "英国", "法国", "德国", "印度", "泰国", "丹麦", "瑞典", "巴西", "加拿大", "俄罗斯", "意大利", "比利时", "爱尔兰", "西班牙", "澳大利亚"]
    LANG = ["", "国语", "英语", "粤语", "日语", "韩语", "法语", "德语", "泰语", "俄语", "闽南语", "丹麦语", "波兰语", "瑞典语", "印地语", "挪威语", "意大利语", "西班牙语"]
    YEARS = ["", "2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017", "2016", "2015", "2014", "2013", "2012", "2011", "2010", "2009", "2008", "2007", "2006", "2005", "2004", "2003", "2002", "2001", "2000", "90年代", "80年代", "70年代", "更早"]
    CLASS_MOVIE = ["", "Netflix", "动作", "喜剧", "爱情", "科幻", "剧情", "悬疑", "恐怖", "惊悚", "犯罪", "冒险", "战争", "奇幻", "动画", "古装", "武侠", "家庭", "纪录", "传记", "历史"]
    CLASS_TV = ["", "Netflix", "短剧", "都市", "言情", "古装", "武侠", "悬疑", "罪案", "科幻", "仙侠", "穿越", "动作", "喜剧", "家庭", "战争", "谍战", "历史"]
    CLASSES = [("today", "今日更新"), ("netflix", "Netflix"), ("20", "电影"), ("21", "电视剧"), ("22", "动漫"), ("23", "综艺"), ("36", "短剧")]
    CARD_RE = re.compile(r'<a[^>]+href=["\'][^"\']*voddetail/(\d+)\.html["\'][^>]*>([\s\S]*?<img[\s\S]*?)</a>', re.I)
    EP_RE = re.compile(r'<a[^>]+href=["\'][^"\']*vodplay/(\d+-\d+-\d+)\.html["\'][^>]*>([\s\S]*?)</a>', re.I)

    def getName(self):
        return "大米星球"

    def init(self, extend=""):
        self.host = self.DEFAULT_HOST
        if isinstance(extend, str) and extend.strip().startswith("http"):
            self.host = extend.strip().rstrip("/")

    # ---------- transport ----------
    def _fetch(self, url):
        headers = {"User-Agent": self.UA, "Referer": self.host + "/", "Accept-Encoding": "gzip"}
        for _ in range(2):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read()
                if raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                if raw:
                    return raw.decode("utf-8", "replace")
            except Exception:
                pass
            time.sleep(0.5)
        if url.startswith("https://"):
            return self._fetch_http(url)
        return ""

    def _fetch_http(self, url):
        headers = {"User-Agent": self.UA, "Referer": self.host + "/"}
        try:
            req = urllib.request.Request("http://" + url[8:], headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", "replace") if raw else ""
        except Exception:
            return ""

    # ---------- helpers ----------
    def _strip(self, s):
        if not s:
            return ""
        return re.sub(r"<[^>]+>", "", str(s)).strip()

    def _decode_unicode_url(self, s):
        if not s:
            return ""
        clean = str(s).replace("\\/", "/").strip()
        decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), clean)
        try:
            return urllib.parse.quote(urllib.parse.unquote(decoded), safe=";/?:@&=+$,-_.!~*'()#")
        except Exception:
            return decoded

    def _clean_img(self, raw_url):
        if not raw_url:
            return ""
        raw = str(raw_url).strip().replace("&amp;", "&")
        if "baidu.com" in raw:
            sm = re.search(r"src=([^&]+)", raw)
            if sm:
                try:
                    real = urllib.parse.unquote(sm.group(1))
                except Exception:
                    real = sm.group(1)
                if not real.startswith("http"):
                    real = "https://" + real.lstrip("/")
                return "https://gimg0.baidu.com/gimg/app=2001&n=0&g=0n&fmt=jpeg&src=" + urllib.parse.quote(real, safe="")
            return raw
        if raw.startswith("//"):
            full = "https:" + raw
        elif raw.startswith("/"):
            full = self.host + raw
        else:
            full = raw
        if not full.startswith("http"):
            full = "https://" + full
        return "https://gimg0.baidu.com/gimg/app=2001&n=0&g=0n&fmt=jpeg&src=" + urllib.parse.quote(full, safe="")

    def _parse_cards(self, html_text):
        items = []
        seen = set()
        for m in self.CARD_RE.finditer(str(html_text or "")):
            vid, chunk = m.group(1).strip(), m.group(0)
            if not vid or vid in seen:
                continue
            title = ""
            tm = re.search(r'title=["\']([^"\']+)["\']', chunk, re.I)
            if tm and tm.group(1).strip() != "大米星球":
                title = tm.group(1).strip()
            if not title:
                am = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', chunk, re.I)
                if am and am.group(1).strip() != "大米星球":
                    title = am.group(1).strip()
            if not title or title == "大米星球":
                continue
            pic = ""
            pm = (re.search(r'data-original=["\']([^"\']+)["\']', chunk, re.I) or
                  re.search(r'data-src=["\']([^"\']+)["\']', chunk, re.I) or
                  re.search(r'src=["\']([^"\']+)["\']', chunk, re.I))
            if pm:
                p = pm.group(1).strip()
                if not any(k in p.lower() for k in self.BAD_PIC_KEYWORDS):
                    pic = self._clean_img(p)
            remarks = "分享者影视"
            sm = re.search(r"<span[^>]*>([\s\S]*?)</span>", chunk, re.I)
            if sm:
                raw_rem = self._strip(sm.group(1))
                if raw_rem:
                    remarks = "分享者影视" + raw_rem
            seen.add(vid)
            items.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
                "style": {"type": "rect", "ratio": 0.71},
            })
        return items

    def _filter_rows(self, class_opts):
        def opts(values):
            return [{"n": (v if v else "全部"), "v": v} for v in values]
        return [
            {"key": "class", "name": "类型", "value": opts(class_opts)},
            {"key": "area", "name": "地区", "value": opts(self.AREA)},
            {"key": "lang", "name": "语言", "value": opts(self.LANG)},
            {"key": "year", "name": "年份", "value": opts(self.YEARS)},
            {"key": "by", "name": "排序", "value": [{"n": n, "v": v} for v, n in self.COMMON_BY]},
        ]

    # ---------- entries ----------
    def homeContent(self, filter=False):
        classes = [{"type_id": cid, "type_name": name} for cid, name in self.CLASSES]
        result = {"class": classes}
        if filter:
            result["filters"] = {
                "20": self._filter_rows(self.CLASS_MOVIE),
                "21": self._filter_rows(self.CLASS_TV),
            }
        return result

    def homeVideoContent(self):
        html_text = self._fetch(self.host + "/vodshow/20--------1---.html")
        return {"list": self._parse_cards(html_text)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        ext = extend if isinstance(extend, dict) else {}
        cid = str(tid or "20")
        if cid == "today":
            url = self.host + "/label/week.html"
        elif cid == "netflix":
            url = self.host + "/vodshow/20---Netflix-----" + str(page) + "---.html"
        else:
            c_by = str(ext.get("by") or "")
            c_class = str(ext.get("class") or "")
            c_area = str(ext.get("area") or "")
            url_class = urllib.parse.quote(c_class, safe="") if c_class else ""
            url_area = urllib.parse.quote(c_area, safe="") if c_area else ""
            if not (url_area or url_class or c_by):
                url = self.host + "/vodshow/" + cid + "--------" + str(page) + "---.html"
            else:
                url = self.host + "/vodshow/" + cid + "-" + url_area + "-" + c_by + "-" + url_class + "-----" + str(page) + "---.html"
        html_text = self._fetch(url)
        items = self._parse_cards(html_text)
        return {"list": items, "page": page, "pagecount": page + 1 if items else page, "limit": len(items), "total": len(items)}

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        keyword = str(key or "").strip()
        if not keyword:
            return {"list": [], "page": page, "pagecount": page, "limit": 0, "total": 0}
        url = self.host + "/vodsearch/" + urllib.parse.quote(keyword, safe="") + "----------" + str(page) + "---.html"
        html_text = self._fetch(url)
        items = self._parse_cards(html_text)
        return {"list": items, "page": page, "pagecount": page + 1 if items else page, "limit": len(items), "total": len(items)}

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = re.sub(r"\D", "", str(ids[0] or ""))
        if not vid:
            return {"list": []}
        detail_url = self.host + "/voddetail/" + vid + ".html"
        html_text = self._fetch(detail_url)
        h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html_text, re.I)
        vod_name = self._strip(h1.group(1)) if h1 else ""
        vod_pic = ""
        pm = (re.search(r'class=["\'][^"\']*detail-pic["\'][\s\S]*?<img[^>]+src=["\']([^"\']+)["\']', html_text, re.I) or
              re.search(r'<img[^>]+class=["\'][^"\']*lazy[^"\']*["\'][^>]+data-original=["\']([^"\']+)["\']', html_text, re.I))
        if pm:
            vod_pic = self._clean_img(pm.group(1).strip())
        desc = ""
        dm = re.search(r'<div[^>]+class=["\'][^"\']*content[^"\']*["\'][^>]*>([\s\S]*?)</div>', html_text, re.I)
        if dm:
            desc = self._strip(dm.group(1))
        tab_names = [self._strip(x) for x in re.findall(r'<div[^>]+class=["\'][^"\']*module-tab-item[^"\']*["\'][^>]*>[\s\S]*?<span>([\s\S]*?)</span>', html_text, re.I)]
        if not tab_names:
            tab_names = [self._strip(x) for x in re.findall(r'<a[^>]+data-toggle=["\']tab["\'][^>]*>([\s\S]*?)</a>', html_text, re.I)]
        play_lists = re.findall(r'<div[^>]+class=["\'][^"\']*module-play-list[^"\']*["\']>([\s\S]*?)</div>', html_text, re.I)
        if not play_lists:
            play_lists = re.findall(r'<ul[^>]+class=["\'][^"\']*playlist[^"\']*["\']>([\s\S]*?)</ul>', html_text, re.I)
        froms = []
        play_urls = []
        for i, plist in enumerate(play_lists):
            line_name = tab_names[i] if i < len(tab_names) and tab_names[i] else ("线路 " + str(i + 1))
            eps = []
            for em in self.EP_RE.finditer(plist):
                play_id = em.group(1).strip()
                ep_name = self._strip(em.group(2)) or ("第 " + str(len(eps) + 1) + " 集")
                val = json.dumps({"playId": play_id}, ensure_ascii=False)
                eps.append(ep_name + "$" + val)
            if eps:
                froms.append(line_name)
                play_urls.append("#".join(eps))
        if not froms:
            froms = ["大米星球"]
            play_urls = ["正片$" + json.dumps({"playId": vid + "-1-1"}, ensure_ascii=False)]
        lines = [
            "分享者在线",
            "导演：分享者在线",
            "当前主站：" + self.host,
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "━━━━━━━",
        ]
        if desc:
            lines.append(desc)
        else:
            lines.append("标题：" + (vod_name or "影视详情"))
            lines.append("片源：大米星球")
            lines.append("编号：" + vid)
        vod = {
            "vod_id": vid,
            "vod_name": vod_name or "影视详情",
            "vod_pic": vod_pic,
            "vod_remarks": "分享者影视",
            "vod_actor": "分享者在线",
            "vod_director": "分享者影视",
            "vod_content": "\n".join(lines),
            "vod_class": "影视专区",
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(play_urls),
            "style": {"type": "rect", "ratio": 0.71},
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        play_id = ""
        try:
            data = json.loads(id)
            if isinstance(data, dict):
                play_id = str(data.get("playId") or "").strip()
        except Exception:
            pass
        if not play_id:
            play_id = str(id or "").strip()
        play_page = self.host + "/vodplay/" + play_id + ".html"
        headers = {"User-Agent": self.UA, "Referer": self.host + "/"}
        html_text = self._fetch(play_page)
        real_url = ""
        um = re.search(r'var\s+player_aaaa\s*=\s*\{[\s\S]*?["\']url["\']\s*:\s*["\']([^"\']+)["\']', html_text, re.I)
        if um:
            real_url = self._decode_unicode_url(um.group(1))
            em = re.search(r'["\']encrypt["\']\s*:\s*(\d+)', html_text, re.I)
            if em:
                enc = em.group(1)
                if enc == "1":
                    try:
                        real_url = urllib.parse.unquote(real_url)
                    except Exception:
                        pass
                elif enc == "2":
                    try:
                        real_url = self._decode_unicode_url(base64.b64decode(real_url).decode("utf-8", "replace"))
                    except Exception:
                        pass
        else:
            jm = re.search(r"var\s+player_aaaa\s*=\s*(\{[\s\S]*?\});", html_text, re.I)
            if jm:
                try:
                    pdata = json.loads(jm.group(1))
                    if isinstance(pdata, dict) and pdata.get("url"):
                        real_url = self._decode_unicode_url(str(pdata["url"]))
                except Exception:
                    pass
        if real_url:
            lower = real_url.lower()
            if ".m3u8" in lower or ".mp4" in lower or ".flv" in lower:
                if any(d in lower for d in self.BAD_SSL_DOMAINS) and real_url.startswith("https://"):
                    real_url = "http://" + real_url[8:]
                if ".m3u8" not in real_url.lower():
                    real_url += ("&" if "?" in real_url else "?") + "format=.m3u8"
                return {"parse": 0, "playUrl": "", "url": real_url, "header": headers}
            return {"parse": 1, "playUrl": "", "url": real_url, "header": headers}
        return {"parse": 1, "playUrl": "", "url": play_page, "header": headers}

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

# --- System Signature ---
#‍​​‌‌​‌​‌​​‌‌​‌‌​​​‌‌​​‌​​​‌‌​​‌‌​​‌‌​‌‌​​​‌‌​‌​‌​​‌‌‌​​‌​​‌‌​​​‌​​‌‌​​‌​​​‌‌​​‌​‍



# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = ["极速蓝光", "极速蓝光- M", "极速蓝光- js", "极速蓝光-R", "极速蓝光-b", "极速蓝光-f", "极速蓝光-j", "极速蓝光-s", "极速高清", "超清蓝光-3"]
_TVBOX_LINE_ORDER = ["超清蓝光-3", "极速蓝光-R", "极速蓝光-b", "极速蓝光"]

_TVBOX_ZY_ENABLED = True
_TVBOX_ZY_CDN = ["ffzy", "feifei", "yzzy", "cdnlz", "lzzy", "bfzy", "rrcdnbf", "fengbao", "ffvip", "7bbffvip", "modujx", "modudm", "mujizybf", "jisuzy", "jisuzyv", "zuidazy", "wsyzym3u8", "xluuss", "bfvvs", "dytt", "phimgood", "ryiplay", "ryplay", "ruyijx", "gsuus", "guangsuzy", "maowushi", "ukuzi", "niuniuzy", "rstu6", "mzm3u8", "ppqrrs", "qqqrst", "hhuus"]
_TVBOX_ZY_API = "/api\\.php/(provide|providedown)|/inc/api_mac|provide/vod|providedown/vod"
_TVBOX_ZY_CODES = ["BD", "BF", "FF", "HH", "HN", "JS", "JY", "KC", "LZ", "MT", "MY", "NN", "SD", "SN", "UK", "WJ", "XL", "YZ"]
_TVBOX_ZY_KW = ["量子", "非凡", "暴风", "魔都", "极速", "最大", "蜗牛", "影库", "红牛", "新浪", "光速", "如意", "卧龙", "无界", "人尽", "牛牛", "猫屋", "电影天堂", "天堂", "4K资源", "索尼"]
_TVBOX_ZY_NEG = ["官方", "自营", "自有", "正版"]

def _tvbox_is_zy_url(url, flag=''):
    import re, urllib.parse
    u = str(url or '')
    f = str(flag or '').strip()
    if re.search(_TVBOX_ZY_API, u, re.I):
        return True
    # 播放地址可能是多集拼接串：'第01集$https://a.com/x.m3u8#第02集$https://b.com/y.m3u8'
    # 必须逐段提取 URL 再取 host，不能对整个串 urlparse（取不到 host）。
    hosts = set()
    for seg in re.split(r'[#$]', u):
        seg = seg.strip()
        if seg.startswith('http://') or seg.startswith('https://'):
            try:
                parsed = urllib.parse.urlparse(seg)
                h = (parsed.hostname or '').lower()
            except Exception:
                h = ''; parsed = None
            # 本地代理型脚本（如 APP影院1）：真实地址藏在 url= 参数里，
            # 需解码后再提取 host，否则只会拿到 127.0.0.1 而漏判。
            if parsed and h in ('127.0.0.1', 'localhost', '::1'):
                qs = urllib.parse.parse_qs(parsed.query)
                real = (qs.get('url') or [''])[0]
                if real.startswith('//'): real = 'https:' + real
                if real.startswith('http://') or real.startswith('https://'):
                    try:
                        rh = (urllib.parse.urlparse(real).hostname or '').lower()
                    except Exception:
                        rh = ''
                    if rh: hosts.add(rh)
            if h:
                hosts.add(h)
            # 中转缓存型：真实 URL 拼在路径里（/cache/https://cdn/...），
            # 取内层 host（如 47电影天堂 dl.gybkw.com/cache/https://c1.7bbffvip.com）。
            im = re.search(r'/(https?://[^/?#]+)', seg)
            if im:
                ih = re.match(r'https?://([^/?]+)', im.group(1))
                if ih:
                    hosts.add(ih.group(1).split(':')[0].lower())
    for h in hosts:
        for p in _TVBOX_ZY_CDN:
            if re.search(r'(^|[.\-_])' + re.escape(p), h, re.I):
                return True
        if re.search(r'(^|[.\-_])lzv\d+', h, re.I):
            return True
    if hosts:
        return False  # 有真实 host 但没命中 CDN → 自有线路，不靠名字
    # 无 host（占位符型脚本，detail 给相对路径/id）：回退到线路名判定。
    # 官方/自营字样优先豁免，避免误伤。
    if any(neg in f for neg in _TVBOX_ZY_NEG):
        return False
    if f.upper() in _TVBOX_ZY_CODES:
        return True
    if any(kw in f for kw in _TVBOX_ZY_KW):
        return True
    if re.search(r'(?i)\b(LZ|FF|BF|HF|HN|YZ|DY|MY)(?:线路|线)', f):
        return True
    return False

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
    if _TVBOX_ZY_ENABLED:
        keep = [(f, u) for f, u in zip(parts_from, parts_url)
                if f not in drop and not _tvbox_is_zy_url(u, f)]
    else:
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
