---
name: 31-element-audit
description: "逐页识别预览中的可见元素，记录坐标、样式、来源、叠放顺序和可编辑性，形成可供重建的清单。用于 pptx-workflow 的阶段 3.1。"
---

# 阶段 3.1：画面元素拆解

本阶段无用户停机点；子步骤之间连续执行到下一闸门或交付。

按下表顺序每次只读一个步骤。步骤编号不改变 workflow-state.json 的阶段编号。共享规范按[分步读取约定](../../shared/context-loading.md)选取章节；返工先查[依赖影响](../../shared/incremental-rework.md)。

| 子步骤 | 当前任务与详细指令 |
|---|---|
| 3.1a | [按页登记元素、文字几何与图片身份](steps/inventory.md) |
| 3.1b | [核对完整性后交给素材重建](steps/verify.md) |

本阶段完成后进入[下一阶段](../32-asset-rebuild/SKILL.md)。
