# 2.1c：展示代表页并取得方向选择

## 预览图由 AI 直接生成

- 三版预览图就是**AI 生成的整页设计图**（精确 1920×1080），不再用本地基本图形拼页面。
- 每页一条生图任务：任务写进 `03_concepts/generation-jobs.json`，真实调用记录写进 `generation-ledger.json`；规范化输出固定为 `03_concepts/assets/GEN-###.png`，再把同一张图放到对应方案的 `03_concepts/option-<x>/<Sxx>.png`。
- **没有骨架图中转稿**：每一页都直接按设计稿生成。封面和目录给「该方向原底图（`hero-image`／`toc-image`）＋单页设计稿」，在原底图上构建，不画图片占位框，按[原底图构建契约](../../../shared/preview-contract.md#封面与目录的原底图构建)；不提供分块示意图；可放已获准的旧稿代表页或已生成的同类预览作风格参考。分区及全部文本框、其他图形元素由提示词详细说明。
- 不运行分块参考复制作为预览前置步骤，不把分块参考图加入 references；提示词提取、同一套配色、占位图与上传要求统一见[生图提示词口径](../../13-design/references/gen-prompt-scope.md)，promptSummary 记录实际采用的设计信息。
- 先dry-run自检任务和提示词，再按通道契约调用工具并登记；机检项目见生图提示词口径，不在此重复。
- 提示词登记：本阶段所有生图任务的提示词都要写进 `02_design/generation-prompts.md` 的「## 阶段 2.1」小节（逐任务写 id、素材编号、用途、参考图（风格参考、获准材料或返工原页）与提示词全文）。
- 生成后逐页登记 `03_concepts/option-<x>/preview.json`（结构见 `shared/schemas/preview-pages.schema.json`）：`id`、`file`、`jobId`、`sha256`、`promptSummary`（除封面／目录外的计划图片页还要写 `placeholders`），可补 `iterations`、`review`。`complete 2.1` 会逐条核对：文件存在且为 1920×1080、阶段 2.1 的预览哈希／阶段 2.2 的 AI 原始页哈希与账本一致、任务元数据绑定页面，提示词不写内部任务页面绑定与分块方式／形态、文字的语义角色、逐张图片位比例、占位块位置与比例与图片计划一致（占位框换算的宽高比与登记原件默认相对偏差容差为 12%；多次修订后的有限放宽见比例契约）。

```powershell
python <skill>/stages/21-concepts/scripts/run_generation.py <project> --stage concepts
# 仅用户明确选择并配置外部CLI通道后执行；默认内置模式见生图通道契约
python <skill>/stages/21-concepts/scripts/run_generation.py <project> --stage concepts --execute
```

先dry-run检查任务，再按通道契约调用内置工具并登记结果；`--execute`仅用于已确认的外部CLI。生图不设次数预算：效果不理想就用 `edit_source` 生图编辑、改提示词重生成或追加候选，淘汰的候选同样保留登记与原因。除下文多轮失败后的本地空白图框修正外，被退回或需要修改的整页预览用图生图改原图：把被退回的那张图放进任务的 `references`（或用 `edit_source` 指向本地 `GEN-###`），提示词写明保留什么、改什么，在该图基础上重绘；不得重新文生图从头生成。


## 方案闸门

三版分别存入 `03_concepts/option-a`、`option-b`、`option-c`。把通道、模型路由、真实调用编号、提示词哈希、原始／规范化输出哈希、种子、采用或淘汰的 `GEN-###`、`edit_source` 编辑关系写入 `03_concepts/prompts/` 与 `generation-ledger.json`。

填写 `03_concepts/concept-review.md`：各方案的气质、视觉系统、结构图形语汇、生成与挑选过程、优点、风险、照片保真与预计可编辑程度。向用户展示三版全部代表页并询问选择或修改意见，状态置为 `awaiting_user`；在用户明确确认前不得生成整套预览。确认后用 `workflow.py approve concept --option <a|b|c> --evidence "实际确认记录"` 记录，再 `complete 2.1`，加载[完整预览子 skill](../../22-full-preview/SKILL.md)。不得伪造确认。
