# 按需帮助

## 宿主没有发现技能

复制整个 `skills/<名称>/` 目录到宿主实际使用的技能目录，再重新加载。保留脚本、引用和 NOTICE、HELP；只复制 SKILL.md 会丢失功能。宿主不支持自动加载时，让模型读取对应 SKILL.md 及当前需要的引用即可。

## 安装世界书后找不到前置技能

把 progressive-reading、durable-task 和 novel-worldbook 安装为相邻目录。也可下载包含它们的合集包。不要通过删去前置说明绕过完整阅读。

## 账本、恢复包或运行环境不匹配

先确认使用的是通用 durable-task、Qoder Cloud 变体还是 BoundForge。三者有各自数据结构与命令，按对应 skill 的 HELP 处理；需要比较时看 [兼容性](docs/compatibility.md)。使用当前材料恢复，不让同名脚本改写不兼容的数据。

## BoundForge 找不到模块或搬迁后找不到论证

从安装后的 boundforge skill 目录运行程序，显式指定任务数据库路径。路径搬迁与分享记录的方法见 [BoundForge HELP](skills/boundforge/HELP.md)。

## 下载校验与维护检查

发布附件旁提供 SHA256SUMS.txt。核对相应文件的 SHA-256 后解压；有差异时重新下载，保留原文件以便比较。从克隆的仓库根运行 `python -B scripts/validate_collection.py` 检查目录、入口与相对链接；运行测试的命令和实际范围见 [验证记录](docs/validation.md)。
