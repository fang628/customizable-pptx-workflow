---
name: 32-asset-rebuild
description: "按元素清单，将非文字视觉元素重建为原生图形、经过验证的 SVG、原始照片或高分辨率位图素材。用于 pptx-workflow 的阶段 3.2。"
---

# 阶段 3.2：素材重建

本阶段无用户停机点；子步骤之间连续执行到下一闸门或交付。

按下表顺序每次只读一个步骤。步骤编号不改变 workflow-state.json 的阶段编号。共享规范按[分步读取约定](../../shared/context-loading.md)选取章节；返工先查[依赖影响](../../shared/incremental-rework.md)。

| 子步骤 | 当前任务与详细指令 |
|---|---|
| 3.2a | [逐个准备原生图形、SVG与局部素材](steps/rebuild.md) |
| 3.2b | [检查透明边缘、来源与重建完整性](steps/verify.md) |

本阶段完成后进入[下一阶段](../33-build/SKILL.md)。
