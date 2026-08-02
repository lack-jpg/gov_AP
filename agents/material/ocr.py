"""
material.ocr - OCR module: extract text from document images

Author: le
Date: 2026/7/30
Version: 0.2
Task: Implement OCR processing (stub mode), real OCR engine integration in Phase 3
"""
from __future__ import annotations

from tools.logger import get_logger

logger = get_logger(__name__)


class OCREngine:
    """
    OCR 文字识别引擎。

    当前为 stub 实现：返回模拟文本。
    Phase 3 接入真实 OCR 模型（PaddleOCR / Tesseract）。

    使用方式:
        engine = OCREngine()
        text = await engine.extract_text(file_bytes)
    """

    def __init__(self, model_path: str = ""):
        """
        Args:
            model_path: OCR 模型路径（Phase 3 使用）
        """
        self._model_path = model_path
        self._model_loaded = False

    async def extract_text(self, file_bytes: bytes) -> str:
        """
        从文件字节流中提取文字。

        Args:
            file_bytes: 文件的原始字节内容

        Returns:
            提取的文本字符串

        Raises:
            ValueError: 无法处理的文件格式
        """
        # ── Stub: 返回模拟文本 ──
        logger.info("OCR stub: extracting text from {} bytes", len(file_bytes))

        # 检测是否是图片格式（简单magic bytes检测）
        if file_bytes[:4] in (b'\x89PNG', b'\xff\xd8\xff', b'%PDF'):
            return self._generate_mock_text(len(file_bytes))
        else:
            # 尝试当纯文本处理
            try:
                return file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                logger.warning("OCR: unable to decode file as text, returning stub")
                return self._generate_mock_text(len(file_bytes))

    def _generate_mock_text(self, file_size: int) -> str:
        """生成模拟的 OCR 识别文本（包含常见政务字段）"""
        return (
            f"申请人：张三\n"
            f"身份证号：510101199001011234\n"
            f"联系电话：13800138000\n"
            f"联系地址：成都市高新区天府大道666号\n"
            f"申请事项：食品经营许可\n"
            f"文件大小：{file_size} 字节\n"
            f"--- OCR Stub 模式 ---"
        )

    def is_loaded(self) -> bool:
        """检查 OCR 模型是否已加载"""
        return self._model_loaded
