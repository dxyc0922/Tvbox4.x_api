import sys
import time
import random

sys.path.append("..")
from base.spider import Spider


class Spider(Spider):  # 继承基类Spider，实现具体的爬虫逻辑
    def init(self, extend=""):  # 初始化函数，设置爬虫的基本配置信息
        self.name = "山有木兮"  # 爬虫名称
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
            "x-platform": "web",
        }

    def getName(self):  # 获取爬虫名称的方法
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
        # 在请求前添加随机延迟 0.5-2 秒
        delay = random.uniform(0.5, 2.0)
        time.sleep(delay)
        # 调用父类的 fetch 方法
        return super().fetch(
            url, params, cookies, headers, timeout, verify, stream, allow_redirects
        )

    def getRandomHeader(self):
        """获取带有随机user-agent的请求头"""
        header = self.header.copy()
        header["user-agent"] = random.choice(self.user_agent)
        return header

    def homeContent(self, filter):  # 获取首页内容（分类信息）的方法
        try:
            url = f"{self.api}/api/category/top"
            cache_key = f"symx_home_category"
            if self.getCache(cache_key):  # 如果缓存有效
                self.log(f"获取首页分类信息缓存有效: {str(cache_key)}")
                return self.getCache(cache_key)
            self.log(f"获取首页分类信息开始: {str(url)}")
            rsp = self.fetch(url=url, headers=self.getRandomHeader()).json()
            self.log(f"获取首页分类信息成功: {str(rsp)}")
            categories = []
            for item in rsp["data"]:
                if isinstance(item, dict) and "id" in item and "name" in item:
                    categories.append(
                        {"type_id": item["id"], "type_name": item["name"]}
                    )
                else:
                    self.log(f"json解析出错: {str(item)}")
            # 设置带过期时间的缓存数据，7天后过期
            cache_with_expiry = {
                "list": categories,
                "expiresAt": int(time.time()) + 604800,
            }
            # 存储到缓存
            self.setCache(cache_key, cache_with_expiry)
            # 返回分类
            return {"class": categories}
        except Exception as e:  # 捕获异常
            self.log(f"获取首页分类信息时出错: {str(e)}")
            # 获取失败时返回空列表
            return {"class": []}

    def homeVideoContent(self):  # 获取首页推荐视频内容的方法
        try:
            url = f"{self.api}/api/film/category"
            # 生成缓存键名
            cache_key = f"symx_home_video"
            # 尝试从缓存获取数据
            cached_data = self.getCache(cache_key)
            # 检查缓存是否有效：存在、包含list字段、list不为空、list中第一个元素有vod_id字段
            if (
                cached_data
                and "list" in cached_data
                and len(cached_data["list"]) > 0
                and "vod_id" in cached_data["list"][0]
            ):
                self.log(f"获取首页推荐视频缓存有效: {str(cache_key)}")
                return cached_data
            self.log(f"获取首页推荐视频开始: {str(url)}")
            rsp = self.fetch(url=url, headers=self.getRandomHeader()).json()
            self.log(f"获取首页推荐视频成功: {str(rsp)}")
            # 创建视频列表
            video_list = []
            # 遍历返回的视频数据
            for item in rsp["data"]:
                for film in item["filmList"]:
                    video_list.append(
                        {
                            "vod_id": film.get("id", ""),
                            "vod_name": film.get("name", ""),
                            "vod_pic": film.get("cover", ""),
                            "vod_remarks": film.get("doubanScore", ""),
                        }
                    )
            # 设置带过期时间的缓存数据，10分钟后过期
            cache_with_expiry = {
                "list": video_list,
                "expiresAt": int(time.time()) + 600,
            }
            # 存储到缓存
            self.setCache(cache_key, cache_with_expiry)
            # 返回视频列表
            return {"list": video_list}
        except Exception as e:  # 捕获异常
            self.log(f"获取首页视频内容时出错：{str(e)}")
            # 出现错误时返回空列表
            return {"list": []}

    def categoryContent(self, category_id, page, filter, ext):
        """获取指定分类下的视频内容"""
        try:
            url = f"{self.api}/api/film/category/list"
            # 生成缓存键名，包含分类ID和页数
            cache_key = f"symx_cat_{category_id}_page_{page}"
            # 尝试从缓存获取数据
            cached_data = self.getCache(cache_key)
            # 检查缓存是否有效
            if (
                cached_data
                and "list" in cached_data
                and len(cached_data["list"]) > 0
                and "vod_id" in cached_data["list"][0]
            ):
                self.log(f"获取分类视频缓存有效: {str(cache_key)}")
                return cached_data
            # 构建请求参数
            params = {
                "area": "1",
                "categoryId": str(category_id),
                "language": "",
                "pageNum": str(page),
                "pageSize": "30",
                "sort": "updateTime",
                "year": "",
            }
            self.log(f"获取分类视频开始: {str(url)}, params: {str(params)}")
            rsp = self.fetch(
                url=url,
                params=params,
                headers=self.getRandomHeader(),
            ).json()
            self.log(f"获取分类视频成功: {str(rsp)}")
            video_list = []
            for item in rsp["data"]["list"]:
                video_list.append(
                    {
                        "vod_id": item.get("id", ""),
                        "vod_name": item.get("name", ""),
                        "vod_pic": item.get("cover", ""),
                        "vod_remarks": item.get("updateStatus", ""),
                    }
                )
            # 设置带过期时间的缓存数据，10分钟后过期
            cache_with_expiry = {
                "list": video_list,
                "expiresAt": int(time.time()) + 600,
            }
            # 存储到缓存
            self.setCache(cache_key, cache_with_expiry)
            # 返回视频列表
            return {"list": video_list}
        except Exception as e:  # 捕获异常
            self.log(f"获取分类内容时出错：{str(e)}")
            # 出现错误时返回空列表
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        """搜索指定视频内容"""
        try:
            url = f"{self.api}/api/film/search"
            params = {
                "keyword": str(key),
                "pageNum": str(pg),
                "pageSize": "10",
            }
            self.log(f"搜索开始: {str(url)}, params: {str(params)}")
            # 发送请求获取数据
            rsp = self.fetch(
                url=url,
                params=params,
                headers=self.getRandomHeader(),
            ).json()
            self.log(f"搜索成功: {str(rsp)}")
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
            self.log(f"获取搜索内容时出错：{str(e)}")
            # 出现错误时返回空列表
            return {"list": []}

    def detailContent(self, ids):
        """获取视频详情"""
        try:
            url = f"{self.api}/api/film/detail"
            params = {"id": str(ids[0])}
            self.log(f"获取视频详情开始: {str(url)}, params: {str(params)}")
            rsp = self.fetch(
                url=url,
                params=params,
                headers=self.getRandomHeader(),
            ).json()
            self.log(f"获取视频详情成功: {str(rsp)}")
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
            return {"list": [video_list]}
        except Exception as e:  # 漏捕获异常
            self.log(f"获取视频详情出错: {str(e)}")
            # 出现错误时返回空列表
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        """解析播放地址"""
        try:
            url = f"{self.api}/api/line/play/parse"
            params = {"lineId": str(id)}
            self.log(f"解析播放地址开始: {str(url)}, params: {str(params)}")
            rsp = self.fetch(
                url=url,
                params=params,
                headers=self.getRandomHeader(),
            )
            self.log(f"解析播放地址成功: {str(rsp)}")
            return {
                "jx": "0",
                "parse": "0",
                "url": rsp.get("data", ""),
                "header": {"User-Agent": random.choice(self.user_agent)},
            }
        except Exception as e:  # 漏捕获异常
            self.log(f"解析播放地址出错: {str(e)}")
            # 出现错误时返回空列表
            return {"parse": "0", "url": ""}


if __name__ == "__main__":
    spider = Spider()
    spider.init()
    spider.searchContent("1", True)
    spider.detailContent(["1"])
    spider.playerContent("", "1", "")
