<div align="center">

# PaddleOCR 文档识别 CLI

**将 PDF / 图片转为结构化 Markdown，基于 PaddleOCR AI Studio API**

[![npm](https://img.shields.io/npm/v/paddle-ocr-skill?color=cb0000&label=npm)](https://www.npmjs.com/package/paddle-ocr-skill)
[![Python](https://img.shields.io/badge/python-3.8+-aff.svg)](https://www.python.org)
![platform](https://img.shields.io/badge/platform-win%20%7C%20mac%20%7C%20linux-pink.svg)
[![license](https://img.shields.io/badge/license-Apache_2.0-green)](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE)

</div>

---
### 🤖 Claude Code Skill

本工具同时是一个 Claude Code Skill，安装后在 Claude Code 中自动触发：

- 说"帮我识别这个文档""把这个转成文字"并提供文件路径
- Skill 自动调用 `paddle_ocr.py --fuse`，输出 Markdown + 图片

Skill 定义文件为仓库根目录的 `SKILL.md`，核心脚本与本 CLI 共用 `scripts/paddle_ocr.py`。


## ✨ 特性

### 🔥 双模型融合识别
> *VL-1.6 提供版面结构 + PP-OCRv6 提供高精度文字，Markdown 格式与文字精度兼备。*

- **PaddleOCR-VL-1.6**：SOTA 视觉语言模型，输出结构化 Markdown（标题层级、图片引用、列表、表格）
- **PP-OCRv6**：纯文字识别引擎，字符精度最高，50+ 语言统一支持
- **融合模式** (`--fuse`)：取两者之长，用 OCRv6 高精度文字替换 VL 的正文段落，同时保留 Markdown 格式

### ⚡ 开箱即用

- 单文件一行命令，批量处理整个目录
- 多页 PDF 自动逐页解析
- 输出目录冲突时自动增量（`_1`、`_2`...），不会覆盖旧结果
- 内嵌图片自动下载，附带版面检测图和 OCR 标注图

### 🛡 健壮可靠

- 单任务最长等待 10 分钟，超时自动退出
- 网络失败自动重试 3 次（指数退避）
- LaTeX 数学公式默认转为纯文本（可读性更好）

---

## 📦 安装

```bash
npm install -g paddle-ocr-skill
pip install requests
```

## 🔑 配置

```bash
# 获取 Token → https://aistudio.baidu.com
setx PADDLE_OCR_TOKEN "你的token"
```

## 🚀 用法

```bash
# 融合模式（推荐）
paddle-ocr 文档.pdf --fuse -o ./out

# 纯文字识别
paddle-ocr 图片.jpg -o ./out

# 批量多文件
paddle-ocr a.pdf b.jpg c.png --fuse -o ./out

# 批量目录
paddle-ocr ./扫描件/ --fuse -o ./out

```

| 参数 | 说明 |
|------|------|
| `files` | 文件路径、目录或 URL（可多个） |
| `-o, --output-dir` | 输出目录（默认 `./ocr_output`） |
| `-t, --token` | API Token |
| `--fuse` | 融合模式，VL-1.6 + PP-OCRv6（推荐） |
| `--merge` | 多页合并为一个 `.md` |
| `--no-math` | 保留 LaTeX 数学公式原样 |
| `--textline-orient` | 文本行方向校正 |


### 输出

```
out/ 文档.md              ← Markdown 正文
     layout_det_res_0.jpg ← 版面检测图
     ocr_annotated_0.jpg  ← OCR 标注图
     ...
```

---

## ⚠️ 注意事项

需要联网调用 PaddleOCR API。文件上传至百度服务器处理，单文件建议 20 MB 以内。
