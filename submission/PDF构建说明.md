# 从 Markdown 生成 PDF

构建入口：`submission/build_pdf.py`。它只处理命令中指定的一份文档，不扫描目录，也不自动重建其他 PDF。

在仓库根目录的 PowerShell 中运行：

```powershell
# 技术报告
D:/anaconda/python.exe submission/build_pdf.py "submission/report/技术报告.md" --label "技术报告"

# 计划书：由作者编辑完成后执行
D:/anaconda/python.exe submission/build_pdf.py "submission/plan/项目计划书.md" --label "项目计划书"
```

默认在输入文件旁生成同名 PDF 及 `.build.json`，后者记录页数、源文件/PDF 摘要和字体路径。用 `-o "目标路径.pdf"` 可以指定其他输出；Markdown 原文不会改动。

## 支持的格式

- `#`、`##`、`###` 标题；普通段落；粗体；行内代码；Markdown 链接。
- 管道表格，表头可跨页重复。单元格内的字面竖线写为 `\|`。
- 单层项目符号、引用块和代码块。
- PNG/JPEG 图片：`![图注](assets/图片.png)`，路径相对 Markdown 所在目录。
- `<!-- pagebreak -->` 显式分页；图片按比例缩放并与图注一起排版。

SVG 或其他复杂图形请先导出 PNG。数学公式和嵌套 HTML 不按浏览器语法渲染，建议先导出图片后引用。表格列数不一致或图片缺失会明确报错。

## 字体与版式

A4，默认宋体正文、黑体标题，正文 11 磅、行距 19 磅。中文字体嵌入 PDF，默认路径为 Windows 的 `simsun.ttc` 与 `simhei.ttf`。

```powershell
D:/anaconda/python.exe submission/build_pdf.py "稿件.md" -o "稿件.pdf" --label "项目计划书" --font-size 11 --line-height 19
```

可用 `--font`、`--bold-font` 指定授权的 TTF/TTC 字体。依赖为 ReportLab、Pillow，本机 `D:/anaconda/python.exe` 已具备；其他环境按需安装 `reportlab pillow`。

构建日志提供实际页数；完成后打开 PDF 检查表格、页尾、截图和中文显示。构建脚本不读取产品数据库、不调用模型、不连接 3001。
