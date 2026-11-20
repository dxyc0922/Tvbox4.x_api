# -*- coding: utf-8 -*-
# by @嗷呜
import json
import sys
import time
import requests
from base64 import b64decode, b64encode
from Crypto.Hash import MD5
from pyquery import PyQuery as pq
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):

    def init(self, extend=""):
        pass

    def getName(self):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    host='http://v.rbotv.cn'

    headers = {
        'User-Agent': 'okhttp-okgo/jeasonlzy',
        'Accept-Language': 'zh-CN,zh;q=0.8'
    }

    def homeContent(self, filter):
        data=requests.post(f'{self.host}/v3/type/top_type',headers=self.headers,files=self.getfiles({'': (None, '')})).json()
        result = {}
        classes = []
        filters = {}
        for k in data['data']['list']:
            classes.append({
                'type_name': k['type_name'],
                'type_id': k['type_id']
            })
            fts = []
            for i,x in k.items():
                if isinstance(x, list) and len(x)>2:
                    fts.append({
                        'name': i,
                        'key': i,
                        'value': [{'n': j, 'v': j} for j in x if j and j!= '全部']
                    })
            if len(fts):filters[k['type_id']] = fts
        result['class'] = classes
        result['filters'] = filters
        return result

    def homeVideoContent(self):
        data=requests.post(f'{self.host}/v3/type/tj_vod',headers=self.headers,files=self.getfiles({'': (None, '')})).json()
        return {'list':self.getv(data['data']['cai']+data['data']['loop'])}

    def categoryContent(self, tid, pg, filter, extend):
        files = {
            'type_id': (None, tid),
            'limit': (None, '12'),
            'page': (None, pg)
        }
        for k,v in extend.items():
            if k=='extend':k='class'
            files[k] = (None, v)
        data=requests.post(f'{self.host}/v3/home/type_search',headers=self.headers,files=self.getfiles(files)).json()
        result = {}
        result['list'] = self.getv(data['data']['list'])
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self, ids):
        data=requests.post(f'{self.host}/v3/home/vod_details',headers=self.headers,files=self.getfiles({'vod_id': (None, ids[0])})).json()
        v=data['data']
        vod = {
            'vod_name': v.get('vod_name'),
            'type_name': v.get('type_name'),
            'vod_year': v.get('vod_year'),
            'vod_area': v.get('vod_area'),
            'vod_remarks': v.get('vod_remarks'),
            'vod_actor': v.get('vod_actor'),
            'vod_director': v.get('vod_director'),
            'vod_content': pq(pq(v.get('vod_content','无') or '无').text()).text()
        }
        n,p=[],[]
        for o,i in enumerate(v['vod_play_list']):
            n.append(f"线路{o+1}({i.get('flag')})")
            c=[]
            for j in i.get('urls'):
                d={'url':j.get('url'),'p':i.get('parse_urls'),'r':i.get('referer'),'u':i.get('ua')}
                c.append(f"{j.get('name')}${self.e64(json.dumps(d))}")
            p.append('#'.join(c))
        vod.update({'vod_play_from':'$$$'.join(n),'vod_play_url':'$$$'.join(p)})
        return {'list':[vod]}

    def searchContent(self, key, quick, pg="1"):
        files = {
            'limit': (None, '12'),
            'page': (None, pg),
            'keyword': (None, key),
        }
        data=requests.post(f'{self.host}/v3/home/search',headers=self.headers,files=self.getfiles(files)).json()
        return {'list':self.getv(data['data']['list']),'page':pg}

    def playerContent(self, flag, id, vipFlags):
        ids=json.loads(self.d64(id))
        url=ids['url']
        if isinstance(ids['p'],list) and len(ids['p']):
            url=[]
            for i,x in enumerate(ids['p']):
                up={'url':ids['url'],'p':x,'r':ids['r'],'u':ids['u']}
                url.extend([f"解析{i+1}",f"{self.getProxyUrl()}&data={self.e64(json.dumps(up))}"])
        h={}
        if ids.get('r'):
            h['Referer'] = ids['r']
        if ids.get('u'):
            h['User-Agent'] = ids['u']
        return  {'parse': 0, 'url': url, 'header': h}

    def localProxy(self, param):
        data=json.loads(self.d64(param['data']))
        h = {}
        if data.get('r'):
            h['Referer'] = data['r']
        if data.get('u'):
            h['User-Agent'] = data['u']
        res=self.fetch(f"{data['p']}{data['url']}",headers=h).json()
        url=res.get('url') or res['data'].get('url')
        return [302,'video/MP2T',None,{'Location':url}]

    def liveContent(self, url):
        pass

    def getfiles(self, p=None):
        if p is None:p = {}
        t=str(int(time.time()))
        h = MD5.new()
        h.update(f"7gp0bnd2sr85ydii2j32pcypscoc4w6c7g5spl{t}".encode('utf-8'))
        s = h.hexdigest()
        files = {
            'sign': (None, s),
            'timestamp': (None, t)
        }
        p.update(files)
        return p

    def getv(self,data):
        videos = []
        for i in data:
            if i.get('vod_id') and str(i['vod_id']) != '0':
                videos.append({
                    'vod_id': i['vod_id'],
                    'vod_name': i.get('vod_name'),
                    'vod_pic': i.get('vod_pic') or i.get('vod_pic_thumb'),
                    'vod_year': i.get('tag'),
                    'vod_remarks': i.get('vod_remarks')
                })
        return videos

    def e64(self, text):
        try:
            text_bytes = text.encode('utf-8')
            encoded_bytes = b64encode(text_bytes)
            return encoded_bytes.decode('utf-8')
        except Exception as e:
            return ""

    def d64(self,encoded_text):
        try:
            encoded_bytes = encoded_text.encode('utf-8')
            decoded_bytes = b64decode(encoded_bytes)
            return decoded_bytes.decode('utf-8')
        except Exception as e:
            return ""



# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = ["线路2(lz)", "线路3(ff)", "线路4(bf)"]
_TVBOX_LINE_ORDER = ["线路3(ff)", "线路2(lz)", "线路1(nby)", "线路4(bf)"]

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
