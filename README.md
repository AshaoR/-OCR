<div align="center">

# PaddleOCR 文档识别 CLI

基于 PaddleOCR AI Studio API，将 PDF / 图片转为结构化 Markdown。

[![Python](https://img.shields.io/badge/python-3.8+-aff)](https://www.python.org)
[![platform](https://img.shields.io/badge/platform-win%20%7C%20mac%20%7C%20linux-pink)](https://nodejs.org)
[![npm](https://img.shields.io/npm/v/paddle-ocr-skill)](https://www.npmjs.com/package/paddle-ocr-skill)
[![license](https://img.shields.io/badge/license-Apache_2.0-green)](LICENSE)

</div>

---

## 安装

```bash
npm install -g paddle-ocr-skill
pip install requests
```

## 配置

```bash
# 获取 Token: https://aistudio.baidu.com
setx PADDLE_OCR_TOKEN "你的token"
```

## 用法

```bash
# 融合模式（推荐）—— 结构 + 精度
paddle-ocr 文档.pdf --fuse -o ./out

# 纯文字
paddle-ocr 图片.jpg -o ./out

# 批量
paddle-ocr a.pdf b.jpg c.png --fuse -o ./out
paddle-ocr ./扫描件/ --fuse -o ./out
```

| 参数 | 说明 |
|------|------|
| `--fuse` | 融合模式，VL-1.6 结构 + PP-OCRv6 文字（推荐） |
| `--merge` | 多页合并为一个 `.md` |
| `--no-math` | 保留 LaTeX 原样 |
| `-o` | 输出目录，默认 `./ocr_output` |

## 输出

```
out/
├── 文档.md              ← Markdown 正文
├── layout_det_res_0.jpg ← 版面检测图
├── ocr_annotated_0.jpg  ← OCR 标注图
└── ...
```

## 注意

需要联网，文件上传至百度服务器处理，单文件建议 20 MB 以内。
