import re
import json
import time
import requests
from lxml import etree
from abc import abstractmethod, ABCMeta


class Spider(metaclass=ABCMeta):
    _instance = None

    def __init__(self):
        self.extend = ""

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
        src = ""
        if m:
            src = m.group(group)
        return src

    def removeHtmlTags(self, src):
        clean = re.compile("<.*?>")
        return re.sub(clean, "", src)

    def cleanText(self, src):
        clean = re.sub(
            "[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff\U0001f1e0-\U0001f1ff]",
            "",
            src,
        )
        return clean

    def fetch(
        self,
        url,
        params=None,
        cookies=None,
        headers=None,
        timeout=5,
        verify=True,
        stream=False,
        allow_redirects=True,
    ):
        rsp = requests.get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            timeout=timeout,
            verify=verify,
            stream=stream,
            allow_redirects=allow_redirects,
        )
        rsp.encoding = "utf-8"
        return rsp

    def post(
        self,
        url,
        params=None,
        data=None,
        json=None,
        cookies=None,
        headers=None,
        timeout=5,
        verify=True,
        stream=False,
        allow_redirects=True,
    ):
        rsp = requests.post(
            url,
            params=params,
            data=data,
            json=json,
            cookies=cookies,
            headers=headers,
            timeout=timeout,
            verify=verify,
            stream=stream,
            allow_redirects=allow_redirects,
        )
        rsp.encoding = "utf-8"
        return rsp

    def html(self, content):
        return etree.HTML(content)

    def str2json(str):
        return json.loads(str)

    def json2str(str):
        return json.dumps(str, ensure_ascii=False)

    def getProxyUrl(self, local=True):
        return f"http://127.0.0.1:9098?do=py"

    def log(self, msg):
        if isinstance(msg, dict) or isinstance(msg, list):
            print(json.dumps(msg, ensure_ascii=False))
        else:
            print(f"{msg}")

    def getCache(self, key):
        if hasattr(self, '_memory_cache'):
            if key in self._memory_cache:
                entry = self._memory_cache[key]
                if time.time() < entry['expires_at']:
                    return entry['value']
                else:
                    # 删除过期的缓存
                    del self._memory_cache[key]
        return None

    def setCache(self, key, value):
        if not hasattr(self, '_memory_cache'):
            self._memory_cache = {}
        
        # 默认7天过期时间（604800秒）
        expires_at = time.time() + 604800
        
        # 处理值的类型
        if isinstance(value, (dict, list)):
            import copy
            value = copy.deepcopy(value)  # 深拷贝避免后续修改影响缓存
        
        self._memory_cache[key] = {
            'value': value,
            'expires_at': expires_at
        }
        return "succeed"

    def delCache(self, key):
        if hasattr(self, '_memory_cache') and key in self._memory_cache:
            del self._memory_cache[key]
        return "succeed"
