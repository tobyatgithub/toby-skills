# Toby's Skills

Toby（[@tobyatlarge](https://x.com/tobyatlarge) / [tobyatgithub](https://github.com/tobyatgithub)）的 AI agent skills 仓库。每个 skill 一个目录，独立安装、独立使用。

这里的每一个 skill 都是三件套：**给 agent 的操作规程（SKILL.md）+ 领域参考手册（references/）+ 配套 CLI（scripts/）**，全部来自真实生产项目的踩坑沉淀，不是 demo——首弹就服役于一个 20 个月 48 个版本的真实发版流程。

## 目录

| Skill | 一句话 |
|---|---|
| [android-apk-release](android-apk-release/) | 把中国大陆五家安卓商店（小米/荣耀/应用宝/OPPO/vivo）的 APK 更新压成 `status → plan → 确认 → 提交` 四步，可选自托管下载服务器 |

## 给 AI agent（如果你是被丢了这个仓库链接的 agent）

本仓库是 skills monorepo，**每个 skill 目录自包含，入口都是该目录下的 `SKILL.md`**。两条路任选：

1. **装进宿主 agent**（宿主支持 skills 规范时，推荐）：跑下面的安装命令，然后用户对 agent 说"用 android-apk-release 更新 APK"即可。
2. **不装直接用**：读 `android-apk-release/SKILL.md` 照做——它本身就是完整的操作规程；CLI 无需安装，用 `uvx --from <skill目录>` 直接跑（前提：本机有 [uv](https://docs.astral.sh/uv/)，Python ≥3.10）。

阅读顺序：本文件 → 目标 skill 的 `SKILL.md`（流程与安全规则）→ `references/provider-api.md`（仅在实际提交时读）→ `README.md`（凭证配置表）。

安全要点（对 agent 操作者也成立）：凭证只从 `ANDROID_CI_CONFIG` 目录读，不进 git、不进日志；`status`/`plan` 是只读的；任何上传/提交都需要人工确认，不允许静默发布。

## 安装

前置：Node.js ≥22.20（skills CLI 要求）。支持的 agent 见 [vercel-labs/skills](https://github.com/vercel-labs/skills)（claude-code、codex 等）。

```bash
# 交互式选择（推荐先 --list 看一眼）
npx skills add tobyatgithub/skills --list
npx skills add tobyatgithub/skills

# 只装单个 skill，全局可用
npx skills add tobyatgithub/skills --skill android-apk-release -g

# 装全部
npx skills add tobyatgithub/skills --all
```

手动安装：把对应 skill 目录拷贝（或 symlink）进你的 agent skills 目录即可。

## License

MIT
