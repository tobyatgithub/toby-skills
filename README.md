# Toby's Skills

Toby（[@tobyatlarge](https://x.com/tobyatlarge) / [tobyatgithub](https://github.com/tobyatgithub)）的 AI agent skills 仓库。每个 skill 一个目录，独立安装、独立使用。

写给 agent 的 skill = 一份操作规程 + 一本领域参考手册 + 必要时的配套脚本。这里的每一个都来自真实项目的踩坑沉淀，不是 demo。

## 目录

| Skill | 一句话 |
|---|---|
| [android-apk-release](android-apk-release/) | 把中国大陆五家安卓商店（小米/荣耀/应用宝/OPPO/vivo）的 APK 更新压成 `status → plan → 确认 → 提交` 四步，可选自托管下载服务器 |

## 安装

```bash
# 安装单个 skill
npx -y skills add tobyatgithub/skills -g android-apk-release

# 或全部
npx -y skills add tobyatgithub/skills -g --all
```

手动安装：把对应 skill 目录拷进你的 agent skills 目录（Claude Code / Codex 等支持 SKILL.md 规范的 agent 通用）。

## License

MIT
