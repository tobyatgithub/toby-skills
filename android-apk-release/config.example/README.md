# 配置模板

1. 把整个目录拷到配置位置（默认 `~/.config/android-ci`）：

   ```bash
   cp -r config.example ~/.config/android-ci
   ```

2. 逐个文件填值：**以 `#` 开头的行是注释，会被忽略**，其余行就是值
3. 五家商店的文件全部必填；`self_hosted_*` 三个可选（不用自托管就删掉）
4. ⚠️ 这个目录含密钥，**永远不要提交进 git**

每个文件需要什么、去哪里拿，见各文件内注释；平台官方文档链接见 [../references/provider-api.md](../references/provider-api.md)。
