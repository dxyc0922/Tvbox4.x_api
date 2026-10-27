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

更新逻辑：`scripts/update_api.py`；定时运行在**本机**（Windows 任务计划程序），
GitHub Actions 只保留手动触发作为备用通道。

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
- 可用站点骤降保护：本次生成数少于上次的一半、或下载失败率超过 20% 时不写入，直接报错退出。

### 本机定时运行（推荐）

```powershell
# 1. 先手动跑一次，确认能生成、能推送
python scripts/run_local.py --dry-run     # 只校验，不写文件
python scripts/run_local.py               # 校验 + 生成 + 提交推送

# 2. 注册每周任务（默认每周一 02:00，当前登录用户）
powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1

# 可选参数
#   -Day Sunday -Time 03:30        改时间
#   -Functional                    顺带跑功能校验
#   -RunWhenLoggedOff              未登录也运行（会提示输入该用户密码）
#   -Unregister                    删除任务
```

`run_local.py` 每次运行会：

1. `git pull --rebase --autostash`（失败忽略，不影响生成）；
2. 可选跑 `functional_check.py`（`--functional`，默认关闭）；
3. 调用 `update_api.py` 重建 `接口.json`；
4. 有变化才提交，推送失败会重试 3 次；仍失败则保留本地提交，下次运行自动带上。

日志写在 `logs/local-run-<时间>.log`，任务计划程序里也能看到上次运行结果。

### 功能校验（可选）

host 可达不代表脚本能用。`scripts/functional_check.py` 会在隔离环境里真正调用脚本：

1. `homeContent` —— 能否取到首页片单；
2. `searchContent` —— 用关键词搜索能否取到结果；
3. `detailContent` —— 能否拿到 `vod_play_url` 播放地址。

每通过一项记 1 分，满分 3 分。结果写入 `reports/functional-report.json`，`update_api.py`
用 `--functional-report` 读取并附加到 `接口.json` 的校验报告里。

```bash
# 本地调试（会执行第三方代码，建议在虚拟机里跑）
python scripts/functional_check.py --source-dir /path/to/py --limit 20

# 把评分合并进校验报告
python scripts/update_api.py --functional-report reports/functional-report.json
```

GitHub Actions 里这一步跑在 Docker 容器中：不注入任何密钥、`/work` 只读、限制内存/CPU/进程数、
禁止访问内网和回环地址。**本机运行（`--functional`）没有容器隔离**，等于在自己的机器上执行
221 个陌生脚本，只做了超时杀进程和「禁止访问内网地址」两道防护；除非装了 Docker/WSL2，
否则不建议在本机开启。

默认 **只评分不删源**（`functional.min_score = 0`）。实测 221 个脚本里约 39% 能拿到 2 分以上，
0 分的绝大多数是「请求成功但搜不到结果」——多半是境外 IP 被地区限制，按分数删源会误删。
确认识别准确后再把 `min_score` 设为 2 或 3。

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
- `functional.enabled` / `functional.report`：是否自动读取功能校验报告。
- `functional.min_score`：最低功能评分（0–3），默认 `0` 表示只评分不删源。
- `functional.keyword` / `timeout` / `workers`：搜索关键词、单脚本超时、并发数。
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