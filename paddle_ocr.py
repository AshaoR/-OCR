"""
PaddleOCR AI Studio API - 文档识别工具
支持表格文档、图片、PDF的OCR识别，输出Markdown+图片

用法:
  python paddle_ocr.py <文件路径/目录/URL> [选项]
  python paddle_ocr.py a.pdf b.jpg c.png -o ./out    # 批量处理
  python paddle_ocr.py ./扫描件/ -o ./out --merge    # 处理整个目录

配置:
  首次使用需要设置API Token:
  1. 在 https://aistudio.baidu.com 注册并获取token
  2. 通过 --token 参数传入，或设置环境变量 PADDLE_OCR_TOKEN
"""

import argparse
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
DEFAULT_MODEL = "PP-OCRv6"
MAX_POLL_SECONDS = 600  # 单任务最长等待 10 分钟

# PP-OCRv6: text-only OCR, returns rec_texts with highest character accuracy (default)
# PaddleOCR-VL-1.6: vision-language model, returns structured Markdown (best formatting)

SUPPORTED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}

# Common LaTeX symbol → plain text mapping
LATEX_SYMBOLS = {
    # Comparison
    r"\geq": ">=",
    r"\leq": "<=",
    r"\neq": "!=",
    r"\equiv": "==",
    r"\approx": "~=",
    r"\propto": "~",
    # Logic
    r"\land": "&&",
    r"\lor": "||",
    r"\lnot": "!",
    r"\neg": "!",
    r"\wedge": "&",
    r"\vee": "|",
    # Operators
    r"\times": "*",
    r"\div": "/",
    r"\pm": "+/-",
    r"\mp": "-/+",
    r"\cdot": "*",
    r"\mid": "|",
    r"\setminus": "\\",
    r"\backslash": "\\",
    # Arrows
    r"\to": "->",
    r"\rightarrow": "->",
    r"\leftarrow": "<-",
    r"\Rightarrow": "=>",
    r"\Leftrightarrow": "<=>",
    r"\leftrightarrow": "<->",
    # Dots
    r"\ldots": "...",
    r"\cdots": "...",
    # Others
    r"\infty": "inf",
    r"\sqrt": "sqrt",
    r"\left|": "|",
    r"\right|": "|",
}

# LaTeX formatting macros to strip (NOT symbol commands like \geq, \leq)
LATEX_FORMAT_MACROS = [
    r"\scriptstyle",
    r"\operatorname",
    r"\boldsymbol",
    r"\mathbf",
    r"\mathrm",
    r"\mathtt",
    r"\mathsf",
    r"\mathit",
    r"\mathcal",
    r"\mathbb",
    r"\mathfrak",
    r"\text",
    r"\textbf",
    r"\textit",
    r"\texttt",
    r"\displaystyle",
    r"\textstyle",
]


def get_token(args_token):
    env_token = os.environ.get("PADDLE_OCR_TOKEN")
    if args_token:
        return args_token
    if env_token:
        return env_token
    return None


def latex_to_plain(text):
    """
    将LaTeX数学公式转为纯文本。
    只去掉格式化命令(\\mathrm, \\mathbf等)，保留符号命令(\\geq, \\leq等)。
    例如: $\\mathrm{do~s+=n-}$ -> do s+=n-
          $x\\geq10$ -> x>=10
    """

    def strip_formatting(inner):
        """递归去掉 \\macro{...} 形式的格式化命令"""
        prev = None
        while prev != inner:
            prev = inner
            for macro in LATEX_FORMAT_MACROS:
                # Match \macro followed by optional braces
                inner = _strip_macro(inner, macro)
        return inner

    def _strip_macro(text, macro):
        """去掉 text 中所有 \\macro{...} 或 \\macro (无参数)"""
        result = []
        i = 0
        mlen = len(macro)
        while i < len(text):
            if text[i:i + mlen] == macro:
                i += mlen
                # Check if followed by {args}
                if i < len(text) and text[i] == "{":
                    depth = 1
                    j = i + 1
                    while j < len(text) and depth > 0:
                        if text[j] == "{":
                            depth += 1
                        elif text[j] == "}":
                            depth -= 1
                        j += 1
                    if depth == 0:
                        # Extract content and recurse
                        content = text[i + 1:j - 1]
                        result.append(strip_formatting(content))
                        i = j
                    else:
                        # Unmatched brace, treat as literal
                        result.append(macro + text[i:])
                        i = len(text)
                else:
                    # \macro without braces — just skip it
                    pass
            else:
                result.append(text[i])
                i += 1
        return "".join(result)

    def replace_math(m):
        inner = m.group(1)
        # Unescape LaTeX special characters
        for esc in [r"\{", r"\}", r"\$", r"\_", r"\&", r"\#", r"\%", r"\|"]:
            inner = inner.replace(esc, esc[1:])
        # Strip formatting macros with their brace arguments
        inner = strip_formatting(inner)
        # Convert LaTeX symbol commands to plain text
        for symbol, plain in LATEX_SYMBOLS.items():
            inner = inner.replace(symbol, plain)
        # Remove leftover braces (stragglers from unmatched cases)
        inner = inner.replace("{", "").replace("}", "")
        # Replace tildes with regular space
        inner = inner.replace("~", " ")
        # Collapse multiple spaces
        inner = re.sub(r"\s+", " ", inner).strip()
        return inner

    # Replace $$...$$ blocks
    text = re.sub(r"\$\$(.+?)\$\$", replace_math, text, flags=re.DOTALL)
    # Replace $...$ blocks
    text = re.sub(r"\$(.+?)\$", replace_math, text)
    return text


def resolve_output_dir(base_dir):
    """增量处理: 如果目录已存在，自动添加后缀 _1, _2, ..."""
    if not os.path.exists(base_dir):
        return base_dir
    counter = 1
    while True:
        new_dir = f"{base_dir}_{counter}"
        if not os.path.exists(new_dir):
            return new_dir
        counter += 1


def collect_files(paths):
    """收集待处理的文件列表。目录会被展开，非支持格式会被跳过。"""
    files = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for ext in SUPPORTED_EXTS:
                for f in sorted(path.glob(f"*{ext}")):
                    files.append(str(f))
                for f in sorted(path.glob(f"*{ext.upper()}")):
                    files.append(str(f))
            # Deduplicate while preserving order
            files = list(dict.fromkeys(files))
        elif path.is_file():
            if path.suffix.lower() in SUPPORTED_EXTS or str(p).startswith(("http://", "https://")):
                files.append(str(p))
            else:
                print(f"跳过不支持的文件格式: {p}")
        else:
            print(f"跳过: 文件不存在: {p}")
    return list(dict.fromkeys(files))


def submit_job(file_path, token, model, optional_payload, retries=3):
    headers = {"Authorization": f"bearer {token}"}

    print(f"处理文件: {file_path}")

    for attempt in range(1, retries + 1):
        try:
            if file_path.startswith(("http://", "https://")):
                headers["Content-Type"] = "application/json"
                payload = {
                    "fileUrl": file_path,
                    "model": model,
                    "optionalPayload": optional_payload,
                }
                resp = requests.post(JOB_URL, json=payload, headers=headers, timeout=30)
            else:
                if not os.path.exists(file_path):
                    print(f"  错误: 文件不存在: {file_path}")
                    return None

                data = {"model": model, "optionalPayload": json.dumps(optional_payload)}
                with open(file_path, "rb") as f:
                    resp = requests.post(JOB_URL, headers=headers, data=data, files={"file": f}, timeout=60)

            if resp.status_code != 200:
                print(f"  请求失败 (HTTP {resp.status_code}): {resp.text}")
                return None

            result = resp.json()
            job_id = result["data"]["jobId"]
            print(f"  任务提交成功, Job ID: {job_id}")
            return job_id
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                print(f"  网络错误 (第{attempt}次): {e}，重试中...")
                time.sleep(2 ** attempt)
            else:
                print(f"  提交失败，已重试{retries}次: {e}")
                return None


def poll_job(job_id, token, max_wait=MAX_POLL_SECONDS):
    headers = {"Authorization": f"bearer {token}"}
    start = time.time()

    while True:
        elapsed = time.time() - start
        if elapsed > max_wait:
            print(f"  任务超时 (已等待 {int(elapsed)} 秒)")
            return None

        try:
            resp = requests.get(f"{JOB_URL}/{job_id}", headers=headers, timeout=15)
        except requests.exceptions.RequestException as e:
            print(f"  查询网络错误: {e}，继续等待...")
            time.sleep(5)
            continue

        if resp.status_code != 200:
            print(f"  查询失败 (HTTP {resp.status_code})")
            return None

        data = resp.json()["data"]
        state = data["state"]

        if state == "pending":
            print("  状态: 排队中...")
        elif state == "running":
            try:
                progress = data["extractProgress"]
                print(f"  状态: 处理中... {progress.get('extractedPages', '?')}/{progress.get('totalPages', '?')} 页")
            except KeyError:
                print("  状态: 处理中...")
        elif state == "done":
            extracted = data["extractProgress"]["extractedPages"]
            print(f"  处理完成! 共提取 {extracted} 页")
            return data["resultUrl"]["jsonUrl"]
        elif state == "failed":
            error_msg = data.get("errorMsg", "未知错误")
            print(f"  任务失败: {error_msg}")
            return None

        time.sleep(5)


def download_results(jsonl_url, output_dir, convert_math):
    resp = requests.get(jsonl_url)
    resp.raise_for_status()

    lines = resp.text.strip().split("\n")
    os.makedirs(output_dir, exist_ok=True)

    page_num = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue

        result = json.loads(line)["result"]

        # PP-StructureV3 format: layoutParsingResults → markdown
        for res in result.get("layoutParsingResults", []):
            md_text = res.get("markdown", {}).get("text", "")
            if md_text:
                md_text = html.unescape(md_text)
                if convert_math:
                    md_text = latex_to_plain(md_text)
                md_path = os.path.join(output_dir, f"doc_{page_num}.md")
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_text)
                print(f"  [OK] Markdown: {md_path}")

            for img_path, img_url in res.get("markdown", {}).get("images", {}).items():
                full_path = os.path.join(output_dir, img_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                try:
                    img_data = requests.get(img_url).content
                    with open(full_path, "wb") as f:
                        f.write(img_data)
                    print(f"  [OK] 图片: {full_path}")
                except Exception as e:
                    print(f"  [FAIL] 图片下载失败 ({img_path}): {e}")

            for img_name, img_url in res.get("outputImages", {}).items():
                try:
                    img_data = requests.get(img_url).content
                    img_path = os.path.join(output_dir, f"{img_name}_{page_num}.jpg")
                    with open(img_path, "wb") as f:
                        f.write(img_data)
                    print(f"  [OK] 图片: {img_path}")
                except Exception as e:
                    print(f"  [FAIL] 图片下载失败 ({img_name}): {e}")

            page_num += 1

        # PP-OCRv6 format: ocrResults → prunedResult.rec_texts
        for res in result.get("ocrResults", []):
            pruned = res.get("prunedResult", {})
            rec_texts = pruned.get("rec_texts", [])
            rec_scores = pruned.get("rec_scores", [])

            if not rec_texts:
                continue

            # Assemble text regions into reading order, filter artifacts
            lines_output = []
            for j, (txt, score) in enumerate(zip(rec_texts, rec_scores)):
                stripped = txt.strip()
                # Skip isolated page numbers (single digit at end of page)
                if stripped.isdigit() and len(stripped) <= 2:
                    continue
                lines_output.append(txt)

            md_text = "\n".join(lines_output)
            if convert_math:
                md_text = latex_to_plain(md_text)

            md_path = os.path.join(output_dir, f"doc_{page_num}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_text)
            print(f"  [OK] Markdown: {md_path}")

            # Download annotated OCR image
            ocr_img_url = res.get("ocrImage")
            if ocr_img_url:
                try:
                    img_data = requests.get(ocr_img_url).content
                    img_path = os.path.join(output_dir, f"ocr_annotated_{page_num}.jpg")
                    with open(img_path, "wb") as f:
                        f.write(img_data)
                    print(f"  [OK] OCR标注图: {img_path}")
                except Exception as e:
                    print(f"  [FAIL] OCR标注图下载失败: {e}")

            page_num += 1

    return page_num


def merge_output(output_dir, source_name):
    """将所有 doc_*.md 合并为一个文件，按页码排序。"""
    md_files = sorted(
        [f for f in os.listdir(output_dir) if re.match(r"doc_\d+\.md", f)],
        key=lambda x: int(re.search(r"doc_(\d+)", x).group(1)),
    )
    if len(md_files) <= 1:
        return

    merged_name = Path(source_name).stem + ".md"
    merged_path = os.path.join(output_dir, merged_name)

    with open(merged_path, "w", encoding="utf-8") as out:
        for i, fname in enumerate(md_files):
            with open(os.path.join(output_dir, fname), "r", encoding="utf-8") as f_in:
                content = f_in.read()
            if i > 0:
                out.write(f"\n\n---\n## 第 {i + 1} 页\n\n")
            out.write(content)
            os.remove(os.path.join(output_dir, fname))

    print(f"  [OK] 合并为: {merged_path}")


def process_one(file_path, token, model, optional_payload, base_output_dir, convert_math, do_merge):
    """处理单个文件，返回 (成功?, 页数)"""
    job_id = submit_job(file_path, token, model, optional_payload)
    if job_id is None:
        return False, 0

    jsonl_url = poll_job(job_id, token)
    if jsonl_url is None:
        return False, 0

    output_dir = resolve_output_dir(base_output_dir)
    page_count = download_results(jsonl_url, output_dir, convert_math)

    if do_merge and page_count > 0:
        merge_output(output_dir, file_path)

    print(f"  输出: {os.path.abspath(output_dir)} ({page_count} 页)\n")
    return True, page_count


# ---- Fusion mode (VL-1.6 structure + PP-OCRv6 text) ----

def text_similarity(a, b):
    """计算两段文本相似度 (0-1)，忽略空白差异"""
    from difflib import SequenceMatcher
    a = re.sub(r"\s+", "", str(a))
    b = re.sub(r"\s+", "", str(b))
    if not a or not b:
        return 0
    return SequenceMatcher(None, a, b).ratio()


def extract_vl_headings(vl_page):
    """从 VL-1.6 parsing_res_list 提取标题"""
    blocks = vl_page.get("prunedResult", {}).get("parsing_res_list", [])
    headings = []
    for i, block in enumerate(blocks):
        label = block.get("block_label", "")
        if label in ("doc_title", "paragraph_title"):
            headings.append((label, block.get("block_content", "")))
    return headings


def find_ocr_pos(heading_text, ocr_texts):
    """在 OCRv6 文本流中定位标题位置"""
    best_sim = 0
    best_idx = -1
    for i, txt in enumerate(ocr_texts):
        sim = text_similarity(heading_text, txt)
        if sim > best_sim:
            best_sim = sim
            best_idx = i
    return best_idx if best_sim > 0.3 else None


def fuse_page(vl_page, ocr_page):
    """融合单页: VL-1.6 markdown结构 + OCRv6高精度文字替换"""
    vl_md = vl_page.get("markdown", {}).get("text", "") if vl_page else ""

    ocr_data = ocr_page.get("prunedResult", {}) if ocr_page else {}
    ocr_texts = ocr_data.get("rec_texts", [])

    if not vl_md:
        # 没有VL markdown时降级为OCRv6纯文本+标题检测
        if not ocr_texts:
            return ""
        headings = extract_vl_headings(vl_page) if vl_page else []
        heading_positions = {}
        for label, htext in headings:
            pos = find_ocr_pos(htext, ocr_texts)
            if pos is not None:
                heading_positions[pos] = label
        lines = []
        for i, txt in enumerate(ocr_texts):
            txt = txt.strip()
            if not txt or (txt.isdigit() and len(txt) <= 2):
                continue
            if i in heading_positions:
                level = "#" if heading_positions[i] == "doc_title" else "##"
                lines.append(f"{level} {txt}")
                lines.append("")
            else:
                lines.append(txt)
        return "\n".join(lines)

    if not ocr_texts:
        return vl_md

    # 用OCRv6高精度文字替换VL markdown中匹配的正文段落
    # 按文本块顺序在markdown中定位，只替换首次出现，避免误伤子串
    vl_blocks = vl_page.get("prunedResult", {}).get("parsing_res_list", [])
    search_pos = 0
    for block in vl_blocks:
        vl_text = block.get("block_content", "")
        if not vl_text or len(vl_text) < 3:
            continue
        best_match = None
        best_sim = 0
        for ocr_txt in ocr_texts:
            sim = text_similarity(vl_text, ocr_txt)
            if sim > best_sim:
                best_sim = sim
                best_match = ocr_txt.strip()
        if best_match and best_sim > 0.5:
            idx = vl_md.find(vl_text, search_pos)
            if idx >= 0:
                vl_md = vl_md[:idx] + best_match + vl_md[idx + len(vl_text):]
                search_pos = idx + len(best_match)

    return vl_md


def process_fused(file_path, token, base_output_dir, convert_math):
    """双模型融合处理: VL-1.6结构 + PP-OCRv6精细文字（两模型并行提交）"""
    vl_payload = {
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": False,
    }
    ocr_payload = {
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useTextlineOrientation": False,
    }

    # Step 1 & 2: 串行运行两个模型（各约20-40秒）
    print("  [1/3] VL-1.6 结构识别")
    vl_job = submit_job(file_path, token, "PaddleOCR-VL-1.6", vl_payload)
    if vl_job is None:
        return False, 0
    vl_url = poll_job(vl_job, token)
    if vl_url is None:
        return False, 0

    print("  [2/3] PP-OCRv6 精细识别")
    ocr_job = submit_job(file_path, token, "PP-OCRv6", ocr_payload)
    if ocr_job is None:
        return False, 0
    ocr_url = poll_job(ocr_job, token)
    if ocr_url is None:
        return False, 0

    # Step 3: Fusion
    print("  [3/3] 融合")
    resp_vl = requests.get(vl_url)
    resp_vl.raise_for_status()
    resp_ocr = requests.get(ocr_url)
    resp_ocr.raise_for_status()

    vl_results = [json.loads(l.strip())["result"] for l in resp_vl.text.strip().split("\n") if l.strip()]
    ocr_results = [json.loads(l.strip())["result"] for l in resp_ocr.text.strip().split("\n") if l.strip()]

    vl_pages = vl_results[0].get("layoutParsingResults", []) if vl_results else []
    ocr_pages = ocr_results[0].get("ocrResults", []) if ocr_results else []
    max_pages = max(len(vl_pages), len(ocr_pages))

    all_parts = []
    for pg in range(max_pages):
        vl_pg = vl_pages[pg] if pg < len(vl_pages) else None
        ocr_pg = ocr_pages[pg] if pg < len(ocr_pages) else None
        md = fuse_page(vl_pg, ocr_pg)
        if md.strip():
            if pg > 0:
                all_parts.append(f"\n\n---\n## 第 {pg + 1} 页\n\n")
            all_parts.append(md)

    full_md = "".join(all_parts)
    full_md = html.unescape(full_md)
    if convert_math:
        full_md = latex_to_plain(full_md)

    # Save
    output_dir = resolve_output_dir(base_output_dir)
    os.makedirs(output_dir, exist_ok=True)
    stem = Path(file_path).stem
    md_path = os.path.join(output_dir, f"{stem}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(full_md)
    print(f"  [OK] 融合完成: {md_path}")

    # 下载 VL-1.6 和 OCRv6 的图片
    for pg in range(max_pages):
        vl_pg = vl_pages[pg] if pg < len(vl_pages) else None
        ocr_pg = ocr_pages[pg] if pg < len(ocr_pages) else None

        # VL-1.6 markdown 内嵌图片
        if vl_pg:
            for img_path, img_url in vl_pg.get("markdown", {}).get("images", {}).items():
                full_path = os.path.join(output_dir, img_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                try:
                    img_data = requests.get(img_url).content
                    with open(full_path, "wb") as f:
                        f.write(img_data)
                    print(f"  [OK] 图片: {full_path}")
                except Exception as e:
                    print(f"  [FAIL] 图片下载失败 ({img_path}): {e}")

            # VL-1.6 outputImages (标注图)
            for img_name, img_url in vl_pg.get("outputImages", {}).items():
                try:
                    img_data = requests.get(img_url).content
                    img_path = os.path.join(output_dir, f"{img_name}_{pg}.jpg")
                    with open(img_path, "wb") as f:
                        f.write(img_data)
                    print(f"  [OK] 图片: {img_path}")
                except Exception as e:
                    print(f"  [FAIL] 图片下载失败 ({img_name}): {e}")

        # OCRv6 标注图
        if ocr_pg:
            ocr_img_url = ocr_pg.get("ocrImage")
            if ocr_img_url:
                try:
                    img_data = requests.get(ocr_img_url).content
                    img_path = os.path.join(output_dir, f"ocr_annotated_{pg}.jpg")
                    with open(img_path, "wb") as f:
                        f.write(img_data)
                    print(f"  [OK] OCR标注图: {img_path}")
                except Exception as e:
                    print(f"  [FAIL] OCR标注图下载失败: {e}")

    print(f"  输出: {os.path.abspath(output_dir)} ({max_pages} 页)\n")
    return True, max_pages


def main():
    parser = argparse.ArgumentParser(description="PaddleOCR 文档识别工具")
    parser.add_argument(
        "files", nargs="+", help="本地文件路径、目录或URL（可多个）"
    )
    parser.add_argument(
        "--output-dir", "-o", default="./ocr_output",
        help="输出目录 (默认: ./ocr_output)",
    )
    parser.add_argument(
        "--token", "-t",
        help="PaddleOCR API Token (也可设置 PADDLE_OCR_TOKEN 环境变量)",
    )
    parser.add_argument(
        "--model", "-m", default=DEFAULT_MODEL,
        help=f"模型名称 (默认: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--doc-orient", action="store_true",
        help="启用文档方向分类",
    )
    parser.add_argument(
        "--unwarp", action="store_true",
        help="启用文档拉平（适合拍歪的文档）",
    )
    parser.add_argument(
        "--textline-orient", action="store_true",
        help="启用文本行方向校正",
    )
    parser.add_argument(
        "--merge", action="store_true",
        help="将多页结果合并为一个 Markdown 文件",
    )
    parser.add_argument(
        "--no-math", action="store_true",
        help="不转换 LaTeX 数学公式（保留原始格式）",
    )
    parser.add_argument(
        "--fuse", action="store_true",
        help="启用双模型融合: VL-1.6结构 + PP-OCRv6精细文字（精度最高）",
    )

    args = parser.parse_args()

    token = get_token(args.token)
    if not token:
        print("错误: 未设置 API Token")
        print("请通过 --token 参数或设置 PADDLE_OCR_TOKEN 环境变量提供 Token")
        print("Token 获取: https://aistudio.baidu.com")
        sys.exit(1)

    # Build optional payload
    model = args.model
    optional_payload = {
        "useDocOrientationClassify": args.doc_orient,
        "useDocUnwarping": args.unwarp,
    }
    if "VL" in model or "Structure" in model:
        optional_payload["useChartRecognition"] = False
    else:
        optional_payload["useTextlineOrientation"] = args.textline_orient

    convert_math = not args.no_math

    # 收集文件
    files = collect_files(args.files)
    if not files:
        print("错误: 没有找到可处理的文件")
        sys.exit(1)

    print(f"共 {len(files)} 个文件待处理\n")

    # 逐个处理
    success_count = 0
    total_pages = 0
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}]", end=" ")
        stem = Path(f).stem if not f.startswith(("http://", "https://")) else "url_doc"

        if args.fuse:
            out_sub = os.path.join(args.output_dir, stem)
            ok, pages = process_fused(f, token, out_sub, convert_math)
        else:
            out_sub = os.path.join(args.output_dir, stem)
            ok, pages = process_one(f, token, model, optional_payload, out_sub, convert_math, args.merge)

        if ok:
            success_count += 1
            total_pages += pages

    print(f"完成! {success_count}/{len(files)} 个文件成功, 共 {total_pages} 页")


if __name__ == "__main__":
    main()
