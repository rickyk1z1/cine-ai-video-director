# 快速验证请求与证据

> 本地适配自TYGG AI Film Studio v3.2.7，详细技术参考，按[加载与输出映射](../tygg-reference-map.md)使用。现有主Skill的用户选择、确认节点、已采用声音及所选实现路径优先；不继承来源中的新增授权。版本/性能数字属于来源记录或启发式，执行时核对本机。


用于 Blender 制作期间的数据初筛。主入口是 `scripts/previs/validate_previs_fast.py`，档位、审片与缓存规则见 [执行规范](blender-mcp-execution.md)。该脚本不生成审片图、不负责自动修复、不实现持久缓存；无需每次重新编写整套检查代码。

只在制作/修改需要检查相关数据或用户明确请求时运行。用户认可当前白模与动画后，按 [用户确认与视频提示词交付](../video-production.md) 直接交付，不为提示词导出再运行快速脚本；原有未验证项保持真实状态即可。

## 一次调用

在当前已授权制作批次中，将 SceneSpec 的本轮检查范围序列化为 JSON，登记到 `scene["previs_validation_request"]`。仅登记本次相关角色、镜头和障碍；相机改动时仍需列出镜头涉及的角色，才能检测主体投影。登记请求是元数据写入，检查脚本本身只临时切帧，不创建、保存或修改对象/动画。将审核过的脚本纯文本作为一次 `execute_blender_code.code` 发送，读取其 `result`，不要逐对象、逐帧调用 MCP。

```json
{
  "mode": "fast",
  "revision_id": "r008",
  "change_scope": "camera_path",
  "affected_shot_ids": ["SH_020"],
  "active_camera_strategy": "single_scene_markers",
  "sample_stride": 6,
  "max_samples": 96,
  "max_seconds": 3.0,
  "risk_frames": [49, 72, 96],
  "characters": [{
    "id": "CHR_hero",
    "root": "CHR_hero_root",
    "path": "CRV_PATH_CHR_hero",
    "collision_radius_m": 0.35,
    "subject_points": ["CHR_hero_head", "CHR_hero_chest"]
  }],
  "collision_objects": ["ENV_COL_wall_left", "ENV_COL_wall_right"],
  "shots": [{
    "id": "SH_020",
    "frame_range": [49, 96],
    "camera": "CAM_SH_020",
    "subject": "CHR_hero",
    "safe_region": {"x": [0.05, 0.95], "y": [0.05, 0.95]},
    "camera_radius_m": 0.2,
    "check_occlusion": true
  }],
  "camera_cuts": [{"frame": 49, "camera": "CAM_SH_020"}],
  "motion_limits": {"camera_speed_mps": 4.0}
}
```

数值是示例，不是所有镜头的统一运动标准。距离指标要求米制且 `scale_length=1`；其他缩放明确报错，不能给出伪造的米/秒结论。角色没有位移时可声明 `motion_scope: static`，无需为静态代理强加 Follow Path。按镜头独立 scene 时使用 `active_camera_strategy: per_shot_scene`，只运行当前 scene 范围，并在外部验证剪辑时间线；Marker 检查仅适用于 `single_scene_markers`。

`risk_frames` 用于明确的转弯、贴墙、开门、停步、切点及其邻帧；脚本不会自动推断全部风险事件。显式 `sample_frames` 会替代自动采样计划，也受上限约束，必须自行包含这些关键帧。超长镜头或关键帧数量超过上限时按镜头/帧段分批，不能让限额截断被当作完整覆盖。未声明镜头时只做当前帧的可用检查，不回退到整片扫描。

## 初筛边界

- 碰撞代理必须是当前 view layer 中参与求值的简单 Mesh/Curve；拆出实际墙体、柱、门扇等障碍，不能拿包住整个室内空间的建筑包围盒作碰撞体。地面、角色自身和装饰散布不得混入墙体列表。
- 当前碰撞方法是角色 root 球体、相机球体对世界轴对齐包围盒，属于宽相候选；旋转物体、凹形道具和门洞可能误报，角色头身和采样之间的高速穿越仍可能漏检。命中后只对该对象/帧段细查：简单局部碰撞体、必要的 BVH/射线或扫掠，再在疑似区间加密采样；不要构造全场每帧 BVH，不为审核 Realize 植被实例。只有实际执行了专项检查才能登记其结果。
- 主体点使用求值后的世界位置与相机数据。圆柱＋球头代理声明球头中心、躯体中心/底部等实际点，不为检查造出手脚；已实际创建的简化手部可按需声明腕/掌或道具点，但不因检查而造手；高级人体才按需要声明脚点。特写只声明必须留在画内的点，不用根原点替代头部。允许出画/遮挡的帧段按镜头合同设置。角色身份、道具类别、景别美感不能靠点投影通过判定。
- 可选遮挡使用 `scene.ray_cast`，只代表当前依赖图的几何命中，不解释透明材质、最终渲染隐藏差异、全部实例或语义遮挡。相机包络检查不等于近裁切平面全部四角的扫掠。
- 默认 Curve 模式检查 root/父级 Action、NLA 与 Location Driver，以及 Follow Path 目标。按各自实际 slot 读取 layered Action；Channelbag、slot 或动画数据读取失败输出 `ANIMATION_DATA_UNREADABLE`，并把 `root_motion_sources` 放入 `unverified`，不能把空结果记为已排除位移冲突。
- 请求可显式使用 `motion_owner: parent` 和 `parent: 实际载体对象名`，此模式仅核对父级绑定、root 无 Follow Path/Location 动画；父级位移是允许来源。它不验证载体完整运动、骨骼、其他约束叠加或切换时段。`static`（或旧 `motion_scope: static`）跳过路径要求，不证明实际没有位移；其他来源输出 `UNSUPPORTED_MOTION_OWNER` 并保留未验证，不强行套 Curve。

3.1默认圆柱弯曲rig不改变root路线来源；本脚本仍不验证变形后网格与支撑面的关系，也不验证可选手部IK链、掌面接触或道具交接。需要处理坐、躺、起身时，只在制作中按 [尺寸与弯曲标准](character-proxy-standard.md) 做相应局部检查，不能把Fast根节点球体采样通过当作弯曲不穿地的证明。用户认可后不追加该检查。
- `full_constraint_and_parent_motion_composition` 与 `full_event_time_mapping` 始终保留未验证。控制来源跨时段切换必须按实际配置专项处理，不能把整段声明为纯 parent 冒充已验证交接。镜头运动阈值为镜内平移离散估计，不检验旋转抖动、完整 jerk 曲线或电影感。

## 限额与返回值

默认至多96个采样帧，3秒软时间预算；每帧只 `frame_set` 一次，共享该帧依赖图。时间预算在帧与帧之间检查，无法中断一个已经开始的高成本 Blender 求值/射线调用，也不能保证严格3秒返回。结束或检查异常后恢复原帧、子帧、活动相机；时间变化仍会触发场景现有 handler，含副作用 handler 的项目须在后台副本验证，不能承诺对任意第三方插件零副作用。

返回 `status`、`planned_sample_frames`、实际 `sample_frames`、`errors`、`warnings`、`unverified` 和 `timings.validation_wall_ms`。每组最多返回200条详细问题，超出以 `ISSUE_OUTPUT_LIMIT` 汇总，避免海量错误占用 MCP 输出。

- `sampled_checks_passed` 仅指声明项在实际采样范围内无报错；不是全片通过。
- `needs_review` 需要解释警告或补齐证据。没有障碍/主体点、采样截断、超时均不得记成通过。
- `error` 表示配置、约束、投影、代理碰撞候选或执行异常需要处理。宽相碰撞先局部核实，不直接为了消除包围盒误报修改场景。
- `unverified` 保留尚未覆盖的全人物碰撞、连续路径、导演质量和实时FPS等项目；没有检测器的项目不伪造检测结果。

将原始结果保存到当前 revision 的 `validation_run.json`，由执行端补上 `change_scope`、受影响 ID、MCP 往返时间、渲染时间和证据复用记录。脚本墙钟不能冒充总等待时间或视口FPS。下一轮先处理失败范围，未改变的图像/统计依据执行规范复用；脚本不会自动读取历史 JSON 来决定跳过什么。
