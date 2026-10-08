---
name: 40-speaker-script
description: "可选阶段：为已完成的 PPTX 生成逐页演讲备注与演讲稿，在阶段 1.1 询问是否生成。用于 pptx-workflow 的阶段 4。"
---

# 阶段 4：演讲稿（可选）

设计选择与数值判断统一按[设计判断与检查提示](../../shared/design-principles.md)执行；内容逻辑与可读性优先。

**停机点：无。** 本阶段只在用户于阶段 1.1 明确要求演讲稿时执行；完成后工作流结束。用户不需要时跳过本阶段，交付在 3.3 结束。

**开工前按需读取**：先读当前子步骤及[分步读取约定](../../shared/context-loading.md)，按执行约定索引只取本步骤所需章节。

前提：阶段 3.3 已完成（`07_delivery/deck.pptx` 与逐页人工对照审阅通过），`02_design/content.json` 的 `include_speaker_script` 为 `true`。

## 产物

| 文件 | 内容 |
|---|---|
| `08_speaker-notes/notes.json` | 逐页演讲备注（结构见 `shared/schemas/speaker-notes.schema.json`）：`pages[]` 按 `content.json` 页序一一对应，写 `id`、`notes`（该页怎么讲），可补 `seconds`、`evidence` |
| `08_speaker-notes/speaker-script.md` | 完整演讲稿：按页分节（`## S01 标题`），每节写开场、要点、数据口径与过渡句 |

## 怎么写

- 逐页备注写“这一页怎么讲”：先给结论，再给证据与口径（样本量、时间范围、限制），最后给过渡到下一页的句子；不要复述画面上的全部文字。
- 演讲稿与设计稿的最终文字一致：页面文字是给观众看的，讲稿是给讲述者说的；不得在讲稿里引入材料之外的新事实或新数字。
- 所有事实性表述都要能追溯到 `01_inventory/materials.json` 的材料，重要数字在 `notes.json` 的 `evidence` 里写材料编号。
- 语言、时长与受众按阶段 1.1 的确认结果；给出每页建议时长与全篇总时长，人工核对seconds之和与brief目标时长及可读的实际讲稿长度相符。
- 默认交付独立notes.json与speaker-script.md。需要写入PPTX原生备注栏时，同步deck-spec各页notes，通过构建器重新构建；重新渲染、prepare_review、release验证，更新PPTX及相关哈希与3.3完成记录。只有当前渲染和页面视觉未变、工具确认同一渲染版本时才复用对应审阅；不得直接改zip并沿用旧文件哈希。最后完成阶段4。

```powershell
python <skill>/shared/scripts/workflow.py <project> complete 4
```

`complete 4` 会核对：用户确实要求演讲稿、逐页备注覆盖全部页面且不是占位文字、演讲稿覆盖每一页与其标题。用户不需要演讲稿时不要执行本阶段——此时工作流在 3.3 交付结束。
