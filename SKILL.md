---
name: paddle-ocr
description: >
  中文OCR文档识别工具。使用PaddleOCR AI Studio API识别图片、PDF、表格文档中的文字，输出Markdown+图片。
  当用户说以下内容时触发：
  "帮我识别这张图里的文字"、"把这个文档转成Markdown"、"帮我把这份文件OCR一下"、"提取这个表格里的文字"、
  "帮我把这个PDF转成文本"、"识别这个图片"、"把这个扫描件转成文字"、"/ocr"、"paddle ocr"。
  即使是简单说"识别这个"、"帮我看这张图里写了什么"也应触发此skill。
  注意：此skill适合需要"识别文档并输出结构化Markdown"的场景。如果用户只是问图片内容而不需要输出文件，直接用多模态能力回答即可，不需要触发此skill。
---

# PaddleOCR 文档识别工具

使用 PaddleOCR AI Studio API 将图片、PDF 中的文字识别并输出为 Markdown 文本 + OCR 标注图片。

## 三种模式

| 模式 | 命令 | 原理 | 适用场景 |
|------|------|------|----------|
| **默认 OCRv6** | 直接运行 | 单模型文字识别，字符精度最高 | 纯文字文档，不需要结构 |
| **融合模式（推荐）** | `--fuse` | VL-1.6 提供 Markdown 结构 + PP-OCRv6 提供高精度文字 | **大多数文档**，需要保留标题、段落、图片结构 |
| **结构分析** | `-m PP-StructureV3` | 单模型表格/文档结构分析 | 含复杂表格的文档 |

> **模型说明：**
> - **PP-OCRv6**（默认）：纯文字识别，`rec_texts` 字符精度最高，但输出为无格式纯文本行
> - **PaddleOCR-VL-1.6**：视觉语言模型，输出结构化 Markdown（含标题层级、表格、图片引用、列表等），格式最好但正文文字精度略低于 OCRv6
> - **PP-StructureV3**：专为表格和文档结构设计，适合有复杂表格的文档
> - **融合模式** (`--fuse`) = VL-1.6 结构 + OCRv6 文字，既保留 Markdown 格式，又有最高文字精度

## 工作流程

### Step 1：确定输入文件

找到用户要识别的文件。以优先级排列：
- 用户直接给出的**文件路径**（如 `D:\扫描件\report.pdf`）
- 用户**拖拽/粘贴**到 IDE 中的图片 → 其路径通常形如 `C:\Users\用户名\AppData\Local\Temp\...`
- 用户提供的 **URL** 链接

如果用户没有给出具体路径，询问文件位置。

### Step 2：检查 API Token 配置

用户**首次使用**时，需要先配置 API Token。如果检测到用户尚未配置：

1. 引导用户到 https://aistudio.baidu.com 注册并获取 Personal Access Token
2. 建议用户通过设置环境变量 `PADDLE_OCR_TOKEN` 来配置，或在命令中直接传入

> 环境变量设置方式（Windows 建议持久化到用户变量）：
> `setx PADDLE_OCR_TOKEN "你的token"`

已配置则跳过此步。

### Step 3：运行 OCR 识别

调用 `paddle_ocr.py` 脚本处理文件：

```bash
# 基本用法
python paddle_ocr.py "<文件路径>" --output-dir "<输出目录>"

# 融合模式（推荐）—— VL-1.6 结构 + OCRv6 文字精度
python paddle_ocr.py "<文件路径>" --fuse -o "<输出目录>"

# 目录批量处理
python paddle_ocr.py "D:\扫描件" -o "./ocr_output"

# 多文件批量处理
python paddle_ocr.py a.pdf b.pdf c.jpg -o "./ocr_output"
```

**参数说明**：

| 参数 | 说明 |
|------|------|
| `files` | 文件路径、目录路径或 URL（可多个，空格分隔） |
| `--output-dir, -o` | 输出目录（默认: `./ocr_output`） |
| `--token, -t` | API Token，不传则读取环境变量 `PADDLE_OCR_TOKEN` |
| `--model, -m` | 模型名称（默认: `PP-OCRv6` 文字识别；可选 `PP-StructureV3` 结构分析） |
| `--fuse` | **融合模式**：VL-1.6 + PP-OCRv6 双模型，Markdown 格式 + 高精度文字（推荐日常使用） |
| `--merge` | 将多页结果合并为一个 Markdown 文件 |
| `--no-math` | 保留 LaTeX 数学公式（默认会转为纯文本） |
| `--textline-orient` | [PP-OCRv6] 启用文本行方向校正 |
| `--doc-orient` | [StructureV3] 启用文档方向分类 |
| `--unwarp` | [StructureV3] 启用文档拉平（适合拍歪的文档） |
| `--chart` | [StructureV3] 启用图表识别（适合含图表的文档） |

**常用示例**：

```bash
# 日常使用 —— 融合模式（格式 + 精度兼备）
python paddle_ocr.py "D:\文档\report.pdf" --fuse -o "./ocr_output"

# 纯文字文档 —— OCRv6 足够了
python paddle_ocr.py "D:\文档\notes.jpg" -o "./ocr_output"

# 含复杂表格 —— 结构分析模式
python paddle_ocr.py "D:\文档\table.pdf" -m PP-StructureV3 -o "./ocr_output"

# 拍歪的文档 —— 结构分析 + 拉平
python paddle_ocr.py "D:\照片\document.jpg" -m PP-StructureV3 --unwarp --doc-orient -o "./ocr_output"

# 批量处理整个目录
python paddle_ocr.py "D:\扫描件" --fuse -o "./ocr_output"
```

脚本会自动：
1. 提交文件到 PaddleOCR API
2. 轮询等待处理完成
3. **LaTeX 数学公式转为纯文本**（可读性更好，如 `$\mathrm{x}\geq10$` → `x>=10`）
4. 下载 Markdown 结果和内嵌图片到指定目录
5. 如果目标目录已存在，**自动创建增量目录**（`xxx_1`, `xxx_2`…），不会覆盖旧结果

### Step 4：展示结果给用户

输出目录结构示例：

```
ocr_output/
├── report.md          # 融合模式: 以文件名为名的 Markdown
├── doc_0.md           # 普通模式: 第1页的 Markdown
├── doc_1.md           # 普通模式: 第2页的 Markdown
├── images/
│   ├── img_001.png    # VL-1.6 内嵌图片
│   └── img_002.png
├── layout_det_res_0.jpg   # VL-1.6 版面检测图
├── ocr_annotated_0.jpg    # OCRv6 标注图
└── ...
```

处理完成后：
1. **直接读取生成的 md 文件显示给用户**，让用户看到识别结果
2. 告诉用户完整的输出目录路径

## 与纯图像理解的区分

此 skill 的核心价值在于**调用专业的 OCR 模型**来处理文档识别，特别适合：
- **表格文档**：含复杂表格结构的文档
- **多页 PDF**：需要逐页识别和输出
- **大量文字**的图片/扫描件
- **需要结构化 Markdown 输出**的场景

如果是简单的一张图片、几个文字，直接用内置多模态能力回答即可，不需要调用此 skill。

## 注意事项

- **网络要求**：需要联网调用 PaddleOCR API
- **文件大小**：API 对文件大小有限制（通常 20MB 以内），超大文件需要先压缩
- **Token 安全**：提醒用户不要将 Token 硬编码在脚本或分享给他人
- **隐私**：文件会上传到百度 AI Studio 服务器处理，敏感文件请谨慎使用
- **依赖**：需要 `requests` 库（`pip install requests`）
