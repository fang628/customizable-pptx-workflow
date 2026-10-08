---
name: 22-full-preview
description: "按确认方向生成整套 1920×1080 AI 底稿，本地插入全部登记原图，逐页实际查看后取得完整预览批准。用于 pptx-workflow 的阶段 2.2。"
---

# 阶段 2.2：完整预览（AI 整页生成）

本阶段仅在 **2.2 完整预览批准** 等待用户；子步骤之间连续执行。

按下表顺序每次只读一个步骤。步骤编号不改变 workflow-state.json 的阶段编号。共享规范按[分步读取约定](../../shared/context-loading.md)选取章节；返工先查[依赖影响](../../shared/incremental-rework.md)。

| 子步骤 | 当前任务与详细指令 |
|---|---|
| 2.2a | [锁定风格并按页生成底稿](steps/plan-generate.md) |
| 2.2b | [落实图片计划并本地插入原图](steps/insert.md) |
| 2.2c | [逐页查看并修订完整预览](steps/review.md) |
| 2.2d | [完成检查后提交用户批准](steps/approve.md) |

本阶段完成后进入[下一阶段](../31-element-audit/SKILL.md)。
