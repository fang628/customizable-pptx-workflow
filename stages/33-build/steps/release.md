# 3.3c：发布校验并交付

## 交付

把 `deck.pptx`、导出的 `deck.pdf`（如已使用 `-Pdf`）、可用的渲染图与总览图、`review-manifest.json`、`qa-review.json`、`qa-report.md` 放入 `07_delivery/`。说明渲染器版本、逐页对照检查结果、已做检查、字体或矢量限制、已批准的偏差，以及无法验证的事项。只有结构、页数、素材、计划图片填充和逐页人工审阅都通过，才标记完成；无法渲染时如实说明，不能宣称通过。

最后运行 `validate_project.py <project-dir> --mode release` 和共享 `workflow.py <project-dir> complete 3.3`。结构、准确文本和对象数量检查不能代替事实判断或图表数据核查。保留旧版本归档与构建记录。
