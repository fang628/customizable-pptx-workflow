---
name: 12-content
description: "先按 PPT 要求选出文字与图片、写内容清单和来源索引并预留图片编号，再生成补充底图并回填结果。用于 pptx-workflow 的阶段 1.2。"
---

# 阶段 1.2：内容与素材清单

本阶段无用户停机点；子步骤之间连续执行到下一闸门或交付。

按下表顺序每次只读一个步骤。步骤编号不改变 workflow-state.json 的阶段编号。共享规范按[分步读取约定](../../shared/context-loading.md)选取章节；返工先查[依赖影响](../../shared/incremental-rework.md)。

| 子步骤 | 当前任务与详细指令 |
|---|---|
| 1.2a | [选内容并先写内容清单与来源索引](steps/copy.md) |
| 1.2b | [依清单生成三方向底图并登记真实结果](steps/images.md) |
| 1.2c | [回填清单并完成验收](steps/verify.md) |

本阶段完成后进入[下一阶段](../13-design/SKILL.md)。
