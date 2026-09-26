# 整包移植与运行条件

分享或安装时复制整个 `cine-ai-video-director` 目录，不只复制 SKILL.md。主入口、参考、标准库服务、工作台界面和 `assets/visual-style-atlas` 一起保留。图库含28个方向、53张本地图片及来源记录；atlas.json是唯一数据源，浏览器数据与Markdown是派生文件。图片的原来源和使用范围说明继续有效。

程序以脚本自身位置寻找Skill资源，项目数据由调用时的 `--directory` 指定。没有固定用户名、Obsidian库位置、项目身份、画布、私有主机或内嵌凭据；新项目可以放在其他目录。测试目录、实例端口与运行锁由本次工作台管理，不作为接收者必须复现的个人环境。

## 按用到的功能准备环境

| 功能 | 接收者需要准备 |
| --- | --- |
| 阅读Skill、文字方法与Markdown图鉴 | 能读取本地Markdown的工具；Skill的自动执行需要支持本地技能的助手环境 |
| 分镜工作台、自动保存、图序预演和图库浏览 | Python 3.10或更高、现代浏览器；基础服务只用标准库 |
| 宫格排版或提取 | Pillow，只在运行grid工具时需要 |
| 声音/视频长度、区间与结果技术检查 | 可在PATH调用的ffprobe；具体解码、转码任务按所用工具准备ffmpeg |
| 图像、声音或视频生成 | 接收者自己的可用平台、账号、凭据及本次授权；没有这些仍可做文字分镜和图库定调 |
| Blender预演 | 接收者选择并安装的Blender、适用MCP/连接及本机能力；未选不加载 |
| Topaz超分 | 接收者可用的Topaz应用与许可，按当前系统版本和实际界面适配；未选不阻挡素材采用 |

在支持本地Skill的环境中安装目录后，调用名仍是 `cine-ai-video-director`。也可独立打开基础工作台：

```text
python <Skill目录>/scripts/storyboard.py create --directory <新项目目录> --title 示例项目
python <Skill目录>/scripts/storyboard.py open --directory <新项目目录>
```

macOS/Linux可将 `python` 换为可用的 `python3`；Windows按本机安装使用 `python` 或 `py`。复制命令时把尖括号占位替换为实际路径，含空格的路径加引号。`open` 返回本机URL，图库位于这个URL的 `/style-atlas/index.html`；可通过工作台“更多操作”进入。直接文件浏览不支持时使用此入口，不需要远端网站服务。

## 兼容实现与实测范围

工作台锁区分Unix的fcntl与Windows的msvcrt，服务启动也区分进程分离方式；不无条件导入Unix模块。macOS已进行实际工作台、迁移安装目录、保存和图库验证。Windows分支通过模拟测试，尚未在原生Windows运行整条链路；本轮也未在Linux实机完整验收。不能将路径扫描、模拟分支或ZIP内容检查称为所有操作系统开箱即用。

迁移验收要检查整个包的资源、不同安装目录下的新项目创建/启动/读取，以及本地图片真实可见；对接收者新增的可选平台或应用，再分别核实其可用入口。已有项目采用素材的文件路径仍是该项目的数据，迁移项目时需一并迁移或重新映射，不把素材未带走误判成Skill有个人依赖。

实现依据：[Python msvcrt文件锁](https://docs.python.org/3/library/msvcrt.html)、[Python subprocess进程启动](https://docs.python.org/3/library/subprocess.html)。这些接口文档不等于本轮已经在Windows实机运行。
