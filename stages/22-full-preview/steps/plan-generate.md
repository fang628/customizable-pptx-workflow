# 2.2a：锁定风格并按页生成底稿

生图默认通过imagegen内置工具；外部接口仅在用户明确选择时使用。调用与结果登记统一按[生图通道契约](../../../shared/image-generation.md)。

职责、底图术语、页型例外、原生文字与返工路由统一见[阶段边界与返工路由](../../../shared/artifact-contract.md#阶段边界与返工路由)。

设计选择与数值判断统一按[设计判断与检查提示](../../../shared/design-principles.md)执行；内容逻辑与可读性优先。

**停机点：2.2（插入原图并逐页检查后的完整预览批准）。** AI 底稿生成完成不是停机点。完成原图插入并逐页实际查看后才运行 `await 2.2`；用户确认后再 `approve preview` 并 `complete 2.2`。

**开工前按需读取**：先读当前子步骤及[分步读取约定](../../../shared/context-loading.md)，按执行约定索引只取本步骤所需章节。

**提示词编写前再读**：每轮编写或修订提示词（含图生图返工）前，按[三个必读时点](../../../shared/operations.md#三个必读时点)按分步读取约定复核当前任务的相关规范片段并核对当前页项目工件，读后再写，自检不能替代阅读。

先核实 `03_concepts/approved-direction.md` 与 `03_concepts/approval.json` 确实包含用户选定，不能以文件存在代替批准。


## 文本框装饰（可选）

框内小元素装饰为可选项，可以写「无装饰」；选用时写清类型、颜色与位置，同级并列框保持一致，不遮挡文字。已批准设计未选用装饰时，不在预览或重建阶段额外补加。


## 原图比例闸门

整页任务size与供应商实际原图都必须是精确16:9（宽×9＝高×16）。请求默认1920x1080，asset_mode使用strict；不符合就退回并保留来源记录，不补边、不裁切修正。合格原图仅等比缩放到1920x1080后再审阅。


## 生图提示词的禁写信息

提示词的Markdown九项结构与嵌套分块树、禁写几何、参考图与返工要求统一见[生图提示词口径](../../13-design/references/gen-prompt-scope.md)；本文件只记录当前阶段的操作。


## 先把风格锁进设计稿

用户选定后在设计稿《全篇视觉约定》的「选定风格与色彩」及 previews.json 的 styleConstraints 写清项目配色、字体和跨页规则，逐页仅在「本页视觉差异与特殊说明」记录例外；每页提示词按[风格说明的具体程度](../../13-design/references/gen-prompt-scope.md#风格说明的具体程度)简要写清整体气质、配色和背景／文本框处理；共用风格概括继承，逐页补充差异，仅在必要时写材质光影或装饰细节。complete 2.2 核验本项目约束已记录。


## 全篇整页生成

- 每一页都用 AI 生成一张整页预览（精确 1920×1080），任务写入 `04_full-preview/generation-jobs.json`，真实调用记录写入 `generation-ledger.json`，规范化输出 `04_full-preview/assets/GEN-###.png`，保留这些 AI 原始输出；本地插入登记原图后，将最终完整预览保存到 `04_full-preview/slides/<Sxx>.png`，不得覆盖原始输出。
- **没有骨架图中转稿**：每一页都直接按设计稿生成。封面和目录给「该方向原底图（`hero-image`／`toc-image`）＋单页设计稿」，在原底图上构建，不画图片占位框，按[原底图构建契约](../../../shared/preview-contract.md#封面与目录的原底图构建)；分区及所有文本框、其他图形元素用提示词详细说明，不提供分块参考图。
- 不运行分块参考复制作为预览前置步骤，不把分块参考图加入 references；提示词提取、同一套配色、占位图与上传要求统一见[生图提示词口径](../../13-design/references/gen-prompt-scope.md)，promptSummary 记录实际采用的设计信息。
- 先dry-run自检任务和提示词，再按通道契约调用工具并登记；机检项目见生图提示词口径，不在此重复。
- 提示词登记：本阶段所有生图任务的提示词都要写进 `02_design/generation-prompts.md` 的「## 阶段 2.2」小节（逐任务写 id、素材编号、用途、参考图（风格参考、获准材料或返工原页）与提示词全文）。
- 逐页登记 `04_full-preview/previews.json`：`stage`、`styleDirection`、`styleConstraints`、`pages[]`（`id`、`file`、`jobId`、`sha256`、`promptSummary`，除封面／目录外的计划图片页还要写 `placeholders`），必须按 `content.json` 的顺序覆盖全部页面；`complete 2.2` 会核对页序、1920×1080、最终预览哈希与文件一致、AI 原始页哈希与账本一致、提示词任务页面绑定／分块方式与形态／风格约束／文字的语义角色／逐张图片位比例、以及占位块位置与比例（占位框换算的宽高比与登记原件默认相对偏差容差为 12%；多次修订后的有限放宽见比例契约）。

```powershell
python <skill>/stages/21-concepts/scripts/run_generation.py <project> --stage full
# 仅用户明确选择并配置外部CLI通道后执行；默认内置模式见生图通道契约
python <skill>/stages/21-concepts/scripts/run_generation.py <project> --stage full --execute
```
