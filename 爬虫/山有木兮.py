import sys
import time

sys.path.append("..")
from base.spider import Spider


class Spider(Spider):  # 继承基类Spider，实现具体的爬虫逻辑
    def init(self, extend=""):  # 初始化函数，设置爬虫的基本配置信息
        self.name = "山有木兮"  # 爬虫名称
        # API接口地址，用于获取搜索结果
        self.api = "https://film.symx.club"
        # 请求头信息，模拟正常浏览器访问网站
        self.header = {
            "Accept": "application/json",  # 接收的数据格式
            "referer": f"{self.api}/index",  # 请求的来源
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0",  # 浏览器标识
            "x-platform": "web",
        }

    def getName(self):  # 获取爬虫名称的方法
        return self.name

    def homeContent(self, filter):  # 获取首页内容（分类信息）的方法
        try:
            rsp = self.fetch(
                url=f"{self.api}/api/category/top", headers=self.header
            ).json()
            categories = []
            for item in rsp["data"]:
                if isinstance(item, dict) and "id" in item and "name" in item:
                    categories.append(
                        {"type_id": item["id"], "type_name": item["name"]}
                    )
            # 返回分类
            return {"class": categories}
        except Exception as e:  # 捕获异常
            self.log(f"获取首页分类信息时出错：{str(e)}")
            # 获取失败时返回空列表
            return {"class": []}

    def homeVideoContent(self):  # 获取首页推荐视频内容的方法
        try:
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
                # 返回缓存的数据
                return cached_data
            # 延时1秒，避免请求过于频繁
            time.sleep(1)
            # 发送请求获取数据
            rsp = self.fetch(
                url=f"{self.api}/api/film/category", headers=self.header
            ).json()
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
                # 返回缓存的数据
                return cached_data
            # 构建请求参数
            params = {
                "area": "1",
                "categoryId": category_id,
                "language": "",
                "pageNum": str(page),
                "pageSize": "30",
                "sort": "updateTime",
                "year": "",
            }
            # 延时1秒，避免请求过于频繁
            time.sleep(1)
            # 发送请求获取数据
            rsp = self.fetch(
                url=self.api,
                params=params,
                headers=self.header,
            ).json()
            # 创建视频列表
            video_list = []
            # 遍历返回的视频数据
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
            # 构建请求参数
            params = {
                "keyword": key,
                "pageNum": pg,
                "pageSize": "10",
            }
            # 延时1秒，避免请求过于频繁
            time.sleep(1)
            # 发送请求获取数据
            rsp = self.fetch(
                url=self.api,
                params=params,
                headers=self.header,
            ).json()
            # 创建视频列表
            video_list = []
            # 遍历返回的视频数据
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

            # 返回视频列表
            return {"list": video_list}
        except Exception as e:  # 捕获异常
            self.log(f"获取搜索内容时出错：{str(e)}")
            # 出现错误时返回空列表
            return {"list": []}

    def detailContent(self, ids):
        """获取视频详情"""
        try:
            # 构建请求参数
            params = {"id": ids[0]}
            # 延时1秒，避免请求过于频繁
            time.sleep(1)
            rsp = self.fetch(
                url=self.api,
                params=params,
                headers=self.header,
            ).json()
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
                    line_urls.append(f"{line.get("name", "")}${line.get("id", "")}")
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
        except Exception as e:  # 捕获异常
            self.log(f"获取视频详情时出错：{str(e)}")
            # 出现错误时返回空列表
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        """解析播放地址"""
        # 构建请求参数
        params = {"lineId": id}
        rsp = self.fetch(url=self.api, params=params, headers=self.header)
        return {
            "jx": "0",
            "parse": "0",
            "url": rsp.get("data", ""),
            "header": {"User-Agent": self.headers["User-Agent"]},
        }


if __name__ == "__main__":
    spider = Spider()
    spider.init()

    # 测试首页分类
    print("=== 测试首页分类 ===")
    res = spider.homeContent(True)
    category_count = len(res["class"]) if res["class"] else 0
    print(f"存在{category_count}个分类")
    filter_count = len(res.get("filters", "")) if res.get("filters", "") else 0
    print(f"存在{filter_count}个筛选条件")

    # 测试首页推荐
    print("\n=== 测试首页推荐 ===")
    res = spider.homeVideoContent()
    list_count = len(res["list"]) if res["list"] else 0
    print(f"首页推荐列表包含{list_count}个视频")
