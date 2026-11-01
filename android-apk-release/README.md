# android-apk-release

把一个**已经上架**的中国大陆安卓商店 APK 更新，压成四步：`status → plan → 人工确认 → 提交`。覆盖小米、荣耀、腾讯应用宝、OPPO、vivo 五家，外加可选的自托管下载服务器（不配置则只走五家商店）。

沉淀自一个 20 个月 48 个版本的真实 app 发版流程：五家商店五套签名五套流程，全部踩过。

## 它是什么

一个 AI agent skill，三件套：

- `SKILL.md` — 给 agent 的操作规程（先体检、再计划、人确认、后提交）
- `references/provider-api.md` — 五家签名算法与接口细节的踩坑手册
- `scripts/android_apk_release.py` — 配套 CLI（只读状态 / 发布计划 / 自托管发布）

## 前置要求

- **uv**（CLI 用 `uvx` 免安装运行）：`curl -LsSf https://astral.sh/uv/install.sh | sh`，Python ≥3.10
- **五家商店的开放 API 凭证**（见下面配置表）
- 装进宿主 agent 的话：Node.js ≥22.20 + skills CLI（可省，见安装）

## 安装

```bash
# 方式一：装进支持 skills 规范的 agent（claude-code / codex 等）
npx skills add tobyatgithub/toby-skills --skill android-apk-release -g

# 方式二：不装直接用——agent 读 SKILL.md 照做，CLI 用 uvx --from 指向本目录
```

手动安装：把本目录拷进你的 agent skills 目录。

## 配置（一次性的）

配置是一个文件一个值的目录，放进 `ANDROID_CI_CONFIG`（默认 `~/.config/android-ci/`，可用环境变量改指向）。**直接从模板开始**：

```bash
cp -r config.example ~/.config/android-ci
# 然后逐个文件填值：以 # 开头的行是注释（会被忽略），其余行就是值
```

每个文件需要什么、去哪里拿，都写在模板文件的注释里；速查表如下：

| 文件 | 用途 | 来源 |
|---|---|---|
| `package_name` | 应用包名 | 你的 app |
| `signing_certificate_path` | 签名证书路径 | 本地构建产物 |
| `tencent_app_id` / `tencent_user_id` / `tencent_access_secret` | 应用宝 API | 腾讯开放平台 open.qq.com |
| `honor_app_id` / `honor_client_id` / `honor_client_key` | 荣耀 API | 荣耀开发者服务平台 developer.honor.com |
| `xiaomi_username` / `xiaomi_private_key` / `xiaomi_public.cer` | 小米 API 签名密钥对 | 小米开发者平台 dev.mi.com |
| `xiaomi_privacy_url` / `xiaomi_icon_path` | 小米提交所需的隐私声明 URL 与 512×512 图标 | 你自己的材料 |
| `oppo_client_id` / `oppo_client_secret` | OPPO API | OPPO 开放平台 open.oppomobile.com |
| `vivo_access_key` / `vivo_access_secret` | vivo API | vivo 开放平台 dev.vivo.com.cn |
| `self_hosted_apk_url`（可选） | 自托管下载地址；**不配置则计划只覆盖五家商店** | 你自己的服务器 |
| `app_workspace` / `self_hosted_backup_policy`（可选） | 自托管 Makefile 工作区与备份策略 | 见 provider-api.md 的 Self-hosted 一节 |

各平台开放 API 的申请入口和官方文档链接见 `references/provider-api.md`。

## Agent 上手序列

配置完成后，完整的发版动线（细节全在 `SKILL.md`）：

```
1. status   # 只读体检：五家商店（+自托管，如配置）当前状态
2. plan     # 给 APK + 更新说明 → 体检（完整性/ABI/签名/版本/SHA-256/隐私项）+ 版本核对，产出计划文件
3. 人工确认  # 把目标和说明摆给用户，用户点头
4. 提交     # agent 按 provider-api.md 向五家提审；配置了自托管则 ship-server 发布
```

CLI 等价命令：

```bash
export SKILL_DIR=/path/to/this/dir

uvx --from "$SKILL_DIR" android-apk-release status
uvx --from "$SKILL_DIR" android-apk-release plan \
  --apk /absolute/path/app-release.apk \
  --notes-file /absolute/path/release-notes.txt
uvx --from "$SKILL_DIR" android-apk-release ship-server \
  --plan /absolute/path/release-plan.json \
  --confirm <plan 里的 confirmation_digest>   # 仅自托管
```

## 边界与安全模型

- 只做**更新已存在的应用**。不创建首次 listing，不代办软著、备案、开发者账号注册——这些是一次性合规成本，请自行完成。
- 凭证只从 `ANDROID_CI_CONFIG` 目录读，**不进 git、不进日志、不进计划文件**。
- `status` / `plan` 严格只读；上传和提交是外部写操作，**必须经过人工确认门**，不会静默发布任何东西。
- 部分失败即停：任何一家提交失败，不盲目重试，先查当前状态防重复发版。

## 已知平台坑（详单见 provider-api.md）

- 腾讯更新说明**不能带 emoji**，每天限额 50 次更新调用
- vivo 生产配额有限，禁止盲重试，用只读查询核实状态
- 小米 API 不暴露审核状态，`/dev/query` 的 update 字段是能力位不是审核位
- OPPO 提交后要轮询任务状态，pending 不是失败

## License

MIT
