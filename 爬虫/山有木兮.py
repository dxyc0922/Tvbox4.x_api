"""
脚本说明：脚本仅用于学习,限制了请求和内容缓存，如若侵犯你的权益请联系删除
请勿用于商业用途，请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任
"""

import sys
import time
import random

sys.path.append("..")
from base.spider import Spider


class Spider(Spider):  # 继承基类Spider，实现具体的脚本逻辑
    def init(self, extend=""):  # 初始化脚本的基本配置信息
        self.name = "山有木兮"  # 脚本名称
        # API接口地址，用于获取搜索结果
        self.api = "https://film.symx.club"
        # 用户代理字符串，模拟浏览器访问
        self.user_agent = [
            # Chrome - Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            # Chrome - macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            # Chrome - Linux
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # Firefox - Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
            # Firefox - macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
            # Firefox - Linux
            "Mozilla/5.0 (X11; Linux i686; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
            # Safari - iOS
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
            # Safari - macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            # Edge - Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
            # Samsung Browser - Android
            "Mozilla/5.0 (Linux; Android 10; SAMSUNG SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.5790.166 Mobile Safari/537.36",
            # Chrome - Android
            "Mozilla/5.0 (Linux; Android 10; Pixel 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
            # Opera - Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/105.0.0.0",
        ]
        # 请求头信息，模拟正常浏览器访问网站
        self.header = {
            "Accept": "application/json",  # 接收的数据格式
            "referer": f"{self.api}/index",  # 请求的来源
            "x-platform": "web",  # 网站要求提供平台来源
        }
        # 添加标志以追踪是否为首次请求,非首次请求时，添加随机延迟,防止对网站的访问频率过快
        self.first_request = True

        # 缓存时间配置（单位：秒）,首次请求后,对常用请求内容进行缓存,避免浪费网络资源
        self.cache_times = {
            # 天*时*分*秒
            "home_category": 7 * 24 * 3600,  # 首页分类信息，7天
            "home_video": 1 * 24 * 3600,  # 首页推荐视频，1天
            "category": 1 * 1 * 10 * 60,  # 分类内容，10分钟
        }

    def getName(self):  # 获取脚本名称的方法
        return self.name

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
        # 如果不是第一次请求，则添加随机延迟 0.5-2 秒
        if not self.first_request:
            delay = random.uniform(0.5, 2.0)
            time.sleep(delay)
        else:
            # 第一次请求后将标志设为False
            self.first_request = False
        # 调用父类的 fetch 方法
        return super().fetch(
            url, params, cookies, headers, timeout, verify, stream, allow_redirects
        )

    def getRandomHeader(self):
        """获取带有随机user-agent的请求头"""
        headers = self.header.copy()
        headers["User-Agent"] = random.choice(self.user_agent)
        return headers

    def searchContent(self, key, quick, pg="1"):
        """搜索指定视频内容"""
        try:
            url = f"{self.api}/api/film/search"
            params = {
                "keyword": key,
                "pageNum": pg,
                "pageSize": "10",
            }
            self.log(f"搜索开始: {url}, params: {params}")
            # 发送请求获取数据
            rsp = self.fetch(
                url=url,
                params=params,
                headers=self.getRandomHeader(),
            ).json()
            self.log(f"搜索成功: {rsp}")
            video_list = []
            for item in rsp["data"]["list"]:
                video_list.append(
                    {
                        "vod_id": item.get("id", ""),
                        "vod_name": item.get("name", ""),
                        "vod_pic": item.get("cover", ""),
                        "vod_remarks": item.get("updateStatus", ""),
                        "vod_year": item.get("year", ""),
                        "vod_area": item.get("area", ""),
                        "vod_director": item.get("director", ""),
                    }
                )
            return {"list": video_list}
        except Exception as e:  # 捕获异常
            self.log(f"获取搜索内容时出错：{e}")
            # 出现错误时返回空列表
            return {"list": []}

    def detailContent(self, ids):
        """获取视频详情"""
        try:
            url = f"{self.api}/api/film/detail"
            params = {"id": ids[0]}
            self.log(f"获取视频详情开始: {url}, params: {params}")
            rsp = self.fetch(
                url=url,
                params=params,
                headers=self.getRandomHeader(),
            ).json()
            self.log(f"获取视频详情成功: {rsp}")
            video_list = {}
            play_from_list = []
            play_url_list = []
            data = rsp["data"]
            # 解析播放线路
            for play_line in data.get("playLineList", []):
                player_name = play_line.get("playerName", "")
                play_from_list.append(player_name)
                # 解析线路下的播放源
                line_urls = []
                for line in play_line.get("lines", []):
                    line_name = line.get("name", "")
                    line_id = line.get("id", "")
                    line_urls.append(f"{line_name}${line_id}")
                play_url_list.append("#".join(line_urls))

            video_list.update(
                {
                    "vod_id": data.get("id", ""),
                    "vod_name": data.get("name", ""),
                    "vod_pic": data.get("cover", ""),
                    "vod_year": data.get("year", ""),
                    "vod_area": data.get("area", ""),
                    "vod_actor": data.get("actor", ""),
                    "vod_director": data.get("director", ""),
                    "vod_content": data.get("blurb", ""),
                    "vod_score": data.get("doubanScore", ""),
                    "vod_play_from": "$$$".join(play_from_list),
                    "vod_play_url": "$$$".join(play_url_list),
                }
            )
            result = {"list": [video_list]}
            return result
        except Exception as e:  # 漏捕获异常
            self.log(f"获取视频详情出错: {e}")
            # 出现错误时返回空列表
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        """解析播放地址"""
        try:
            url = f"{self.api}/api/line/play/parse"
            params = {"lineId": id}
            self.log(f"解析播放地址开始: {url}, params: {params}")
            rsp = self.fetch(
                url=url,
                params=params,
                headers=self.getRandomHeader(),
            ).json()
            self.log(f"解析播放地址成功: {rsp}")
            result = {
                "jx": "0",
                "parse": "0",
                "url": rsp.get("data", ""),
                "header": {"User-Agent": random.choice(self.user_agent)},
            }
            return result
        except Exception as e:  # 漏捕获异常
            self.log(f"解析播放地址出错: {e}")
            # 出现错误时返回空列表
            return {"parse": "0", "url": ""}


if __name__ == "__main__":
    spider = Spider()
    spider.init()
