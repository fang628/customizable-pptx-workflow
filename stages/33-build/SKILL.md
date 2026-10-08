---
name: 33-build
description: "依据确认后的元素清单与素材，组装、校验、渲染和验收可编辑 PPTX 并交付。用于 pptx-workflow 的阶段 3.3。"
---

# 阶段 3.3：组装与验收

本阶段无用户停机点；子步骤之间连续执行到下一闸门或交付。

按下表顺序每次只读一个步骤。步骤编号不改变 workflow-state.json 的阶段编号。共享规范按[分步读取约定](../../shared/context-loading.md)选取章节；返工先查[依赖影响](../../shared/incremental-rework.md)。

| 子步骤 | 当前任务与详细指令 |
|---|---|
| 3.3a | [依据规格组装原生可编辑对象](steps/assemble.md) |
| 3.3b | [渲染并检查美观度、逐页对照](steps/polish.md) |
| 3.3c | [发布校验并交付](steps/release.md) |

本阶段完成后进入[下一阶段](../40-speaker-script/SKILL.md)（仅用户要求讲稿时继续；否则交付结束）。
