<div align="center">
  <h1>PaddleOCR 文档识别 CLI 工具</h1>
  <p>基于 PaddleOCR AI Studio API 的图片/PDF 文字识别工具，输出结构化 Markdown + 图片</p>

[![Python](https://img.shields.io/badge/python-3.8+-aff.svg)](https://www.python.org)
![platform](https://img.shields.io/badge/platform-linux%2C%20win%2C%20mac-pink.svg)
![PyPI - Downloads](https://img.shields.io/badge/dependencies-requests-blue)
[![License](https://img.shields.io/badge/license-Apache_2.0-green)](https://www.apache.org/licenses/LICENSE-2.0)

</div>

---

## 📦 简介

轻量级 CLI 工具，封装 PaddleOCR AI Studio API，将 PDF、图片快速转为结构化 Markdown，内置三种识别模式：

- **PP-OCRv6** — 纯文字识别，字符精度最高
- **融合模式**（推荐）— VL-1.6 版面结构 + PP-OCRv6 高精度文字
- **PP-StructureV3** — 复杂表格/文档结构分析

---

## ✨ 特性

| 特性 | 说明 |
|------|------|
| **多格式支持** | PDF、PNG、JPG、BMP、TIFF、WebP、GIF |
| **三种识别模式** | 按需选择不同的精度/结构组合 |
| **批量处理** | 多文件或整个目录一键识别 |
| **自动增量** | 输出目录已存在时自动 `_1`、`_2`... 不覆盖 |
| **LaTeX 转换** | `$\mathrm{x}\geq10$` → `x>=10`，可读性更好 |
| **图片提取** | 自动下载内嵌图片、版面检测图、OCR 标注图 |
| **超时保护** | 单任务最长等待 10 分钟，网络错误自动重试 3 次 |

---

## 🔧 安装

```bash
pip install requests
```

## 🔑 配置 API Token

> Token 获取：[百度 AI Studio](https://aistudio.baidu.com)

**方式一：环境变量（推荐）**
```bash
setx PADDLE_OCR_TOKEN "你的token"
```

**方式二：命令行参数**
```bash
python paddle_ocr.py file.pdf --token "你的token"
```

---

## 🚀 用法

### 快速开始

```bash
# 日常推荐 —— 融合模式
python paddle_ocr.py 文档.pdf --fuse -o ./output

# 纯文字识别
python paddle_ocr.py image.jpg -o ./output

# 复杂表格
python paddle_ocr.py 表格.pdf -m PP-StructureV3 -o ./output

# 批量处理
python paddle_ocr.py a.pdf b.pdf c.jpg --fuse -o ./output

# 批量目录
python paddle_ocr.py ./扫描件/ --fuse -o ./output
```

### 参数列表

| 参数 | 说明 |
|------|------|
| `files` | 文件路径、目录路径或 URL（可多个） |
| `-o, --output-dir` | 输出目录（默认 `./ocr_output`） |
| `-t, --token` | API Token |
| `-m, --model` | 模型名称（默认 `PP-OCRv6`，可选 `PP-StructureV3`） |
| **`--fuse`** | **融合模式（推荐）** |
| `--merge` | 多页结果合并为一个文件 |
| `--no-math` | 保留 LaTeX 数学公式原样 |
| `--doc-orient` | 文档方向分类 |
| `--unwarp` | 文档拉平（适合拍歪的文档） |
| `--textline-orient` | 文本行方向校正 |

### 输出结构

```
output/
├── 文档.md              # 融合模式：以文件名为名的 Markdown
├── doc_0.md             # 普通模式：逐页 Markdown
├── images/
│   ├── img_001.png      # VL-1.6 内嵌图片
│   └── img_002.png
├── layout_det_res_0.jpg # 版面检测图
└── ocr_annotated_0.jpg  # OCR 标注图
```

---

## ⚠️ 注意事项

- 需要联网调用 PaddleOCR API
- 单文件限制通常 20MB 以内，超大文件需先压缩
- 文件会上传到百度服务器处理，敏感文件请谨慎
