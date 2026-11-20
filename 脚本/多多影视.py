# -*- coding: utf-8 -*-
import sys, re, time, json, hashlib, base64
from urllib.parse import quote
sys.path.append('..')
try:
    from base.spider import Spider
except:
    class Spider: pass

HOSTS = ['https://323433ssdfd.top', 'https://duoduosdf12223234334.top', 'https://xds2435u23422342342u.top', 'https://dduotv01.top']
HOST = HOSTS[0]
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'
F = 'WF-2c064bc5b3400788f31b848849bc3a60f835423ba2dfe69d7ea93974c216e4f2'
SK = 'WEB-50a8e9c84a1dc05669a692ded99a2dac46527229e607a7be15db88dbc59059d1'
ID = 'com.web.player'
W = 'ddtvf65f3a83d6d9ad6f'
XC = '8f3d2a1c7b6e5d4c9a0b1f2e3d4c5b6a'
CATEGORIES = [{'type_id': '1', 'type_name': '电影'}, {'type_id': '2', 'type_name': '剧集'}, {'type_id': '3', 'type_name': '动漫'}, {'type_id': '4', 'type_name': '综艺'}]

def _vint(n):
    out = b''
    while True:
        b = n & 0x7f
        n >>= 7
        if n:
            out += bytes([b | 0x80])
        else:
            out += bytes([b])
            break
    return out

def _pb(url, vf, ts):
    sig = hashlib.sha256(('finger=%s&id=%s&nonce=%s&sk=%s&time=%s&v=1' % (F, ID, '0' * 32, SK, ts)).encode()).hexdigest().upper()
    b = b'\x0a' + _vint(len(url)) + url.encode()
    b += b'\x12' + _vint(len(vf)) + vf.encode()
    b += b'\x18' + _vint(ts)
    b += b'\x22' + _vint(32) + b'0' * 32
    b += b'\x2a' + _vint(64) + sig.encode()
    b += b'\x32' + _vint(14) + b'com.web.player'
    b += b'\x38\x01'
    return b

def _parse_pb(b):
    i, fields = 0, {}
    while i < len(b):
        tag = b[i]; i += 1
        f = tag >> 3; w = tag & 7
        if w == 0:
            v = 0; s = 0
            while True:
                x = b[i]; i += 1
                v |= (x & 0x7f) << s
                if not x & 0x80: break
                s += 7
            fields[f] = v
        elif w == 2:
            ln = 0; s2 = 0
            while True:
                x = b[i]; i += 1
                ln |= (x & 0x7f) << s2
                if not x & 0x80: break
                s2 += 7
            fields[f] = b[i:i + ln].decode('utf-8', errors='replace')
            i += ln
        elif w == 5:
            i += 4
    return fields

class Spider(Spider):
    def __init__(self):
        self.h = {'web-sign': W, 'X-Client': XC, 'User-Agent': UA}
        self._host = HOST

    def init(self, extend=""):
        self.__init__()

    def _fetch(self, url, params=None, headers=None, data=None, method='GET'):
        hosts = [self._host] + [h for h in HOSTS if h != self._host]
        for host in hosts:
            u = url.replace(HOST, host, 1) if HOST in url else url
            try:
                import requests
                kw = dict(timeout=6, verify=False)
                if method == 'POST':
                    r = requests.post(u, params=params, headers=headers, data=data, **kw)
                else:
                    r = requests.get(u, params=params, headers=headers, **kw)
                if r.status_code == 200:
                    self._host = host
                    return r.content
            except Exception:
                pass
            try:
                import urllib.request, ssl
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                if params:
                    u += ('&' if '?' in u else '?') + '&'.join('%s=%s' % (k, quote(str(v))) for k, v in params.items())
                req = urllib.request.Request(u, data=data, headers=headers or {})
                r = urllib.request.urlopen(req, timeout=6, context=ctx)
                self._host = host
                return r.read()
            except Exception:
                pass
        return b''

    def _get(self, path, params=None):
        for _ in range(2):
            r = self._fetch(HOST + path, params=params, headers=self.h)
            if r:
                try:
                    return json.loads(r)
                except Exception:
                    pass
            time.sleep(0.3)
        return {}

    def _norm(self, v):
        return {'vod_id': v.get('vod_id'), 'vod_name': v.get('vod_name'), 'vod_pic': v.get('vod_pic'), 'vod_remarks': v.get('vod_remarks')}

    def homeContent(self, filter=False):
        j = self._get('/api.php/web/index/home')
        d = j.get('data') or {}
        cats = []
        vids = []
        for c in d.get('categories') or []:
            cats.append({'type_id': str(c.get('type_id')), 'type_name': c.get('type_name')})
            for v in c.get('videos') or []:
                vids.append(self._norm(v))
        return {'class': cats, 'list': vids}

    def homeVideoContent(self):
        j = self._get('/api.php/web/index/home')
        d = j.get('data') or {}
        vids = []
        for c in d.get('categories') or []:
            for v in c.get('videos') or []:
                vids.append(self._norm(v))
        return {'list': vids}

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        name = next((c['type_name'] for c in CATEGORIES if c['type_id'] == str(tid)), '电影')
        j = self._get('/api.php/web/filter/vod', {'type_name': name, 'page': pg, 'sort': 'hits'})
        data = j.get('data') or []
        vids = [self._norm(v) for v in data]
        return {'list': vids, 'page': pg, 'pagecount': 9999, 'limit': 18, 'total': 9999}

    def detailContent(self, ids):
        j = self._get('/api.php/web/vod/get_detail', {'vod_id': ids[0]})
        d = (j.get('data') or [{}])[0]
        v = {'vod_id': d.get('vod_id'), 'vod_name': d.get('vod_name'), 'vod_pic': d.get('vod_pic'),
             'type_name': d.get('type_name'), 'vod_year': d.get('vod_year'), 'vod_area': d.get('vod_area'),
             'vod_remarks': d.get('vod_remarks'), 'vod_actor': d.get('vod_actor'), 'vod_director': d.get('vod_director'),
             'vod_content': d.get('vod_content'), 'vod_play_from': d.get('vod_play_from'), 'vod_play_url': d.get('vod_play_url')}
        return {'list': [v]}

    def searchContent(self, key, quick=False, pg='1'):
        j = self._get('/api.php/web/search/index', {'wd': key, 'page': pg, 'limit': 15})
        data = j.get('data') or []
        return {'list': [self._norm(v) for v in data]}

    def playerContent(self, flag, id, vipFlags=None):
        ts = int(time.time() * 1000)
        body = _pb(id, flag, ts)
        h = dict(self.h)
        h['Content-Type'] = 'application/x-protobuf'
        h['Accept'] = 'application/x-protobuf'
        for _ in range(2):
            try:
                r = self._fetch(HOST + '/api.php/web/decode/url', headers=h, data=body, method='POST')
                fields = _parse_pb(r)
                if fields.get(1) == 1 and fields.get(3):
                    return {'parse': 0, 'url': fields[3]}
            except Exception:
                pass
            time.sleep(0.3)
        return {}

    def destroy(self):
        pass



# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = []
_TVBOX_LINE_ORDER = ["zijianm3u8", "CO4K", "NBY", "PAN1"]

_TVBOX_ZY_ENABLED = True
_TVBOX_ZY_CDN = ["ffzy", "feifei", "yzzy", "cdnlz", "lzzy", "lzcdn", "bfzy", "rrcdnbf", "fengbao", "ffvip", "7bbffvip", "modujx", "modudm", "mujizybf", "jisuzy", "jisuzyv", "zuidazy", "wsyzym3u8", "xluuss", "bfvvs", "dytt", "phimgood", "ryiplay", "ryplay", "ruyijx", "gsuus", "guangsuzy", "maowushi", "ukuzi", "niuniuzy", "rstu6", "mzm3u8", "ppqrrs", "qqqrst", "hhuus", "bdzybf", "bfikuncdn", "wlcdn88", "dious", "ly166", "xgplay13", "taopianplay", "kuktxu", "2767.org", "892539"]
_TVBOX_ZY_API = "/api\\.php/(provide|providedown)|/inc/api_mac|provide/vod|providedown/vod"
_TVBOX_ZY_CODES = ["BD", "BF", "FF", "HH", "HN", "IK", "IQY", "JS", "JY", "KC", "LZ", "MT", "MY", "MZ", "NN", "PL", "RY", "SD", "SN", "TK", "UK", "WJ", "WL", "XL", "YZ"]
_TVBOX_ZY_KW = ["量子", "非凡", "暴风", "魔都", "极速", "最大", "蜗牛", "影库", "红牛", "新浪", "光速", "如意", "卧龙", "无界", "人尽", "牛牛", "猫屋", "电影天堂", "天堂", "4K资源", "索尼", "无尽", "魔爪", "猫眼", "快车", "百度", "ikun", "速播", "站外", "西瓜", "淘宝片", "天空", "卧龙", "拍律", "xiguam3u8", "ikm3u8", "tpm3u8", "rym3u8", "taopian"]
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
    if re.search(r'(?i)\b(LZ|FF|BF|HF|HN|YZ|DY|MY|IK|WL|TK|IQY|XL|WJ|BD|DB|SB|SN|MZ|PL)(?:线路|线)', f):
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
