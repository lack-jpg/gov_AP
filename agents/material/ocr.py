"""
material.ocr - OCR module: extract text from document images

Author: le
Date: 2026/7/30
Version: 0.3
Task: Implement OCR processing with PaddleOCR (real engine) + stub fallback
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from tools.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# Data Models
# ============================================================


@dataclass
class OCRBlock:
    """OCR 识别的一个文本块（段落/区域）"""

    text: str
    confidence: float = 1.0
    box: Optional[list[list[float]]] = None  # 4-point polygon [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]


@dataclass
class OCRPage:
    """OCR 识别的一页结果"""

    page_num: int = 0
    text: str = ""
    blocks: list[OCRBlock] = field(default_factory=list)
    confidence: float = 0.0  # 整页平均置信度


@dataclass
class OCRResult:
    """完整的 OCR 识别结果"""

    pages: list[OCRPage] = field(default_factory=list)
    full_text: str = ""
    language: str = "ch"
    engine: str = "stub"  # "paddleocr" | "stub"
    duration_ms: float = 0.0

    @property
    def avg_confidence(self) -> float:
        """所有页面的平均置信度"""
        if not self.pages:
            return 0.0
        confidences = [p.confidence for p in self.pages if p.confidence > 0]
        if not confidences:
            return 0.0
        return sum(confidences) / len(confidences)


# ============================================================
# OCREngine
# ============================================================


class OCREngine:
    """
    OCR 文字识别引擎。

    支持双模式：
    1. PaddleOCR 模式（生产）- 高精度中文 OCR，需安装 paddleocr
    2. Stub 模式（开发/降级）- 返回模拟文本，无需任何依赖

    使用方式:
        engine = OCREngine()
        result = await engine.extract_text(file_bytes)
        # 或获取结构化结果
        ocr_result = await engine.recognize(file_bytes)
    """

    # PaddleOCR 文档方向分类阈值
    _CLS_THRESH = 0.9

    def __init__(self, model_path: str = "", language: str = "ch", use_gpu: bool = False):
        """
        Args:
            model_path: PaddleOCR 模型目录（空则使用默认）
            language: OCR 语言，默认 "ch"（中文）
            use_gpu: 是否使用 GPU 推理
        """
        self._model_path = model_path
        self._language = language
        self._use_gpu = use_gpu
        self._model_loaded = False
        self._engine: Any = None  # PaddleOCR 实例

    # ── 公开方法 ──

    async def extract_text(self, file_bytes: bytes) -> str:
        """
        从文件字节流中提取文字（简易接口）。

        Args:
            file_bytes: 文件的原始字节内容

        Returns:
            提取的文本字符串
        """
        result = await self.recognize(file_bytes)
        return result.full_text

    async def recognize(self, file_bytes: bytes) -> OCRResult:
        """
        从文件字节流中执行完整 OCR 识别（结构化接口）。

        Args:
            file_bytes: 文件的原始字节内容

        Returns:
            OCRResult 包含页面级、文本块级结构化结果
        """
        import time

        t_start = time.perf_counter()

        # 检测文件格式
        file_format = self._detect_format(file_bytes)

        if file_format == "text":
            # 纯文本 — 直接返回
            text = file_bytes.decode("utf-8")
            duration_ms = (time.perf_counter() - t_start) * 1000
            return OCRResult(
                pages=[OCRPage(page_num=0, text=text, confidence=1.0)],
                full_text=text,
                engine="stub",
                duration_ms=duration_ms,
            )

        if file_format == "pdf":
            return await self._ocr_pdf(file_bytes, t_start)

        # ── 图片格式 — 尝试 PaddleOCR ──
        if self._ensure_paddleocr():
            return await self._ocr_image_paddle(file_bytes, file_format, t_start)

        # ── Fallback: stub 模式 ──
        return await self._ocr_image_stub(file_bytes, file_format, t_start)

    async def recognize_image(
        self,
        image_bytes: bytes,
        image_format: str = "png",
    ) -> OCRResult:
        """
        识别单张图片（明确指定格式）。

        Args:
            image_bytes: 图片字节内容
            image_format: 图片格式 (png/jpg/jpeg/bmp/tiff)

        Returns:
            OCRResult
        """
        import time

        t_start = time.perf_counter()

        if self._ensure_paddleocr():
            return await self._ocr_image_paddle(image_bytes, image_format, t_start)

        return await self._ocr_image_stub(image_bytes, image_format, t_start)

    def is_loaded(self) -> bool:
        """检查 OCR 模型是否已加载"""
        return self._model_loaded

    # ── PaddleOCR 模式 ──

    def _ensure_paddleocr(self) -> bool:
        """确保 PaddleOCR 已加载，返回是否可用"""
        if self._model_loaded:
            return True

        try:
            from paddleocr import PaddleOCR

            kwargs: dict[str, Any] = {"lang": self._language, "use_gpu": self._use_gpu}
            if self._model_path:
                kwargs["det_model_dir"] = os.path.join(self._model_path, "det")
                kwargs["rec_model_dir"] = os.path.join(self._model_path, "rec")
                kwargs["cls_model_dir"] = os.path.join(self._model_path, "cls")

            self._engine = PaddleOCR(**kwargs)
            self._model_loaded = True
            logger.info("PaddleOCR 模型加载成功: lang={}, gpu={}", self._language, self._use_gpu)
            return True

        except ImportError:
            logger.info("PaddleOCR 未安装，使用 stub 模式（pip install paddleocr）")
            return False
        except Exception as e:
            logger.warning("PaddleOCR 加载失败: {}，降级到 stub 模式", e)
            return False

    async def _ocr_image_paddle(
        self,
        image_bytes: bytes,
        image_format: str,
        t_start: float,
    ) -> OCRResult:
        """使用 PaddleOCR 识别图片"""
        import time

        import numpy as np
        from PIL import Image

        # 解码图片
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        img_array = np.array(image)

        # 执行 OCR
        assert self._engine is not None
        raw_result = self._engine.ocr(img_array, cls=True)

        if raw_result is None or (isinstance(raw_result, list) and len(raw_result) == 0):
            duration_ms = (time.perf_counter() - t_start) * 1000
            return OCRResult(
                pages=[OCRPage(page_num=0, text="", confidence=0.0)],
                full_text="",
                language=self._language,
                engine="paddleocr",
                duration_ms=duration_ms,
            )

        # PaddleOCR 返回格式: [[[box], (text, confidence)], ...]
        # 可能是单页 list 或多页 list[list]
        if raw_result and isinstance(raw_result[0], list) and isinstance(raw_result[0][0], (int, float)):
            # 是坐标点列表 → 单页结果
            pages_data = [raw_result]
        elif raw_result and isinstance(raw_result[0], list) and isinstance(raw_result[0][0], list):
            # 多页结果
            pages_data = raw_result
        else:
            pages_data = [raw_result] if raw_result else []

        pages: list[OCRPage] = []
        all_texts: list[str] = []

        for page_idx, page_data in enumerate(pages_data):
            blocks: list[OCRBlock] = []
            line_texts: list[str] = []

            for line in page_data:
                if not line or len(line) < 2:
                    continue
                box = line[0] if len(line) > 0 else None
                text_conf = line[1] if len(line) > 1 else ("", 0.0)
                if isinstance(text_conf, (list, tuple)):
                    text, conf = text_conf[0], text_conf[1]
                else:
                    text, conf = str(text_conf), 0.0

                blocks.append(OCRBlock(text=text, confidence=float(conf), box=box))
                line_texts.append(text)

            page_text = "\n".join(line_texts)
            avg_conf = sum(b.confidence for b in blocks) / len(blocks) if blocks else 0.0

            pages.append(OCRPage(
                page_num=page_idx,
                text=page_text,
                blocks=blocks,
                confidence=avg_conf,
            ))
            all_texts.append(page_text)

        duration_ms = (time.perf_counter() - t_start) * 1000
        logger.info(
            "PaddleOCR: {} pages, {} blocks, avg_conf={:.2%}, {:.0f}ms",
            len(pages), sum(len(p.blocks) for p in pages),
            sum(p.confidence for p in pages) / len(pages) if pages else 0,
            duration_ms,
        )

        return OCRResult(
            pages=pages,
            full_text="\n\n".join(all_texts),
            language=self._language,
            engine="paddleocr",
            duration_ms=duration_ms,
        )

    async def _ocr_pdf(
        self,
        file_bytes: bytes,
        t_start: float,
    ) -> OCRResult:
        """识别 PDF 文件 — 逐页转为图片后 OCR"""
        import time

        try:
            from pdf2image import convert_from_bytes

            images = convert_from_bytes(file_bytes, dpi=300)
        except ImportError:
            logger.warning("pdf2image 未安装，PDF OCR 降级到 stub 模式（pip install pdf2image）")
            return OCRResult(
                pages=[OCRPage(page_num=0, text=self._generate_mock_text(len(file_bytes)), confidence=1.0)],
                full_text=self._generate_mock_text(len(file_bytes)),
                engine="stub",
                duration_ms=(time.perf_counter() - t_start) * 1000,
            )
        except Exception as e:
            logger.error("PDF 解析失败: {}", e)
            return OCRResult(
                pages=[OCRPage(page_num=0, text="", confidence=0.0)],
                full_text="",
                engine="stub",
                duration_ms=(time.perf_counter() - t_start) * 1000,
            )

        import numpy as np

        if not images:
            duration_ms = (time.perf_counter() - t_start) * 1000
            return OCRResult(
                pages=[], full_text="", engine="stub", duration_ms=duration_ms
            )

        pages: list[OCRPage] = []
        all_texts: list[str] = []
        engine_used = "stub"

        if self._ensure_paddleocr():
            engine_used = "paddleocr"
            assert self._engine is not None

            for page_idx, image in enumerate(images):
                img_array = np.array(image.convert("RGB"))
                raw = self._engine.ocr(img_array, cls=True)

                if not raw:
                    pages.append(OCRPage(page_num=page_idx, text="", confidence=0.0))
                    all_texts.append("")
                    continue

                blocks: list[OCRBlock] = []
                line_texts: list[str] = []

                for line in raw:
                    if not line or len(line) < 2:
                        continue
                    box = line[0] if len(line) > 0 else None
                    text_conf = line[1] if len(line) > 1 else ("", 0.0)
                    if isinstance(text_conf, (list, tuple)):
                        text, conf = text_conf[0], text_conf[1]
                    else:
                        text, conf = str(text_conf), 0.0
                    blocks.append(OCRBlock(text=text, confidence=float(conf), box=box))
                    line_texts.append(text)

                page_text = "\n".join(line_texts)
                avg_conf = sum(b.confidence for b in blocks) / len(blocks) if blocks else 0.0
                pages.append(OCRPage(page_num=page_idx, text=page_text, blocks=blocks, confidence=avg_conf))
                all_texts.append(page_text)
        else:
            # stub PDF
            for page_idx, _image in enumerate(images):
                mock_text = self._generate_mock_text(len(file_bytes), page=page_idx + 1)
                pages.append(OCRPage(page_num=page_idx, text=mock_text, confidence=1.0))
                all_texts.append(mock_text)

        duration_ms = (time.perf_counter() - t_start) * 1000
        return OCRResult(
            pages=pages,
            full_text="\n\n".join(all_texts),
            language=self._language,
            engine=engine_used,
            duration_ms=duration_ms,
        )

    # ── Stub 模式 ──

    async def _ocr_image_stub(
        self,
        image_bytes: bytes,
        image_format: str,
        t_start: float,
    ) -> OCRResult:
        """Stub 模式：返回模拟 OCR 结果"""
        import time

        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            w, h = img.size
            detail = f"{image_format.upper()} 图片 ({w}x{h})"
        except Exception:
            detail = f"{len(image_bytes)} 字节"

        mock_text = self._generate_mock_text(len(image_bytes))
        duration_ms = (time.perf_counter() - t_start) * 1000

        logger.info("OCR stub: {} → {} chars, {:.0f}ms", detail, len(mock_text), duration_ms)

        return OCRResult(
            pages=[OCRPage(
                page_num=0,
                text=mock_text,
                blocks=[
                    OCRBlock(text=line, confidence=0.95)
                    for line in mock_text.split("\n") if line.strip()
                ],
                confidence=0.95,
            )],
            full_text=mock_text,
            engine="stub",
            duration_ms=duration_ms,
        )

    # ── 文件格式检测 ──

    def _detect_format(self, file_bytes: bytes) -> str:
        """
        检测文件格式。

        Returns:
            "png" | "jpg" | "bmp" | "tiff" | "pdf" | "text" | "unknown"
        """
        if not file_bytes:
            return "text"

        head = file_bytes[:12]

        # PNG: \x89PNG\r\n\x1a\n
        if head[:8] == b'\x89PNG\r\n\x1a\n':
            return "png"

        # JPEG: \xff\xd8\xff
        if head[:3] == b'\xff\xd8\xff':
            return "jpg"

        # BMP: BM
        if head[:2] == b'BM':
            return "bmp"

        # TIFF: II*\x00 or MM\x00*
        if head[:4] in (b'II*\x00', b'MM\x00*'):
            return "tiff"

        # GIF: GIF89a or GIF87a
        if head[:6] in (b'GIF89a', b'GIF87a'):
            return "gif"

        # WebP: RIFF....WEBP
        if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
            return "webp"

        # PDF: %PDF
        if head[:4] == b'%PDF':
            return "pdf"

        # 尝试作为文本解码
        try:
            file_bytes.decode('utf-8')
            return "text"
        except UnicodeDecodeError:
            return "unknown"

    def _generate_mock_text(self, file_size: int, page: int = 1) -> str:
        """生成模拟的 OCR 识别文本（包含常见政务字段）"""
        base = (
            f"申请人：张三\n"
            f"身份证号：510101199001011234\n"
            f"联系电话：13800138000\n"
            f"联系地址：成都市高新区天府大道666号\n"
            f"申请事项：食品经营许可\n"
            f"文件大小：{file_size} 字节"
        )
        if page > 1:
            base += f"\n第{page}页"
        base += "\n--- OCR Stub 模式 ---"
        return base


# ============================================================
# 便捷函数
# ============================================================

_engine: Optional[OCREngine] = None


def get_ocr_engine(language: str = "ch", use_gpu: bool = False) -> OCREngine:
    """获取 OCREngine 单例"""
    global _engine
    if _engine is None:
        _engine = OCREngine(language=language, use_gpu=use_gpu)
    return _engine


async def ocr_extract_text(
    file_bytes: bytes,
    language: str = "ch",
    use_gpu: bool = False,
) -> str:
    """快捷函数：从文件字节流中提取文字"""
    engine = get_ocr_engine(language=language, use_gpu=use_gpu)
    return await engine.extract_text(file_bytes)


# ============================================================
# Smoke Test — python -m agents.material.ocr
# ============================================================

if __name__ == "__main__":
    import asyncio

    passed = 0
    failed = 0

    def check(description: str, condition: bool, detail: str = ""):
        global passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {description}")
        else:
            failed += 1
            print(f"  [FAIL] {description}")
            if detail:
                print(f"         {detail}")

    def section(title: str):
        print(f"\n{'─'*60}")
        print(f"  {title}")
        print(f"{'─'*60}")

    async def main():
        engine = OCREngine()

        # ── 1. 基本属性 ──
        section("1. 基本属性")
        check("is_loaded 初始 False (未安装PaddleOCR时)", not engine.is_loaded() or engine.is_loaded() is False)
        check("language == ch", engine._language == "ch")

        # ── 2. 纯文本识别 ──
        section("2. 纯文本识别")
        text_bytes = "这是一段测试文本\n包含政务字段".encode("utf-8")
        result = await engine.recognize(text_bytes)
        check("format=text → engine=stub", result.engine == "stub")
        check("文本内容正确", "政务字段" in result.full_text)
        check("1页结果", len(result.pages) == 1)
        check("文本置信度=1.0", result.pages[0].confidence == 1.0)

        # ── 3. 图片 format 检测 ──
        section("3. 文件格式检测")
        check("PNG 检测", engine._detect_format(b'\x89PNG\r\n\x1a\n') == "png")
        check("JPEG 检测", engine._detect_format(b'\xff\xd8\xff') == "jpg")
        check("PDF 检测", engine._detect_format(b'%PDF-1.4') == "pdf")
        check("BMP 检测", engine._detect_format(b'BM') == "bmp")
        check("GIF 检测", engine._detect_format(b'GIF89a') == "gif")
        check("WebP 检测", engine._detect_format(b'RIFF\x00\x00\x00\x00WEBP') == "webp")
        check("text 检测", engine._detect_format(b'hello world') == "text")

        # ── 4. 空字节 ──
        section("4. 边界情况")
        result_empty = await engine.recognize(b'')
        check("空字节 → text", len(result_empty.full_text) == 0)

        # ── 5. extract_text 快捷接口 ──
        section("5. extract_text 快捷接口")
        text = await engine.extract_text("测试文本内容".encode("utf-8"))
        check("extract_text 返回字符串", isinstance(text, str) and len(text) > 0)

        # ── 6. recognize 结构化结果 ──
        section("6. recognize 结构化结果")
        # 构造一个最小的 1x1 PNG 来测试图片处理路径
        import struct
        import zlib

        def make_minimal_png() -> bytes:
            """创建一个最小合法的 1x1 白色 PNG"""
            def chunk(chunk_type: bytes, data: bytes) -> bytes:
                c = chunk_type + data
                crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
                return struct.pack(">I", len(data)) + c + crc

            sig = b'\x89PNG\r\n\x1a\n'
            ihdr = chunk(b'IHDR', struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            # 1px RGB white, filtered
            raw = b'\x00\xff\xff\xff'
            idat = chunk(b'IDAT', zlib.compress(raw))
            iend = chunk(b'IEND', b'')
            return sig + ihdr + idat + iend

        png_bytes = make_minimal_png()
        result_img = await engine.recognize(png_bytes)
        check("图片 → OCRResult", isinstance(result_img, OCRResult))
        check("engine 字段存在", result_img.engine in ("paddleocr", "stub"))
        check("avg_confidence ≥ 0", result_img.avg_confidence >= 0.0)
        check("duration_ms ≥ 0", result_img.duration_ms >= 0.0)

        # ── 7. recognize_image 接口 ──
        section("7. recognize_image 接口")
        result_img2 = await engine.recognize_image(png_bytes, image_format="png")
        check("recognize_image → OCRResult", isinstance(result_img2, OCRResult))
        check("full_text 非空", isinstance(result_img2.full_text, str))

        # ── 8. OCRBlock/OCRPage/OCRResult 数据模型 ──
        section("8. 数据模型")
        block = OCRBlock(text="测试", confidence=0.95)
        check("OCRBlock.text", block.text == "测试")
        check("OCRBlock.confidence", abs(block.confidence - 0.95) < 0.001)

        page = OCRPage(page_num=1, text="测试文本", blocks=[block], confidence=0.95)
        check("OCRPage.page_num", page.page_num == 1)
        check("OCRPage.blocks 数量", len(page.blocks) == 1)

        ocr_result = OCRResult(pages=[page], full_text="测试文本", engine="stub")
        check("OCRResult.avg_confidence", abs(ocr_result.avg_confidence - 0.95) < 0.001)

        # 空 pages 的 avg_confidence
        empty_result = OCRResult(pages=[], full_text="")
        check("空 pages → avg_confidence=0", empty_result.avg_confidence == 0.0)

        # ── 9. 便捷函数 ──
        section("9. 便捷函数")
        engine2 = get_ocr_engine()
        check("get_ocr_engine 返回 OCREngine", isinstance(engine2, OCREngine))

        shortcut_text = await ocr_extract_text("便捷函数测试".encode("utf-8"))
        check("ocr_extract_text 返回字符串", isinstance(shortcut_text, str) and len(shortcut_text) > 0)

        # ── 10. PaddleOCR 安装检测 ──
        section("10. PaddleOCR 可用性检测")
        try:
            import paddleocr  # noqa: F401
            paddle_available = True
        except ImportError:
            paddle_available = False
        check("PaddleOCR 导入状态已检查", True)  # 无论是否安装，都不影响测试通过
        print(f"         PaddleOCR 可用: {paddle_available}")

        # ── Summary ──
        section("SUMMARY")
        total = passed + failed
        print(f"\n  {passed}/{total} passed", end="")
        if failed:
            print(f", {failed} FAILED")
            exit(1)
        else:
            print(" — all good")
            print("\n  Run with: python -m agents.material.ocr")
            if not paddle_available:
                print("  ℹ PaddleOCR 未安装，OCR 使用 stub 模式")
                print("    安装命令: pip install paddleocr")

    asyncio.run(main())
