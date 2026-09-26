# SceneSpec 与 ShotSpec

> 详细技术参考，按[制作技术索引](../production-reference-map.md)选择本次需要的部分。当前分镜、已有决定、采用声音和所选路线优先；技术参数应在实际工具与版本中核对。


在修改 Blender 场景前，生成一个可重放、增量可更新的数据合同。保持 schema 小而严格；新的字段要有默认值和版本兼容方案。

## 当前工程真源与桥接

分镜权威仍为storyboard.json的当前内容，历史确认与范围制作授权由同一production记录解释；SceneSpec只保存工程实现。通过 [工程桥接](../previs-integration.md) 的previs_bridge.py从当前所选镜头及已选择工程参数派生，以can_prepare核对适用的确认或继续制作授权，保留shot稳定ID、source_binding、实际fps与整数帧范围。不新建project-state.json或另一个当前分镜。工程、硬件、manifest作为previs/asset记录的files引用；具体说明回到同一制作Markdown。

用户修改相关分镜后，bridge拒绝把旧SceneSpec冒充当前输入；范围外文字改动不使局部工程失效。工程中需要调整创作内容时同步当前工作台，再派生受影响工程版本；既有授权继续适用，不要求重走整段文字确认。技术实现变化留在新工程版本，不反向覆盖分镜。新source_binding.scope_version=2绑定当前范围；旧确认快照绑定继续读取。默认section时基保留原段累计帧位置，独立局部参考可明确用local时基且不声称原片source_frame_range；详见工程桥接。技术检查、继续制作授权与静态/动态实际采用分别记录；图片/声音的投产条件仍沿现有主Skill。

## 地点资产与场次引用

室内、室外、公共或私人场所等可独立使用的空间，默认作为一个完整地点资产复用。内部家具、常见道具、布局、尺度和锚点属于该地点整体，不因资产管理而拆散重建；小道具仅按实际跨地点复用价值独立登记。`asset_uses` 用于绑定完整资产与本场实例，不能替代 `assets` 中场次对象的稳定 ID。

```yaml
asset_uses:
  - asset_id: LOC_LOCATION_A
    asset_version: v001
    instance_id: ASTUSE_LOCATION_01
    kind: location
    library_ref: project_assets
    manifest_ref: "assets/locations/LOC_LOCATION_A/v001/asset-manifest.json"
    source_ref: "assets/locations/LOC_LOCATION_A/v001/location.blend"
    root_collection: AST_LOC_LOCATION_A
    use_mode: linked_collection
    placement: {location: [0, 0, 0], rotation_euler: [0, 0, 0], scale: [1, 1, 1]}
    local_variant_ref: null
    static_review_ref: "assets/locations/LOC_LOCATION_A/v001/validation-static.json"
    presentation_owner: SC_020
    imports_story_or_shot_data: false
```

`asset_id + asset_version + instance_id + placement` 必须齐全；不能把 `latest`、文件名猜测或 Blender 自动后缀作为版本。`placement` 是资产局部坐标到本场世界坐标的唯一入口，锚点、碰撞与导航引用都按该变换解释。同一资产可有多个 `instance_id`；实例改动不回写母资产。同一剧情地点必须固定使用原精确版本，新版升级或新地点派生要列出受影响的空间、锚点、走位和镜头。

地点资产只带可复用空间事实与自身静态能力，不带旧剧本、分镜、相机、角色、路径、Timeline Marker、镜头时长、动作/NLA、场次节奏、天气/氛围或视频提示词。本场灯光、道具状态、人物、镜头和动画归 `presentation_owner`，按本场 `SceneSpec` 重新建立。门轴等结构接口可以保留，旧场戏“何时开门”的动画不能带入。详细入库和能力保留边界见 [资产库](asset-library.md)。

项目本地临时改装通过 `local_variant_ref` 关联独立变体记录；新租客陈设、临时封锁或本場道具状态不应污染共享地点母资产。仅更换场次不构成资产新版，也不能因新分镜而重建一个外观或布局不同的“同一地点”。

真实类型或专业空间任务还应扩展两个顶层字段（旧 Schema 可保留未知字段）：

```yaml
scene_research_manifest:
  - id: SRC_01
    url: "https://..."
    source_type: official_plan
    evidence_level: confirmed
    claims: [entrance_to_lobby, table_games_zone]
    scope: "仅支持邻接关系，不支持材质"
design_intent:
  hierarchy: {primary_anchor: ENV_entry_canopy, destination_anchor: ENV_table_games}
  order: {grid: "6m", axis: "main_public_path"}
  transitions: [ENV_lobby, ENV_security_threshold]
  sightlines: [{from: CAM_SH_010, target: ENV_entry_canopy, status: planned}]
  semantic_elements: [{id: PRP_signage, purpose: wayfinding, lod: previs}]
```

`scene_research_manifest` 的来源结论必须标为 `confirmed`、`inferred` 或 `artistic`，并在 `assumptions` 中记录缺口；`design_intent` 用于检查层级、秩序、过渡、视线和语义道具是否真实存在。没有这些字段时，纯抽象/非现实场景可声明 `research_scope: not_applicable`。

- 所有 ID 在项目内唯一且稳定：场景、资产、对象、镜头、事件、动作片段、碰撞代理、光源和集合均不可依赖 Blender 的 `.001` 后缀。
- 顶层包含 `schema_version`、`project.id`、`seed`、`request_id`、`assumptions`、`warnings`、`source_refs` 与 `budgets`。
- 坐标为米，Z 轴向上；`fps`、帧范围、画幅、色彩管理必须显式记录。
- `sequence` 明确动作时间线、剪辑时间线和活动相机。`handoff_state` 必须挂在每个相邻镜头的 `continuity_link` 或 `camera_cut` 上，不能只放一个全局摘要。

## 节奏层级与优先级

已采用style记录 只定义跨场稳定的交付与影像边界，例如画幅/帧率、构图安全区、轴线和连续性原则、允许的运镜/手持条件、预演代理边界与长期禁用项。它不规定全片“慢节奏”或“快节奏”，也不直接给镜头指定时长、切点或抖动。节奏必须随当前故事段落、场次、节拍和镜头变化。

```yaml
screen_language_boundary:
  source_ref: "canon/screen-language.md"
  status: confirmed
  delivery: {aspect_ratio: "2.39:1", fps: 24}
  continuity: {axis_policy: preserve_unless_declared, screen_direction: preserve}
  camera_motion: {handheld: event_motivated_only, cruising_interpolation: linear}
  prohibitions: ["unmotivated_shake", "unreadable_action_cutting"]

sequence:
  id: SQ_010
  pacing_profile:
    energy_arc: "arrival -> pressure -> release"
    information_release: controlled
    scene_transition_intent: "raise_stakes"

scene:
  id: SC_020
  pacing_profile:
    mode: conversational_tension
    information_rate: measured
    performance_energy: restrained
    camera_energy: low
    editorial_density: sparse
    required_readability: [reaction_before_cut]

directing:
  beats:
    - id: BT_020
      purpose: pressure_rises
      trigger: "CHR_A notices the empty chair"
      visible_action: "CHR_A stops before the table"
      information_delta: "viewer understands the invitation was deliberate"
      resulting_state: "CHR_A must decide whether to sit"
      pacing: {readability_window: reaction_before_cut, hold_reason: decision}

shots:
  - id: SH_030
    frame_range: [73, 120]
    beat_ids: [BT_020]
    pacing:
      shot_role: reaction_and_decision
      editorial_pressure: hold
      performance_window: "CHR_A registers the chair before moving"
      camera_temporal_behavior: "slow_push_after_recognition"
      cut_condition: "decision becomes visible"
```

各层职责不能互相替代：`sequence` 描述跨场的能量与信息释放；`scene.pacing_profile` 定义本场表演、相机、剪辑与可读性合同；`beat.pacing` 说明观察、触发、行动、反应或结果需要何种读取窗口；`shot.pacing` 才落实为帧范围、镜头内速度、停留和切点条件。对话可以低运动、高信息压力；打斗可以高人物能量、稳定相机和稀疏切镜，以让攻击、结果和反应可读。不存在“一种项目节奏”自动套用到所有场次的规则。

覆盖优先级为：本轮用户明确要求 > 当前镜头已确认的有意例外 > Beat 目标 > Scene 的 `pacing_profile` > Sequence 节奏弧线 > `screen_language_boundary` > Skill 默认判断。上层只能约束边界，不能无理由改写下层的叙事需要；下层违反项目边界时，必须记录有意例外与导演理由。

节奏修改时同步受影响 Beat、镜头帧段/切点、角色 Curve 时间映射、停步/转身/道具事件、相机曲线与连续性状态；相关轨迹和提示词标为 `stale`，只更新本次需要的产物。Fast 只覆盖请求中的有限切点/帧段数据，未实现完整事件、源时间与剪辑时间映射校验；离线工具范围见 [交付检查](offline-handoff-check.md)。节拍可读性与节奏由用户查看确认；用户认可后直接交付提示词，不要求 Standard/Release。

## 最小结构

完整可解析的新任务示例见 [minimal-scene-spec.json](minimal-scene-spec.json)，采用 Schema 1.1、规则 3.1。它是单镜头无人物的静态产品构图计划，引用均在文件内有声明，性能测量为 `not_run/null`，不证明对象已在 Blender 中创建。复制后按本任务填写，不照抄示例预算或为无人物任务加角色资产。

使用 `scripts/previs/validate_handoff.py <项目根目录> --scene-spec <相对路径>` 可做已实现的 ID、帧范围、切点、预算字段和路径检查，能力边界见 [离线检查](offline-handoff-check.md)。该工具不取代完整 JSON Schema 验证或画面判断。

## 镜头字段

每个镜头必须包含帧范围、意图、景别、焦段、焦点、主体屏幕区域、路径和连续性链接。故事任务还必须把镜头绑定的 `beat_ids` 与 `pacing` 写清楚，说明这段时间为何停留、推进或切出；无节拍的纯功能镜头可声明 `pacing.not_applicable` 并说明原因。`sequence.camera_cuts` 是主时间线的唯一活动相机绑定/切换来源：首条可仅建立初始相机，不算画面内切镜；单镜头片可仅有首帧绑定且无相邻镜头links。镜头内部计算使用 `pre_roll/post_roll`，剪辑输出只使用 `edit_frame` 对应的有效区间。Blender 中可用单场景多相机 + Timeline Markers，或按镜头独立场景，但必须在合同中声明策略并能重建活动相机。

需要时增加：

- `movement`：`dolly|truck|pan|tilt|orbit|crane|handheld|zoom|pov|whip_pan|crash_zoom`，并带速度、加速度、jerk 和幅度上限。
- `dof.rack_focus`：明确起止帧、源焦点和目标焦点。拉焦是事件，不可由 look-at 隐式触发。
- `impact_shake`：关联接触事件、固定 seed、衰减、平移/旋转幅度；不得逐帧独立随机。
- `composition`：主体 bbox、headroom、look-room、安全框、地平线和前景遮挡目标。
- `axis_crossing`：跨轴原因和方式：`frontal_transition|camera_crosses_axis|intentional_jump_axis`。

## 动作与接触事件

默认结构动作记录角色/道具 ID、事件时间、起止位置与朝向、必要转折和结果状态；道具另记录位移、旋转、归属与释放/交接时刻。`intent|anticipation|execution|contact|recovery` 可用于描述节拍，不要求每个节拍都制作肢体动画。Seedance 2.5 的代理动作不强制填写 hitbox、支撑脚、冲量或 hit-stop。

仅在用户明确选择 `articulated_performance` 并要求详细攻防/接触时，按需要补充 `attacker`、`receiver`、`hitbox`、`receiver_hitbox`、`contact_frame`、`contact_tolerance_frames`、`impact_point`、`reaction_delay_frames`、`hit_result`、`impact_strength` 与 `hit_stop_frames`。

使用 `hit_result` 时只能是 `hit`、`miss`、`blocked` 或 `glancing`。实际撞击造成的反应不得早于接触帧；对手预判后的格挡/闪避属于独立的接触前行为。风格化例外记录范围与原因。默认抓握事件用道具所有者、代理锚点和释放帧表达，不要求手指动画。

## 连续性状态

对每一对相邻镜头至少交接：角色和道具的世界变换、速度、朝向、姿态、视线、手持/抓握关系、受伤或损坏状态、出入画、可见性、光照、天气与环境状态。每条 link 包含 `from_frame`、`to_frame`、`handoff_state`、`allowed_error` 和验证结果。跨轴、时间跳跃、主观镜头和故意跳切必须写明原因，不能以缺少状态掩盖。

## 默认验收阈值

以下阈值仅用于已选择执行的专项检查，不是用户确认后的交付门槛；足部与全身IK只适用于明确启用的完整肢体动画；无手圆柱代理不检查手部接触，启用简化手部时只按 [接触附件规范](contact-hand-ik.md) 处理对应镜头。阈值为启发式，可按 `style_profile` 或事件覆盖：足部接触点与支撑面误差参考 0.01 m，腾空相位不适用；接触事件位置误差参考 0.08 m；支撑脚相对锚点的屏幕残差参考 3 px/frame，注明分辨率；焦点误差参考主体深度范围的 10%；主体安全框外面积参考 5%。有意裁切、出画、失焦按镜头意图单列，不套成全片通用错误。

脚滑的世界检测在支撑物局部坐标比较实际接触点与参考锚点，此时不涉及相机。屏幕检测每帧用同一相机分别投影脚接触点和随支撑物移动的锚点，比较投影残差的时间变化；不同深度物体的相机运动投影不同，不能统一减去一次“相机像素位移”。

跨镜头连续性比较同一角色/道具在对应时间的状态，或按时间差推进后的运动预测残差：位置不超过 0.05 m、旋转不超过 5 度、速度不超过 0.25 m/s。不能直接用相邻帧原始位移判断跑动穿帮，也不能将这些阈值施加于硬切前后的两台相机。高速动作另外检查 m/s、deg/s、px/frame、加速度和 jerk；相机差分仅在连续镜头内部计算，硬切边界分段处理，不用单一帧位移阈值代替。

## 预算与退化

预算超限时按下列顺序退化：镜头外集合、远景 LOD、实例密度、纹理分辨率、粒子/模拟、细分。不得降低影响角色接触、遮挡、镜头构图或事件因果的几何，除非将风险写入 `warnings`。

## 1.1 硬件与性能记录

新任务显式引用工作区hardware-profile.json；数值起点与测量语义以 [performance-budget.md](performance-budget.md) 为唯一依据。schema要求1.1包含以下字段：

```json
{
  "schema_version":"1.1",
  "budgets":{
    "hardware_profile_id":"hw-local",
    "calibration_status":"heuristic",
    "visible_triangles":1500000,"expanded_visible_triangles":1500000,
    "objects":1500,"base_objects":1500,
    "instance_count_soft":20000,"texture_mb":1024,
    "target_fps":24,"viewport_status":"unverified",
    "render_resolution":[1920,1080]
  },
  "performance":{
    "hardware_profile_id":"hw-local","stage":"microbenchmark",
    "measurement_method":"not_run",
    "viewport_fps":null,"depsgraph_ms_p95":null,
    "warnings":["Realtime viewport playback is not verified"]
  }
}
```

这是合并进完整合同的片段，不是独立SceneSpec。预算值和实际测量不能互写；target_fps不能填入viewport_fps。扩展字段可带每镜头预算与实际原型/实例/视锥上界/内存统计。额外语义校验：旧visible_triangles等于新expanded_visible_triangles预算、objects等于base_objects；profile_id引用一致；所有camera_cut引用真实镜头/相机、帧段无意外空隙/重叠。单scene连续动作的source_frame默认等于edit_frame；时间重映射必须由实际动作轨实现，不能只改marker描述。

## 导演方案扩展（规则1.2，SceneSpec仍1.1）

本节为故事任务的制作约定，既有Schema允许额外字段，但不会自动验证其导演含义。纯静物/性能演示可省略不适用字段并说明范围。导演方案可先独立Markdown/YAML记录；执行前将采用方案映射到SceneSpec，不为保存计划伪造硬件测量或现成Blender对象。

- 顶层 `directing`：scene_question、character_objectives、viewer_alignment、audience_information、beats、style_contract、reference_roles、assumptions。每个 beat 包含 `id`、trigger、visible_action、information_delta、resulting_state；故事任务还记录 `pacing.readability_window` 与节拍目的，避免用全局“快/慢”替代可执行的读取条件。
- 顶层 `blocking`：坐标约定、可走区域/障碍、角色起止状态、actor_paths、camera_paths、aim_paths、focus_paths。自主行进默认 `actor_paths` 关联实际 Blender Curve 对象和稳定 `curve_id`，静态/载体父级/交接按 [联合路线](blocking-and-camera-paths.md) 声明来源；路径带 stable ID、owner、曲线对象、控制点、弧长/时间映射、空间点、时间标记、朝向策略及转身/停步/接触事件。Curve 模式由该 Follow Path 提供位置，parent 模式由声明载体提供，不重复驱动同一自由度；时间映射与空间曲线分开。
- 角色记录实际 `root_motion_owner`（默认 `curve_follow_path`，另可 `static`、`parent` 或明确来源）；只有启用高级肢体时记录 in-place 动作、支撑相位与混合边界，避免动作资源重复驱动位移。Fast 请求对应字段名为 `motion_owner`。
- 镜头扩展 `beat_ids`、`pacing`、viewpoint、information_delta、composition_start/end、movement_motivation、path_id、aim_id、focus_id、edit_in_reason/out_reason、readability_windows、intentional_exceptions。全局camera_cuts仍是实际切镜来源，不把每个beat自动转相机。
- `sequence` 显式记录编辑时间、源时间、mapping方式与跨场 `pacing_profile`；整数帧区间连续且端点定义一致，非整数秒只量化一次。剪辑handles、动作/模拟pre-roll与读取动作的时段分别记录；首尾不足的handles须真实延展或标不可用。
- `review` 分项记录 narrative、blocking、animation、camera、continuity、viewport、export 状态及证据。可用planned/not_built/unverified/checked等明确状态并注明方法；不设“字段齐全=电影感通过”的总分。

构图/路线/事件的必需字段应由本次采用方法决定，例如无拉焦镜头不必生成rack_focus事件。不得把常用字段清单扩大成每次都要走完整套导演流程的障碍。

## 3.1 可选记录与兼容

新项目在现有制作记录按需引用`creative_documents`与`stage_reviews`，保存创作资料和具体产物的展示/采用证据，见 [文档模板](production-document-templates.md)。连续项目另记`project_kind`、`work_scope`、章节多维进度、`last_checkpoint`和`resume_context`。选用圆柱模板时记录`character_geometry: cylinder_and_sphere`、`character_motion_scope: root_and_simple_bend`、4骨骼rig和H/W/D参数来源，遵循 [尺寸与弯曲标准](character-proxy-standard.md)。旧`root_and_torso_transform`及其他历史字段兼容读取，不自动重建认可模型。必要接触镜头另记录可选顶层`contact_hand_plan`，结构和`none/contact_ik`含义见 [简化手部IK](contact-hand-ik.md)；历史文件缺少此字段不代表要补手。新增字段由实际流程执行，旧JSON Schema不证明已完成访谈、展示、绑定、手部接触或变形支撑检查。

`shots[].shot_size` 写实际景别，不能使用 `planned_per_director_plan` 等逃避填写；摄影/色调有对应文档及镜头例外。工程表不能替代向用户展示的完整分镜表。

`generation_profile`、`delivery_contract`、独立产物状态与图片职责分别以 [视频交付](reference-video-delivery.md)、[图片流程](reference-image-driven-assets.md) 为准；不再复制完整字段定义。关键事件双重表达按 [结构预演](previs-visual-contract.md) 对齐。只保留当前任务需要的记录，不要求旧项目迁移全部档案。

统一使用 `information_rate` 和列表形式 `required_readability`。读取旧 `narrative_information` 时映射为 `information_rate`；旧可读性字符串转为单元素列表。`camera_energy` 新写取 low/medium/high 并说明变化，旧 low_to_medium 等值保留其含义，重写时依据当前场次落实，不能直接丢失原设定。Schema 容许扩展不代表语义已被自动验证。
