"""Regenerate browser data and Markdown from atlas.json; no network access."""
from pathlib import Path
import json
r=Path(__file__).resolve().parents[1]
d=json.loads((r/'atlas.json').read_text());assets={a['id']:a for a in d['assets']}
(r/'atlas-data.js').write_text('window.STYLE_ATLAS = '+json.dumps(d,ensure_ascii=False).replace('</','<\\/')+';\n')
lines=['# 全球主流视觉定调库','',f"首版：{len(d['cards'])} 个方向，{len(assets)} 张本地参考图（部分为原站对比组图）。更新日期：{d['updated_at']}。",'', '打开同目录的 [离线选图页](index.html) 浏览、对比和生成定调说明。图片已保存在 images 内，无需联网；来源网站链接需要联网。','', '## 怎么选','', '先确定呈现形式，再选视觉方向，最后选择调性。赛博朋克、奇幻、超现实作为可跨形式组合的美术方向，不和真人、3D 或定格放在同一个层级。已有明确风格的项目可以直接跳过。','', '默认展示五个差异明显的示例起点；新项目推荐由助手结合品牌、受众、内容和用途提出 3–5 个方向。静态图片说明外观，不能证明动作或切镜质量。','', '“主流”按跨作品可辨认的常见方向人工筛选，不代表统计排名。图片中的人物、服装和构图不自动成为项目要求。原网站以作品或作者命名的预设已尽量转为可描述的视觉特征。','']
for fam,label in [(x['id'],x['name']) for x in d['forms']]+[('world','可跨形式组合的美术方向')]:
 lines+=['## '+label,'']
 for c in [c for c in d['cards'] if c['family']==fam]:
  lines+=['### '+c['name']+' · '+c['english'],'',c['definition'],'','适合：'+c['suited_for']+'。','','动态考虑：'+c['motion_guidance'],'','辨别与边界：'+c['boundary'],'','可选调性：'+'、'.join(c['suggested_moods'])+'。','']
  for aid in c['images']:
   a=assets[aid];lines+=['!['+c['name']+'参考]('+a['path']+')','',f"来源：[{a['publisher']} · {a['source_label']}]({a['page']})；{a['kind']}。",'']
  lines+=['定义参考：'+' · '.join('[来源页面]('+u+')' for u in c['definition_sources']),'']
lines+=['## 调性选择','']
for m in d['moods']:lines+=['- **'+m['name']+'**：'+m['guidance']]
lines+=['','## 来源与维护','','主要样图来自 Midlibrary 和 OpenArt；具体缺口补充作品官方参考。模型版本、来源、文件校验值与检查状态见 atlas.json。缩略图用于个人离线定调，不是生产用高清参考或公开素材授权。','','中文解释和应用建议为本库整理。条目真源为 atlas.json，运行 tools/rebuild_views.py 生成浏览器数据和本 Markdown；程序不联网。']
(r/'视觉风格图鉴.md').write_text('\n'.join(lines)+'\n')
print('Regenerated atlas-data.js and 视觉风格图鉴.md')
