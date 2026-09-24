# SceneSpec离线检查与旧包兼容

> 本地适配自TYGG AI Film Studio v3.2.7，详细技术参考，按[加载与输出映射](../tygg-reference-map.md)使用。现有主Skill的用户选择、确认节点、已采用声音及所选实现路径优先；不继承来源中的新增授权。版本/性能数字属于来源记录或启发式，执行时核对本机。


当前视频包由storyboard.py package检查。下列--package结构仅为TYGG旧包兼容读取/测试，不作为当前投产格式；工程桥接见[接入说明](../previs-integration.md)。

`scripts/previs/validate_handoff.py` 是仅用 Python 标准库的只读检查器。不启动 Blender、访问网络、生成媒体或改项目；用于首次写出较复杂的交付清单和 Skill 维护。它不作为每个短任务的强制阶段，更不在人工认可动画后重新审核画面。

```text
python -B validate_handoff.py <项目根目录> --scene-spec revisions/r001/scene-spec.json
python -B validate_handoff.py <项目根目录> --package revisions/r001/generation-package.json
```

可同时指定两项；`--hardware-profile hardware-profile.json` 可选，与 SceneSpec 配合核对 profile_id。参数文件及内部文件路径相对项目根目录；不同项目复制时只更换执行命令中的根目录。

## 检查范围

- SceneSpec：资产/镜头/事件 ID 重复、镜头与事件帧范围、镜头交叠/空隙、切点的镜头/相机声明与起始帧、连续性链接的镜头和帧、预算新旧别名以及性能记录中的硬件 ID。相机可由 camera.id 或 role=camera 的资产声明；声明不证明 Blender 对象存在。
- SceneSpec 显式文件字段 `manifest_ref`、`source_ref`、`scene_spec_ref`、`hardware_profile_ref`、`image_path`：项目内路径和文件存在性。不遍历所有字符串猜路径；库引用等符号字段不检查，URL 不视为本地文件。
- 视频包：引用 ID、文件存在/非空、已声明绑定的标签冲突、已知占位 PNG 标记、生成单位的引用与时长、1:1 源片段范围、必需人物图片的清单缺口。非线性/延长等时间映射标未验证，不假装自动支持。

`declared_checks_passed` 只代表上述声明项没有发现错误；文件存在不证明能解码、内容清晰或已上传。`needs_review` 表示待补素材/绑定、时间映射未知等具体警告；`error` 表示引用、范围、配置或读取错误。退出码 0 为无错误/警告，1 为需处理，参数错误为 2；不能把非零状态自动转换为重新审片或补渲染命令。

该工具不执行完整 JSON Schema 校验，不判断剧本细节是否表达、不测动画/碰撞、不自动核实媒体元数据和真实上传。完整素材读取及输出范围按 [视频交付](reference-video-delivery.md)。需要精确重映射时按实际编辑轨记录，不仅修改此清单。

## 可采用的视频包结构

以下是待补素材的示例，复制后填实际文件、时长与正文。`available: false` 和 `binding_status: planned` 会明确产生待办；不要求为了文件校验先上传或付费生成。

```json
{
  "revision_id": "r001",
  "required_character_ids": ["CHR_A"],
  "references": [
    {"id": "V1", "kind": "video", "path": "exports/reference.mp4", "available": false,
     "duration_seconds": 5, "binding_status": "planned", "label": null},
    {"id": "I1", "kind": "image", "role": "character_appearance", "asset_ids": ["CHR_A"],
     "path": "图片资产/03_人物A.png", "available": false, "binding_status": "planned", "label": null}
  ],
  "generation_units": [
    {"unit_id": "U1", "duration_seconds": 5, "time_basis": "local",
     "reference_ids": ["V1", "I1"], "source_reference_id": "V1",
     "source_range_seconds": [0, 5], "time_mapping": "one_to_one",
     "prompt": "条件稿：按已确认剧本写完整正文；实际上传后替换为对应标签。"}
  ]
}
```

`source_range_seconds` 用起点包含、终点不包含的秒范围，时长=end−start；SceneSpec 整数帧区间含首尾，时长=(end−start+1)/fps。示例 1–120 帧/24fps 对应 0–5 秒，避免多一帧/少一帧。未知实际时长不填猜测数值；以真实元数据补齐。

无人物项目 `required_character_ids: []`；主要角色分别对应实际人物图，不默认逐个登记背景群众。`required_character_ids` 为本包确实需要图像确定身份的角色，不强迫已明确不要人物图的用户补图。标签只有核实实际上传后才能标 `bound`，正文仍须写明素材职责；检查器不解析正文里的自然语言标签关系。

## 维护测试

```text
python -B -m unittest discover -s scripts/previs -p test_offline_workflow.py -v
```

测试实际脚本的纯逻辑和临时文件边界，包括 Channelbag 读取失败、NLA slot、载体父级、引用/时间/占位问题与文件不覆盖。Blender 数据接口采用替身，不称 Blender 5.2 实机通过；现有 `test_validate_previs_fast.py` 需在适合的 Blender 环境另行运行，不因维护规则而启动用户项目。
