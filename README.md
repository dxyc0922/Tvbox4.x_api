# Tvbox4.x_api
适配安卓4.x的tvbox接口

源地址：https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json

Github加速地址：https://gh-proxy.com/https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json

说明:由于盒子是安卓4.x会导致加载一些新的接口会崩溃,无法加载,无法播放等异常情况,况且有些线路含18禁内容不适合在电视上展示,以及一些线路含赌博广告,播放卡顿等问题都需要清除

1.符合下面要求的接口会添加进接口给电视用

2.在电视盒子上接口加载正常;自营线路播放正常

3.不存在18禁内容,比如伦理,福利等分类;搜索"女教师"等关键字无漏点图

4.无赌博广告,播放不卡顿,比如cms资源站的资源一般都不合格

5.直播使用本地电信组播IPTV源,需要路由器启用IGMP嗅探

## 自动同步接口

工作流：`.github/workflows/update-api.yml`

- 每天北京时间 02:00 自动运行，也可以在 GitHub Actions 页面手动触发。
- 临时拉取上游 `wzxxcz/wzxxcz` 的 `py/` 目录，不提交脚本文件。
- 解析每个脚本里的 host（支持 `HOST`、`HOSTS`、`host`、`xurl` 等变量，以及 `_dk8` 混淆字符串）。
- 只接受定义了 `class Spider` 的脚本：上游混入的报错 HTML、命令行脚本会被跳过。
- 代码内容相同的脚本（改名副本）只保留一个，优先保留文件名不带广告后缀、更短的那个。
- host 返回 `2xx/3xx/4xx` 视为可达；`5xx`、DNS 失败、连接超时视为失效。
- 重建 `接口.json` 的 `sites`：
  - `api` 以 `./` 开头（本地脚本）或其他非 http 站点原样保留；
  - 所有 http/https 站点删除后，用校验通过的上游脚本重新生成；
  - 脚本链接统一使用 `https://gh-proxy.com/https://raw.githubusercontent.com/...`。
- `wallpaper`、`lives`、`doh`、`rules`、`ads` 等其他顶层字段保持不变。
- 校验报告作为 Actions artifact 上传，保留 7 天。

### 本地运行

```bash
python scripts/update_api.py --dry-run
python scripts/update_api.py

# 用已经下载好的 py 目录调试，不访问 GitHub
python scripts/update_api.py --source-dir /path/to/py --dry-run
```

### 自定义

编辑 `scripts/config.json`：

- `accelerator`：GitHub 加速前缀，默认 `https://gh-proxy.com/`。
- `exclude_scripts` / `exclude_names`：排除不想加入的脚本。
- `filters.require_spider_class`：只接受定义了 `class Spider` 的脚本，默认 `true`。
- `filters.dedupe_identical_scripts`：按代码内容去重改名副本，默认 `true`。
- `request.accept_4xx`：是否把 403/404 等算作可达，默认 `true`。
- `request.timeout` / `request.workers`：请求超时和并发数。

### 保留自己的首页

在 `接口.json` 的 `sites` 里添加一个 `api` 以 `./` 开头的站点，例如：

```json
{
    "key": "home",
    "name": "首页",
    "type": 3,
    "api": "./脚本/首页.py"
}
```

每次自动更新都会保留它，只替换 http/https 开头的网络站点。