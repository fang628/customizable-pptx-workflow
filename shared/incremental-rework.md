# 页面依赖与增量返工

## 变更检测

新完成记录保存 `dependencies`：全篇依赖指纹和按 Sxx 编号保存的页面指纹。页面指纹包含本页定稿、设计章节、图片意图与适配、事实来源与实际文件、所用生成任务及原始输出；重建和成品阶段还覆盖元素记录、素材及构建规格。

全篇字段、页序、章节导航、需求或风格规则改变时扩大验收范围；改一页文案、图片或所用素材时仅标记相应页面。共享素材用于多页时，这些页面一起失效。无法可靠按页解析的说明按全篇依赖处理；没有依赖快照的旧记录保守地重新验收，不推定页面已经批准。

```powershell
python <skill>/shared/scripts/workflow.py <project> impact
python <skill>/shared/scripts/workflow.py <project> impact --stage 2.2
```

## 状态与复用

`complete` 对相同工件及依赖幂等，不再无条件重置全部下游。受影响的已有阶段变为 `in_progress`，保存 `pending_pages`、`global_change`、旧文件指纹和依赖基线。未变化的阶段保留完成记录；未变化页面与素材可复用。文件指纹改变而依赖不变，也仍须按阶段原验收规则检查，不能自动重绑版本。

全篇构建、结构校验与交付仍完整运行；增量范围表示哪些页需要修订和重新审阅，不表示跳过全篇事实与完整性检查。

## 批准与审阅

新概念批准绑定选中方向的代表页，而非与代表页无关的正文。非代表页变化且全篇方向未变时可沿用风格选择；代表页或全篇视觉语言变化仍需重新确认。

完整预览批准保留逐页 `page_confirmations`，每条含依赖指纹、真实确认原话与日期。首次或全篇变化时整体批准；只有局部变化时，展示变化页并取得真实确认后执行：

```powershell
python <skill>/shared/scripts/workflow.py <project> await 2.2 --notes "S03 已修订、插入原图并复看；等待用户确认"
python <skill>/shared/scripts/workflow.py <project> approve preview --pages S03 --evidence "实际用户确认原话"
python <skill>/shared/scripts/workflow.py <project> complete 2.2
```

命令拒绝未确认的变化页、未知页、全篇依赖变化及缺少旧页面快照的局部批准。旧批准归档到 `approval-history/`；未变化页保留原确认，不伪造新批准。需求与风格选择仍整体确认。

生图缓存按本任务提示词、参考文件和本页依赖计算；不再以整份 content.json 或设计稿作每页缓存键。页面审阅仅在渲染字节和 `dependency_sha256` 同时相同时复用；内容、图片计划、预览、素材或原生构建规格变化，即使渲染看起来相同，也重新审阅该页。
