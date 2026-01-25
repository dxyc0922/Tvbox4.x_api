import re
import json
import requests
from lxml import etree
from abc import abstractmethod, ABCMeta


class Spider(metaclass=ABCMeta):
    _instance = None

    def __init__(self):
            self.extend = ''

    def __new__(cls, *args, **kwargs):
        if cls._instance:
            return cls._instance
        else:
            cls._instance = super().__new__(cls)
            return cls._instance

    @abstractmethod
    def init(self, extend=""):
        pass

    def homeContent(self, filter):
        pass

    def homeVideoContent(self):
        pass

    def categoryContent(self, tid, pg, filter, extend):
        pass

    def detailContent(self, ids):
        pass

    def searchContent(self, key, quick, pg="1"):
        pass

    def playerContent(self, flag, id, vipFlags):
        pass

    def liveContent(self, url):
        pass

    def localProxy(self, param):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def action(self, action):
        pass

    def destroy(self):
        pass

    def getName(self):
        pass

    def getDependence(self):
        return []

    def regStr(self, reg, src, group=1):
        m = re.search(reg, src)
        src = ''
        if m:
            src = m.group(group)
        return src

    def removeHtmlTags(self, src):
        clean = re.compile('<.*?>')
        return re.sub(clean, '', src)

    def cleanText(self, src):
        clean = re.sub('[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', src)
        return clean

    def fetch(self, url, params=None, cookies=None, headers=None, timeout=5, verify=True, stream=False, allow_redirects = True):
        rsp = requests.get(url, params=params, cookies=cookies, headers=headers, timeout=timeout, verify=verify, stream=stream, allow_redirects=allow_redirects)
        rsp.encoding = 'utf-8'
        return rsp

    def post(self, url, params=None, data=None, json=None, cookies=None, headers=None, timeout=5, verify=True, stream=False, allow_redirects = True):
        rsp = requests.post(url, params=params, data=data, json=json, cookies=cookies, headers=headers, timeout=timeout, verify=verify, stream=stream, allow_redirects=allow_redirects)
        rsp.encoding = 'utf-8'
        return rsp

    def html(self, content):
        return etree.HTML(content)

    def str2json(str):
        return json.loads(str)

    def json2str(str):
        return json.dumps(str, ensure_ascii=False)
    
    def log(self, msg):
        if isinstance(msg, dict) or isinstance(msg, list):
            print(json.dumps(msg, ensure_ascii=False))
        else:
            print(f'{msg}')

    def getCache(self, key):
        import os
        import json
        import time
        
        cache_file = f'cache_{key}.json'
        if not os.path.exists(cache_file):
            return None
            
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                value = f.read()
                
            if len(value) > 0:
                if value.startswith('{') and value.endswith('}') or value.startswith('[') and value.endswith(']'):
                    value = json.loads(value)
                    if type(value) == dict:
                        if not 'expiresAt' in value or value['expiresAt'] >= int(time.time()):
                            return value
                        else:
                            self.delCache(key)
                            return None
                return value
            else:
                return None
        except Exception:
            return None

    def setCache(self, key, value):
        import os
        import json
        
        cache_file = f'cache_{key}.json'
        
        if type(value) in [int, float]:
            value = str(value)
        if len(value) > 0:
            if type(value) == dict or type(value) == list:
                value = json.dumps(value, ensure_ascii=False)
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(value)
            return 'succeed'
        except Exception as e:
            return 'failed'

    def delCache(self, key):
        import os
        
        cache_file = f'cache_{key}.json'
        try:
            if os.path.exists(cache_file):
                os.remove(cache_file)
            return 'succeed'
        except Exception as e:
            return 'failed'
