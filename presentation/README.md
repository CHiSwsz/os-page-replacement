# 汇报 PPT

[下载 PowerPoint](page-replacement.pptx)。共 21 页，前 15 页约 10 分钟，后 6 页为详细缺页表、参数研究和复现说明。每页包含中文讲稿备注。

沿用用户提供的《第三讲_反向传播_修订版_v22》模板：16:9、白底、紫色标题、浅紫页脚、微软雅黑与 Consolas。原模板未修改，也未上传仓库。

11 个图表和 11 个表格均为 PowerPoint 原生对象。图表包含嵌入式工作簿，所有数据来自仓库的 CSV。缺页均值显示两位小数；图表内部数值保留最多八位小数，完整精度和逐次整数保留在 `results/`。

已用 PowerPoint 打开并渲染全部页面，检查文字溢出；在测试副本中修改图表数值、调整尺寸、编辑表格后保存重开，验证可编辑性。文件结构、原生图表工作簿对应关系和图表/附录表数据也经过校验。未验证 Google Slides。

`build.mjs` 是幻灯片内容与布局源文件，使用 `@oai/artifact-tool`。需提供原模板和相应运行库：

```bash
python3 presentation/export_data.py
export PAGING_PRESENTATION_TEMPLATE=/path/to/第三讲_反向传播_修订版_v22.pptx
node presentation/build.mjs
```

生成 `build/presentation/candidate.pptx` 草稿。发布文件额外经过 PowerPoint 兼容性处理：删除三个无标题图表的空标题占位符，将保存时展开的浮点数字恢复为构建时的八位小数，并为原生图表生成嵌入式工作簿。发布前必须重新检查版面和数据，不能将未经验证的草稿直接替代本文件。
