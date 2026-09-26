# 硬件与性能预算（1.2）

> 详细技术参考，按[制作技术索引](../production-reference-map.md)选择本次需要的部分。当前分镜、已有决定、采用声音和所选路线优先；技术参数应在实际工具与版本中核对。


本页用于实际制作负载规划和用户要求的性能检查。用户认可模型与动画后的提示词交付不触发硬件查询、校准或性能测量；按 [用户确认与视频提示词交付](../video-production.md) 直接继续。

## 启动测定

运行 `scripts/previs/probe_hardware.py --output <工作区>/hardware-profile.json` 只读采集硬件。再经MCP读取gpu.platform.renderer_get/backend_type_get、Blender版本、渲染引擎、FPS、实际VIEW_3D尺寸/模式。系统显卡列表不等于Blender活动显卡；Windows AdapterRAM是32位且可能错误，显存优先厂商工具。未知/统一内存标unknown，不当作零或独显；不相加多GPU显存。输出使用 [hardware-profile.schema.json](hardware-profile.schema.json)。

相同设备/驱动/Blender版本/引擎/视口尺寸/基准版本可复用档案；实际重负载操作前按需要刷新可用 RAM/VRAM。温度、电源模式、远程桌面或其他负载变化时先降低预算，确需性能判断再测，不自动启动基准场景。探测不读取序列号、账号或网络，不安装依赖。活动 GPU 未确认或显存未知时保守分档。

只有实际需要校准才创建测试场景，不作为每次制作前置任务。校准场景必须**参与求值且可见**；隐藏/排除集合不能测显示成本。先预热再测固定种子实例、植被风、移动镜头；角色rig另测，缺人物资产就标rig未测。使用1x/2x有限递增，不直接跑满配额。临时校准恢复用户状态；用户授权当前项目替换/保留时保留结果。

## 起始软预算

所有档目标一致：通常24fps；30/60fps按任务指定。硬件只给heuristic候选，对应模式/分辨率实际测过才能标calibrated。数值是保守起点，不是厂商保证，也不是必须填满的配额。

| 指标 | low | mid | high |
|---|---:|---:|---:|
| 候选依据 | 未知/集显或RAM<16GiB | RAM≥16GiB、活动独显≥6GiB | RAM≥32GiB、活动独显≥12GiB、CPU/求值充足 |
| 展开可见三角估算 | 500,000 | 1,500,000 | 3,000,000 |
| 场景基础Object | 500 | 1,500 | 3,000 |
| 当前镜头实例软上限 | 5,000 | 20,000 | 50,000 |
| 图像纹理估算MiB | 512 | 1,024 | 2,048 |
| 起始实时模式 | Solid/720p | Solid或轻Eevee/1080p | 轻Eevee/1080p |

当前余量不足时高档也降级。新增资产工作集起始不超过可用RAM一半；新增GPU分配不超过空闲VRAM一半，独显尽量保留max(2GiB,总量20%)可用。统一内存是同一共享池，不能重复分配。设备级GPU占用不称Blender专属消耗。

## 统计与验收

可把 `scripts/previs/inspect_performance.py` 纯文本送入官方 `execute_blender_code` 做当前帧只读审计；它不切帧、不写文件、不推导FPS，返回JSON result。含递归Realize检查、源/基础/实例计数、缓存求值网格、保守相机球-视锥上界；默认扫描最多250k记录或12秒，截断时上界为null。其统计是mesh-only，非mesh成本与精确透明过绘/遮挡不在内。基准计时与该审计耗时分离。

- 分开记录基础Object、唯一源网格/三角数、求值实例总数、相机可见实例估算。Realize增加真实几何但未必增加Object；Make Instances Real才建立Object，两者都查。
- expanded_visible_triangles = 求值后非实例几何 + 候选可见实例的求值源几何。包围盒/视锥法是上界估算，不是精确遮挡剔除；嵌套实例需避免重复计数。禁止为了统计先Realize。
- 区分RSS/working set、系统可用、设备GPU占用与纹理估算，未知为null。纹理压缩文件大小不是运行内存；宽×高×通道×字节数×mipmap系数也只是估算。
- frame_set+depsgraph的p50/p95是场景求值墙钟；MCP往返、截图、离线渲染秒/帧单列。timer轮询frame_current也不是呈现FPS。
- 真实播放在可见窗口测，并记录sync mode/视口尺寸/shading/时段。Play Every Frame推进可辅助观察；Frame Dropping进度可能掩盖丢帧。没有可靠呈现采集就设viewport_fps=null、viewport_status=unverified；用户目视确认为observed。完整playblast不代表实时通过。
- 24fps帧时41.7ms、30fps33.3ms、60fps16.7ms。有可靠采样时以呈现p95不超目标帧时验收；求值+绘制留30%余量更稳。只有求值数据不能判定实时达标。

超限WARN后按镜头外评估集合→远景LOD→实例密度→材质/纹理/阴影→模拟→细分降级。保留构图/接触代理。内存不足或未批准全量Realize为ERROR，停止扩建。软阈值例外记录镜头价值、测量证据和新预算。结构、求值、视口流畅度、预览完整性分别判定。

## 检查频率与缓存

性能检查与导演/几何审片分开记录，执行范围以 [Blender / MCP 执行规范](blender-mcp-execution.md) 为准。`Fast` 使用当前预算与已有统计，不调用全量 `inspect_performance.py`、不测播放 FPS。只有修改实际影响负载、用户报告卡顿或明确要求性能复核时，才选择必要测量；阶段完成和用户认可不触发审计、校准或 Release。用户认可当前模型与动画后按 [用户确认与视频提示词交付](../video-production.md) 直接交付。

确需 `inspect_performance.py` 时，它扫描当前帧/view layer，不支持按受影响集合自动缩小范围。实例循环有 250k 记录或 12 秒保护，但依赖图与节点遍历也耗时，12 秒不是整次调用超时；截断结果只能标 `partial_not_an_upper_bound`。完整正常速度预览或真实 FPS 测量仅在用户所要求的复核涵盖这些项目时执行。

首次设备测定和校准结果可以复用，依赖包括设备配置/驱动、Blender版本、活动GPU与后端、引擎、视口尺寸/模式、目标FPS和校准场景版本；当前可用RAM/VRAM需另行刷新。改变实例密度/GN/LOD/修改器或场景几何时，使相关几何统计和性能证据失效；改变渲染分辨率、透明、阴影、引擎、GPU/驱动、视口模式或目标FPS时，使相关视口/渲染结论失效。仅调整相机时保留未改变的源几何统计，使可见实例估算、遮挡和相关视口性能证据失效；相机驱动LOD/GN或时间求值变化另行触发几何重审。若要重算可见实例估算，现有性能脚本仍会扫描当前 view layer；不得宣称它已经实现独立增量重算。

这些缓存与失效约定是流程规则，现有脚本没有实现持久缓存。证据记录保存检测帧、scene/view layer、实际检查范围、来源 `revision`、资产/GN版本、渲染模式和测量方法；跨 revision 复用时记录当前引用版本与相关依赖未改变的依据，不把旧证据改写成新测量。预算、当前帧依赖图统计、离线渲染秒数与 FPS 不能互相替代；依赖变化或范围不明时标 `unverified`，不强制立即运行校准。性能统计也不能证明网格碰撞、脚底接触、轴线或导演审片通过。

## 植被与重复资产

禁止逐草叶/树叶/砂砾建大量Object、唯一Mesh、骨架/关键帧；近景少量交互可例外并记录数量。优先2–4个共享草簇原型，每簇20–100 triangles是起点；原型×实例仍受总几何预算控制。

使用Distribute Points on Faces→Instance on Points或共享预计算点云；暴露seed、密度/数量、缩放、区域、风。默认无Realize；局部接触或目标格式需要真实几何时在小副本里预估并转换。无用高LOD输入可能仍参与求值，须实际测量。

近景保轮廓和接触、中景低模簇、远景地表色块/低密度不透明几何/卡片。透明卡不天然便宜，过绘/阴影可能比低模不透明叶更慢；默认优先不透明几何，用卡时限制空白面积/层叠并测GPU。材质数不是draw call数；没测过就不伪造过绘层数。

风优先在共享草簇少量顶点上GN Set Position，再实例化，基部权重0顶端1；2–4相位簇避免全同步。远景小幅实例旋转可做代理。Eevee bump/法线/颜色不改变剪影，不能替代真实风动。近景接触用局部变形/代理，禁止每帧重建散布。

## 大场景、LOD与修改器

地块20–50m为起点，按镜头调整，组织ENV_SECTOR_*与共享源。Blender不因命名自动流式加载/LOD/剔除：必须实现集合排除、实例前选择、链接加载或代理策略，检查depsgraph是否减少。眼睛隐藏/相机外/Hide Render不保证所有求值停止；阴影/反射关联物不能只按相机裁掉。

连续镜头用全程可见范围+边缘余量，或稳定ID点云+距离选择；不要相机一动就重新随机散布。切点可换LOD；镜内切换检查闪跳，必要时固定LOD。近中远空间密度分区不是自动动态LOD。

Bevel视口通常1–2段，hero可3；Subdivision默认0–1，hero可2。Boolean超过3个、嵌套Realize、大Repeat Zone需成本评估；不一律套Mirror→Array→Bevel→Weighted Normal→Subdivision→Decimate。源可保留可编辑修改器，烘焙副本需有减少重复求值的依据。Array通常输出真实几何，不等于实例。

贴图通常1K–2K共享材质/图集，关闭无用高阶皮肤、毛发、体积、布料/流体。角色降级保护关节/接触。模拟限定帧段并缓存，固定seed；暂停动画不跑帧handler。超千米场景规划局部原点，同步相机/角色与轨迹。

依据：[Instance on Points](https://docs.blender.org/manual/en/5.2/modeling/geometry_nodes/instances/instance_on_points.html)、[Realize Instances](https://docs.blender.org/manual/en/5.2/modeling/geometry_nodes/instances/realize_instances.html)、[社区植被Skill](https://github.com/arjun988/blender-skills/blob/main/.claude/skills/vegetation-artist/SKILL.md)。预算数字为本Skill启发式。

## 批次与必要导出

“小批次”必须具体到本次要创建/修改的对象集合、单个资产、单个镜头或有限帧段；每批记录起止范围、已有成果、可恢复保存点与停止条件。未知负载从简单资产/短帧段起步，依据实际成本决定下一批，不能把整场构建放进一次主线程长循环。

先用已有硬件与场景记录保守估算；没有精度需要不跑校准场景。出口选能说明结构的低成本模式与任务所需画幅，必要视频导出按 [交付流程](reference-video-delivery.md) 串行完成并保留分段进度。标注实际帧数/分辨率/引擎，不承诺一个脚本软时限能防止所有卡顿或系统故障。

一次仅运行一个 Blender 重操作；不要同时渲染、测基准、散布大量实例。超时先确认正在执行还是已经部分完成，再决定恢复或缩批；不盲目重复写入/启动新进程。用户曾报告崩溃时沿用更保守的工作方式，无新负载问题不额外重测机器。
