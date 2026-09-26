# 将 🎬 Cine AI Video Director 分享给朋友

项目保持私有，没有发布到公开 npm。朋友安装的是你授权其访问的私有 GitHub 版本；这不会把仓库、图库或你的制作项目公开。

## 你先做什么

在 [GitHub 仓库](https://github.com/rickyk1z1/cine-ai-video-director) 的 **Settings → Collaborators** 中邀请朋友的 GitHub 账号。只有你决定分享给谁；安装器不会邀请他人或修改仓库权限。

朋友接受邀请后，可在浏览器中用自己的账号打开仓库。对个人账号拥有的仓库，协作者权限按 GitHub 当前实际支持范围授予；不要把“仅安装”理解成自动配置了只读角色。

你自己的视频项目与本地工作台数据不随 Skill 安装包分发。仓库里的参考图保留来源记录，私有分享也不意味着获得这些图片的公开转载许可。

## 朋友准备什么

- 能加载本地 Skill 的 Codex 环境。
- Node.js 20+（包含 npm）、Git。
- Python 3.10+ 和浏览器，用于运行工作台。
- 能访问该仓库的 GitHub 账号，以及可供终端 Git 使用的认证。

如果已经能在终端访问这个私有仓库，不用重新登录。没有配置 Git 认证时，可以使用官方 GitHub CLI：

```sh
gh auth login
gh auth setup-git
```

使用朋友自己的账号完成登录；不需要共享你的密码或令牌，也不要把令牌写进安装命令。GitHub CLI 只负责认证，Skill 的安装器不会自动安装它。

可先确认访问权限：

```sh
git ls-remote https://github.com/rickyk1z1/cine-ai-video-director.git HEAD
```

## 一条命令安装

```sh
npm exec --yes --package=github:rickyk1z1/cine-ai-video-director#v3.2.1 -- cine-ai-video-director
```

这条命令会下载指定版本并执行安装器，默认新安装目录为 `~/.agents/skills/cine-ai-video-director`。如果存在唯一的现役安装，沿用其安装根；已有受管理旧名 `cinematic-storyboard` 的安装，会核对文件后迁移为新名。

安装后新开 Codex 对话，必要时重启 Codex，然后说：

> 使用 cine-ai-video-director，帮我把这个想法做成分镜，先讨论视觉方向、拍法和生成路线。

完整步骤见[中文使用手册](USAGE.md)。媒体生成平台、账号和额度按需要另行配置；安装 Skill 不等于所有图片与视频接口都已接通。

## 更新或选择安装目录

更新时使用新发布页提供的版本号运行同一命令。安装器保护本地修改：检测到修改或新旧名称同时存在时，会保留原文件并停止。先让助手比较差异，不要直接删除自己的修改。

需要明确安装位置时，指定 Skill 的上一级目录：

```sh
npm exec --yes --package=github:rickyk1z1/cine-ai-video-director#v3.2.1 -- cine-ai-video-director --skills-root "$HOME/.codex/skills"
```

这些路径示例使用 macOS / Linux shell；Windows 使用自己的绝对安装路径。项目材料继续保存在原项目目录，不迁入 Skill。

## 常见问题

**看到 Repository not found 或无法下载。** 先确认朋友已经接受邀请、Git 正在使用正确账号，并且上面的 `git ls-remote` 能成功。浏览器能打开而命令不能，通常需要配置终端 Git 的认证。

**运行 `npx cine-ai-video-director` 找不到包。** 本项目没有发布到公共 npm 注册表；请使用上面带 GitHub 来源的完整命令。仍然是一条安装命令，但下载来源是私有 GitHub。

**出现旧安装含本地修改的提示。** 这表示安装器没有覆盖原文件。让助手核对实际差异，再迁移到唯一的新名称目录。

**取消仓库访问权限后，朋友已经装好的副本会消失吗？** 不会。撤销权限会阻止后续访问和下载，不会远程删除对方已经获得的本地文件。
