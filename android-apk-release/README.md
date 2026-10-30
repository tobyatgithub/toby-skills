# android-apk-release

把一个**已经上架**的中国大陆安卓商店 APK 更新，压成四步：`status → plan → 人工确认 → 提交`。覆盖小米、荣耀、腾讯应用宝、OPPO、vivo 五家，外加可选的自托管下载服务器（不配置则只走五家商店）。

它是一个 AI agent skill，三件套：

- `SKILL.md` — 给 agent 的操作规程（先体检、再计划、人确认、后提交）
- `references/provider-api.md` — 五家签名算法与接口细节的踩坑手册
- `scripts/android_apk_release.py` — 配套 CLI（只读状态 / 发布计划 / 自托管发布）

## 边界（先读这个）

- 只做**更新已存在的应用**。不创建首次 listing，不代办软著、备案、开发者账号注册——这些是一次性合规成本，请自行完成。
- 上传和提交是外部写操作：skill 设计了人工确认门，不会静默发布任何东西。
- 凭证一律放 `ANDROID_CI_CONFIG` 目录（默认 `~/.config/android-ci`），不进 git、不进日志、不进计划文件。

## 安装

```bash
npx -y skills add tobyatgithub/skills -g android-apk-release
```

或安装本仓库全部 skills：

```bash
npx -y skills add tobyatgithub/skills -g --all
```

手动安装：把本目录拷进你的 agent skills 目录即可（Claude Code / Codex 等支持 SKILL.md 规范的 agent 通用）。

## 配置

一个文件一个值，放进 `ANDROID_CI_CONFIG`（默认 `~/.config/android-ci/`）：

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

## 用法

给 agent 用：装好后直接说"用 android-apk-release 发一个更新"，agent 按 `SKILL.md` 的流程走。

CLI 直接用（agent 内部也是调它）：

```bash
export SKILL_DIR=/path/to/this/dir

# 只读体检：五家商店（+自托管，如配置）当前状态
uvx --from "$SKILL_DIR" android-apk-release status

# 发布计划：APK 体检（完整性/ABI/签名/版本/SHA-256/隐私项）+ 各店版本核对
uvx --from "$SKILL_DIR" android-apk-release plan \
  --apk /absolute/path/app-release.apk \
  --notes-file /absolute/path/release-notes.txt

# 自托管发布（可选；仅在配置了 self-hosted 且五家提交全部成功后）
uvx --from "$SKILL_DIR" android-apk-release ship-server \
  --plan /absolute/path/release-plan.json \
  --confirm <plan 里的 confirmation_digest>
```

五家商店的提交动作由 agent 按 `references/provider-api.md` 执行；CLI 负责状态查询、计划构建、自托管发布这三件确定性的事。

## 已知平台坑（详单见 provider-api.md）

- 腾讯更新说明**不能带 emoji**，每天限额 50 次更新调用
- vivo 生产配额有限，禁止盲重试，用只读查询核实状态
- 小米 API 不暴露审核状态，`/dev/query` 的 update 字段是能力位不是审核位
- OPPO 提交后要轮询任务状态，pending 不是失败

## License

MIT
