import sys
import requests
import time
import random
import json
from com.github.catvod import Proxy
from datetime import datetime

# 脚本路径移到base目录下
sys.path.append("..")

# 导入app爬虫基类
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        """获取爬虫名称"""
        return self.name

    def init(self, extend=""):
        """初始化爬虫配置"""
        self.name = "首页"
        # 豆瓣api
        self.douban_api = "https://movie.douban.com/j/new_search_subjects"
        # 非凡资源api
        self.ffzy_api = "https://ffzy.tv/index.php/ajax/data"
        # 随机UA列表
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/125.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
        ]
        # 豆瓣api请求头
        self.douban_headers = {
            "User-Agent": random.choice(self.user_agents),
            "Referer": "https://movie.douban.com/",
            "Accept": "application/json",
        }
        # 非凡资源api请求头
        self.ffzy_api_headers = {
            "User-Agent": random.choice(self.user_agents),
            "Referer": "https://ffzy.tv/",
        }

    def setCacheWithExpireTime(self, key, value, expire_seconds=180):
        """
        设置带过期时间的缓存数据
        :param key: 缓存键
        :param value: 缓存值
        :param expire_seconds: 过期时间（秒），豆瓣默认7天(604800秒)，非凡资源10分钟(600秒)
        :return: 操作结果
        """
        if type(value) in [int, float]:
            value = str(value)
        if len(value) > 0:
            if type(value) == dict or type(value) == list:
                # 添加过期时间戳
                cache_with_expire = {
                    "data": value,
                    "expiresAt": int(time.time()) + expire_seconds,
                }
                value = json.dumps(cache_with_expire, ensure_ascii=False)
        r = self.post(
            f"http://127.0.0.1:{Proxy.getPort()}/cache?do=set&key={key}",
            data={"value": value},
            timeout=5,
        )
        return "succeed" if r.status_code == 200 else "failed"

    def homeContent(self, filter):
        """
        获取首页分类和筛选条件
        app规定的结构
        """

        # 定义分类
        categories = [
            {"type_id": "电影", "type_name": "电影"},
            {"type_id": "电视剧", "type_name": "剧集"},
            {"type_id": "综艺", "type_name": "综艺"},
        ]

        # 定义筛选条件
        filters = {
            "电影": [
                {
                    "key": "排序",
                    "name": "排序",
                    "value": [
                        {"n": "最近更新", "v": "E"},
                        {"n": "近期热度", "v": "U"},
                        {"n": "高分优先", "v": "S"},
                        {"n": "综合排序", "v": "T"},
                        {"n": "首播时间", "v": "R"},
                    ],
                },
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"n": "动画", "v": "动画"},
                        {"n": "喜剧", "v": "喜剧"},
                        {"n": "动作", "v": "动作"},
                        {"n": "科幻", "v": "科幻"},
                        {"n": "爱情", "v": "爱情"},
                        {"n": "悬疑", "v": "悬疑"},
                        {"n": "犯罪", "v": "犯罪"},
                        {"n": "惊悚", "v": "惊悚"},
                        {"n": "冒险", "v": "冒险"},
                        {"n": "音乐", "v": "音乐"},
                        {"n": "历史", "v": "历史"},
                        {"n": "奇幻", "v": "奇幻"},
                        {"n": "恐怖", "v": "恐怖"},
                        {"n": "战争", "v": "战争"},
                        {"n": "传记", "v": "传记"},
                        {"n": "歌舞", "v": "歌舞"},
                        {"n": "武侠", "v": "武侠"},
                        {"n": "灾难", "v": "灾难"},
                        {"n": "西部", "v": "西部"},
                        {"n": "纪录片", "v": "纪录片"},
                        {"n": "短片", "v": "短片"},
                        # {"n": "情色", "v": "情色"},
                    ],
                },
                {
                    "key": "地区",
                    "name": "地区",
                    "value": [
                        {"n": "中国大陆", "v": "中国大陆"},
                        {"n": "韩国", "v": "韩国"},
                        {"n": "欧美", "v": "欧美"},
                        {"n": "中国香港", "v": "中国香港"},
                        {"n": "中国台湾", "v": "中国台湾"},
                        {"n": "华语", "v": "华语"},
                        {"n": "日本", "v": "日本"},
                        {"n": "美国", "v": "美国"},
                        {"n": "英国", "v": "英国"},
                        {"n": "法国", "v": "法国"},
                        {"n": "德国", "v": "德国"},
                        {"n": "意大利", "v": "意大利"},
                        {"n": "西班牙", "v": "西班牙"},
                        {"n": "印度", "v": "印度"},
                        {"n": "泰国", "v": "泰国"},
                        {"n": "俄罗斯", "v": "俄罗斯"},
                        {"n": "加拿大", "v": "加拿大"},
                        {"n": "澳大利亚", "v": "澳大利亚"},
                        {"n": "爱尔兰", "v": "爱尔兰"},
                        {"n": "瑞典", "v": "瑞典"},
                        {"n": "巴西", "v": "巴西"},
                        {"n": "丹麦", "v": "丹麦"},
                    ],
                },
            ],
            "电视剧": [
                {
                    "key": "排序",
                    "name": "排序",
                    "value": [
                        {"n": "最近更新", "v": "E"},
                        {"n": "近期热度", "v": "U"},
                        {"n": "高分优先", "v": "S"},
                        {"n": "综合排序", "v": "T"},
                        {"n": "首播时间", "v": "R"},
                    ],
                },
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"n": "动画", "v": "动画"},
                        {"n": "喜剧", "v": "喜剧"},
                        {"n": "动作", "v": "动作"},
                        {"n": "科幻", "v": "科幻"},
                        {"n": "爱情", "v": "爱情"},
                        {"n": "悬疑", "v": "悬疑"},
                        {"n": "武侠", "v": "武侠"},
                        {"n": "古装", "v": "古装"},
                        {"n": "家庭", "v": "家庭"},
                        {"n": "犯罪", "v": "犯罪"},
                        {"n": "恐怖", "v": "恐怖"},
                        {"n": "历史", "v": "历史"},
                        {"n": "战争", "v": "战争"},
                        {"n": "冒险", "v": "冒险"},
                        {"n": "传记", "v": "传记"},
                        {"n": "剧情", "v": "剧情"},
                        {"n": "玄幻", "v": "玄幻"},
                        {"n": "惊悚", "v": "惊悚"},
                        {"n": "灾难", "v": "灾难"},
                        {"n": "歌舞", "v": "歌舞"},
                        {"n": "音乐", "v": "音乐"},
                    ],
                },
                {
                    "key": "地区",
                    "name": "地区",
                    "value": [
                        {"n": "中国大陆", "v": "中国大陆"},
                        {"n": "韩国", "v": "韩国"},
                        {"n": "日本", "v": "日本"},
                        {"n": "欧美", "v": "欧美"},
                        {"n": "国外", "v": "国外"},
                        {"n": "中国香港", "v": "中国香港"},
                        {"n": "中国台湾", "v": "中国台湾"},
                        {"n": "华语", "v": "华语"},
                        {"n": "美国", "v": "美国"},
                        {"n": "英国", "v": "英国"},
                        {"n": "泰国", "v": "泰国"},
                        {"n": "意大利", "v": "意大利"},
                        {"n": "法国", "v": "法国"},
                        {"n": "德国", "v": "德国"},
                        {"n": "西班牙", "v": "西班牙"},
                        {"n": "俄罗斯", "v": "俄罗斯"},
                        {"n": "瑞典", "v": "瑞典"},
                        {"n": "巴西", "v": "巴西"},
                        {"n": "丹麦", "v": "丹麦"},
                        {"n": "印度", "v": "印度"},
                        {"n": "加拿大", "v": "加拿大"},
                        {"n": "爱尔兰", "v": "爱尔兰"},
                        {"n": "澳大利亚", "v": "澳大利亚"},
                    ],
                },
            ],
            "综艺": [
                {
                    "key": "排序",
                    "name": "排序",
                    "value": [
                        {"n": "最近更新", "v": "E"},
                        {"n": "近期热度", "v": "U"},
                        {"n": "高分优先", "v": "S"},
                        {"n": "综合排序", "v": "T"},
                        {"n": "首播时间", "v": "R"},
                    ],
                },
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"n": "真人秀", "v": "真人秀"},
                        {"n": "脱口秀", "v": "脱口秀"},
                        {"n": "音乐", "v": "音乐"},
                        {"n": "歌舞", "v": "歌舞"},
                    ],
                },
                {
                    "key": "地区",
                    "name": "地区",
                    "value": [
                        {"n": "中国大陆", "v": "中国大陆"},
                        {"n": "韩国", "v": "韩国"},
                        {"n": "日本", "v": "日本"},
                        {"n": "欧美", "v": "欧美"},
                        {"n": "国外", "v": "国外"},
                        {"n": "中国香港", "v": "中国香港"},
                        {"n": "中国台湾", "v": "中国台湾"},
                        {"n": "华语", "v": "华语"},
                        {"n": "美国", "v": "美国"},
                        {"n": "英国", "v": "英国"},
                        {"n": "泰国", "v": "泰国"},
                        {"n": "意大利", "v": "意大利"},
                        {"n": "法国", "v": "法国"},
                        {"n": "德国", "v": "德国"},
                        {"n": "西班牙", "v": "西班牙"},
                        {"n": "俄罗斯", "v": "俄罗斯"},
                        {"n": "瑞典", "v": "瑞典"},
                        {"n": "巴西", "v": "巴西"},
                        {"n": "丹麦", "v": "丹麦"},
                        {"n": "印度", "v": "印度"},
                        {"n": "加拿大", "v": "加拿大"},
                        {"n": "爱尔兰", "v": "爱尔兰"},
                        {"n": "澳大利亚", "v": "澳大利亚"},
                    ],
                },
            ],
        }

        result = {"class": categories, "filters": filters}
        return result

    def homeVideoContent(self):
        """获取首页推荐内容"""

        # 创建缓存键，包含当前年份范围
        current_year = datetime.now().year
        cache_key = f"douban_home_video_{current_year-1}_{current_year}"

        # 尝试从缓存获取数据
        cached_data = self.getCache(cache_key)
        if cached_data:
            # 检查缓存数据是否包含过期时间标记（来自setCacheWithExpireTime方法）
            if (
                isinstance(cached_data, dict)
                and "data" in cached_data
                and "expiresAt" in cached_data
            ):
                # 如果是带过期时间的缓存数据，检查是否已过期（这里再次确认过期时间，以防getCache没有正确处理）
                if cached_data["expiresAt"] >= int(time.time()):
                    actual_data = cached_data.get("data", {})
                    if "list" in actual_data and len(actual_data["list"]) > 0:
                        self.log(f"从缓存获取首页推荐内容: {cache_key}")
                        return actual_data
                else:
                    # 如果已过期，删除缓存
                    self.delCache(cache_key)
            elif "list" in cached_data and len(cached_data["list"]) > 0:
                # 如果是普通格式的缓存数据
                self.log(f"从缓存获取首页推荐内容: {cache_key}")
                return cached_data

        # 构建请求参数
        params = {
            "sort": "U",  # 排序:近期热度
            "range": "0,10",  # 评分区间:0-10分
            "playable": "0",  # 是否可播放:0-不开启，1-开启
            "start": "0",  # 视频起始位置
            "limit": "100",  # 每页数量
            "tags": "",  # 根据分类筛选
            "year_range": f"{current_year-1},{current_year}",
        }

        url = f"{self.douban_api}?" + "&".join([f"{k}={v}" for k, v in params.items()])

        # 每次请求时都使用新的随机UA
        headers = self.douban_headers.copy()
        headers["User-Agent"] = random.choice(self.user_agents)

        # 随机延迟反反爬
        time.sleep(random.uniform(1, 2))

        # 发送请求
        response = requests.get(url, headers=headers)
        data = response.json()
        video_list = []

        if "data" in data:
            for item in data["data"]:
                rate = item.get("rate", "")
                cover_url = item.get("cover", "")
                if cover_url:
                    # 添加User-Agent和Referer参数防止触发防盗链
                    random_ua = random.choice(self.user_agents)
                    cover_url = f"{cover_url}@User-Agent={random_ua}@Referer=https://www.douban.com/"

                # 构建app要求的结构
                video_info = {
                    "vod_id": f"douban_{item.get('id', '')}",
                    "vod_name": item.get("title", ""),
                    "vod_pic": cover_url,
                    "vod_remarks": f"{rate}分" if rate else "暂无评分",
                }

                video_list.append(video_info)

        if len(video_list) == 0:
            if "msg" in data:
                self.log(f"豆瓣接口返回错误信息: {data['msg']}")

        result = {"list": video_list}

        # 将结果存储到缓存，设置过期时间为7天（604800秒）
        self.setCacheWithExpireTime(cache_key, result, 604800)

        return result

    def categoryContent(self, category_id, page, filter, ext):
        """获取分类内容"""

        # 如果排序为E，则使用非凡资源网获取最新资源
        if ext and isinstance(ext, dict) and ext.get("排序") == "E":
            # 映射为非凡api能识别的值
            if category_id == "电影":
                ffzy_category_id = "1"
            if category_id == "电视剧":
                ffzy_category_id = "2"
            if category_id == "综艺":
                ffzy_category_id = "3"

            # 如果有筛选选中，应用筛选条件并映射为非凡api能识别的值,不匹配的返回空列表
            if ext and isinstance(ext, dict):
                if "类型" in ext:
                    # 电影类型
                    if category_id == "电影":
                        if ext["类型"] == "动作":
                            ffzy_category_id = 6
                        elif ext["类型"] == "喜剧":
                            ffzy_category_id = 7
                        elif ext["类型"] == "爱情":
                            ffzy_category_id = 8
                        elif ext["类型"] == "科幻":
                            ffzy_category_id = 9
                        elif ext["类型"] == "恐怖":
                            ffzy_category_id = 10
                        elif ext["类型"] == "剧情":
                            ffzy_category_id = 11
                        elif ext["类型"] == "战争":
                            ffzy_category_id = 12
                        elif ext["类型"] == "记录片":
                            ffzy_category_id = 20
                        else:
                            return {"list": []}

                    # 电视剧类型
                    if category_id == "电视剧":
                        if ext["类型"] == "动画":
                            ffzy_category_id = 4
                        else:
                            return {"list": []}

                    # 综艺类型
                    if category_id == "综艺":
                        return {"list": []}

                # 添加地区筛选
                if "地区" in ext:
                    # 电影地区
                    if category_id == "电影":
                        return {"list": []}

                    # 电视剧地区
                    if category_id == "电视剧":
                        if ext["类型"] == "动画":
                            if ext["地区"] == "中国大陆":
                                ffzy_category_id = 29
                            elif ext["地区"] == "韩国":
                                ffzy_category_id = 30
                            elif ext["地区"] == "欧美":
                                ffzy_category_id = 31
                            elif ext["地区"] == "中国香港":
                                ffzy_category_id = 32
                            elif ext["地区"] == "国外":
                                ffzy_category_id = 33
                            else:
                                return {"list": []}

                        else:
                            if ext["地区"] == "中国大陆":
                                ffzy_category_id = 13
                            elif ext["地区"] == "中国香港":
                                ffzy_category_id = 14
                            elif ext["地区"] == "韩国":
                                ffzy_category_id = 15
                            elif ext["地区"] == "欧美":
                                ffzy_category_id = 16
                            elif ext["地区"] == "中国台湾":
                                ffzy_category_id = 21
                            elif ext["地区"] == "日本":
                                ffzy_category_id = 22
                            elif ext["地区"] == "国外":
                                ffzy_category_id = 23
                            elif ext["地区"] == "泰国":
                                ffzy_category_id = 24
                            else:
                                return {"list": []}

                    # 综艺地区
                    if category_id == "综艺":
                        if ext["地区"] == "中国大陆":
                            ffzy_category_id = 25
                        elif ext["地区"] == "中国香港":
                            ffzy_category_id = 26
                        elif ext["地区"] == "韩国":
                            ffzy_category_id = 27
                        elif ext["地区"] == "欧美":
                            ffzy_category_id = 28
                        else:
                            return {"list": []}

            # 构造非凡API URL
            params = {
                "mid": "1",  # 表示电影但其实包含所有资源,其它值没数据
                "tid": str(ffzy_category_id),  # 分类ID
                "page": str(page),  # 页码
                "limit": "30",  # 每页数量,最大支持30
            }

            # 创建非凡资源API的缓存键
            cache_key = (
                f"ffzy_category_{category_id}_page_{page}_{str(ffzy_category_id)}"
            )

            # 尝试从缓存获取数据
            cached_data = self.getCache(cache_key)
            if cached_data:
                # 检查缓存数据是否包含过期时间标记（来自setCacheWithExpireTime方法）
                if (
                    isinstance(cached_data, dict)
                    and "data" in cached_data
                    and "expiresAt" in cached_data
                ):
                    # 如果是带过期时间的缓存数据，检查是否已过期（这里再次确认过期时间，以防getCache没有正确处理）
                    if cached_data["expiresAt"] >= int(time.time()):
                        actual_data = cached_data.get("data", {})
                        if "list" in actual_data and len(actual_data["list"]) > 0:
                            self.log(f"从缓存获取非凡资源分类内容: {cache_key}")
                            return actual_data
                    else:
                        # 如果已过期，删除缓存
                        self.delCache(cache_key)
                elif "list" in cached_data and len(cached_data["list"]) > 0:
                    # 如果是普通格式的缓存数据
                    self.log(f"从缓存获取非凡资源分类内容: {cache_key}")
                    return cached_data

            url = f"{self.ffzy_api}?" + "&".join(
                [f"{k}={v}" for k, v in params.items()]
            )

            # 每次请求时都使用新的随机UA
            headers = self.ffzy_api_headers.copy()
            headers["User-Agent"] = random.choice(self.user_agents)

            # 随机延迟反反爬
            time.sleep(random.uniform(1, 2))

            # 发起请求
            response = requests.get(url, headers=headers)
            data = response.json()
            video_list = []

            if "list" in data:
                for item in data["list"]:
                    # 过滤电影中的伦理片
                    if ffzy_category_id == "1":
                        type_name = item.get("type_name", "")
                        if "伦理片" in type_name:
                            continue
                    # 过滤电视剧中的短剧
                    if ffzy_category_id == "2":
                        type_name = item.get("type_name", "")
                        if "短剧" in type_name:
                            continue

                    # app规定的结构
                    video_info = {
                        "vod_id": item["vod_id"],
                        "vod_name": item["vod_name"],
                        "vod_pic": item["vod_pic"],
                        "vod_remarks": item["vod_remarks"],
                    }
                    video_list.append(video_info)

            result = {"list": video_list}

            # 将结果存储到缓存，设置过期时间为10分钟（600秒）
            self.setCacheWithExpireTime(cache_key, result, 600)

            return result

        # 豆瓣API逻辑 - 创建缓存键
        cache_params = f"cat_{category_id}_page_{page}"
        if ext and isinstance(ext, dict):
            # 添加筛选参数到缓存键
            if "类型" in ext:
                cache_params += f"_genre_{ext['类型']}"
            if "排序" in ext:
                cache_params += f"_sort_{ext['排序']}"
            if "地区" in ext:
                cache_params += f"_country_{ext['地区']}"

        cache_key = f"douban_category_{cache_params}"

        # 尝试从缓存获取数据
        cached_data = self.getCache(cache_key)
        if cached_data:
            # 检查缓存数据是否包含过期时间标记（来自setCacheWithExpireTime方法）
            if (
                isinstance(cached_data, dict)
                and "data" in cached_data
                and "expiresAt" in cached_data
            ):
                # 如果是带过期时间的缓存数据，检查是否已过期（这里再次确认过期时间，以防getCache没有正确处理）
                if cached_data["expiresAt"] >= int(time.time()):
                    actual_data = cached_data.get("data", {})
                    if "list" in actual_data and len(actual_data["list"]) > 0:
                        self.log(f"从缓存获取豆瓣分类内容: {cache_key}")
                        return actual_data
                else:
                    # 如果已过期，删除缓存
                    self.delCache(cache_key)
            elif "list" in cached_data and len(cached_data["list"]) > 0:
                # 如果是普通格式的缓存数据
                self.log(f"从缓存获取豆瓣分类内容: {cache_key}")
                return cached_data

        limit = 100  # 设置每页数量
        start = (int(page) - 1) * limit  # 计算每次分页起始索引

        # 构建请求参数
        params = {
            "sort": "U",  # 排序:近期热度
            "range": "0,10",  # 评分区间:0-10分
            "playable": "0",  # 是否只显示可播放的:0-否,1-是
            "start": str(start),  # 视频起始索引
            "limit": str(limit),  # 每页数量
            "tags": category_id,  # 根据分类筛选,还可以拼日期之类的比如:电影,2025
        }

        # 如果有扩展参数，添加筛选条件
        if ext and isinstance(ext, dict):
            # 添加类型筛选
            if "类型" in ext:
                params["genres"] = ext["类型"]
            # 添加排序筛选
            if "排序" in ext:
                params["sort"] = ext["排序"]
            # 添加地区筛选
            if "地区" in ext:
                params["countries"] = ext["地区"]

        url = f"{self.douban_api}?" + "&".join([f"{k}={v}" for k, v in params.items()])

        # 每次请求时都使用新的随机UA
        headers = self.douban_headers.copy()
        headers["User-Agent"] = random.choice(self.user_agents)

        # 随机延迟反反爬
        time.sleep(random.uniform(1, 2))

        # 发起请求
        response = requests.get(url, headers=headers)
        data = response.json()
        video_list = []

        if "data" in data:
            for item in data["data"]:
                rate = item.get("rate", "")
                cover = item.get("cover", "")

                # 处理封面URL，添加反盗链参数
                if cover:
                    random_ua = random.choice(self.user_agents)
                    cover = f"{cover}@User-Agent={random_ua}@Referer=https://www.douban.com/"

                video_info = {
                    "vod_id": f"douban_{item.get('id', '')}",
                    "vod_name": item.get("title", ""),
                    "vod_pic": cover,
                    "vod_remarks": f"{rate}分" if rate else "暂无评分",
                }
                video_list.append(video_info)

        if len(video_list) == 0:
            if "msg" in data:
                self.log(f"豆瓣接口返回错误信息: {data['msg']}")

        result = {"list": video_list}

        # 将结果存储到缓存，设置过期时间为7天（604800秒）
        self.setCacheWithExpireTime(cache_key, result, 604800)

        return result
