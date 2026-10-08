# 2.1c：展示代表页并取得方向选择

## 方案闸门

三版分别存入 `03_concepts/option-a`、`option-b`、`option-c`。把通道、模型路由、真实调用编号、提示词哈希、原始／规范化输出哈希、种子、采用或淘汰的 `GEN-###`、`edit_source` 编辑关系写入 `03_concepts/prompts/` 与 `generation-ledger.json`。

填写 `03_concepts/concept-review.md`：各方案的气质、视觉系统、结构图形语汇、生成与挑选过程、优点、风险、照片保真与预计可编辑程度。向用户展示三版全部代表页并询问选择或修改意见，状态置为 `awaiting_user`；在用户明确确认前不得生成整套预览。确认后用 `workflow.py approve concept --option <a|b|c> --evidence "实际确认记录"` 记录，再 `complete 2.1`，加载[完整预览子 skill](../../22-full-preview/SKILL.md)。不得伪造确认。
