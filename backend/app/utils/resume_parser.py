"""
简历解析工具
支持PDF、Word、图片等格式
"""
import os
import tempfile
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ResumeParser:
    """简历解析器"""
    
    def __init__(self):
        self.supported_formats = ['.pdf', '.doc', '.docx', '.txt', '.jpg', '.jpeg', '.png']
    
    async def parse(
        self,
        file_path: str,
        file_name: str
    ) -> Dict[str, Any]:
        """
        解析简历文件
        
        Args:
            file_path: 文件路径
            file_name: 文件名
            
        Returns:
            解析结果字典
        """
        try:
            # 获取文件扩展名
            ext = Path(file_name).suffix.lower()
            
            if ext not in self.supported_formats:
                raise ValueError(f"不支持的文件格式: {ext}")
            
            # 根据文件类型选择解析方法
            if ext == '.pdf':
                text = await self._parse_pdf(file_path)
            elif ext in ['.doc', '.docx']:
                text = await self._parse_word(file_path)
            elif ext in ['.jpg', '.jpeg', '.png']:
                text = await self._parse_image(file_path)
            elif ext == '.txt':
                text = await self._parse_text(file_path)
            else:
                raise ValueError(f"未知的文件格式: {ext}")
            
            # 提取结构化信息
            talent_data = await self._extract_info(text)
            
            return {
                "success": True,
                "text": text,
                "talent_data": talent_data,
                "confidence": 0.85  # 默认置信度
            }
            
        except Exception as e:
            logger.error(f"简历解析失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "text": None,
                "talent_data": None,
                "confidence": 0
            }
    
    async def _parse_pdf(self, file_path: str) -> str:
        """解析PDF文件"""
        try:
            import pymupdf as fitz  # PyMuPDF (新API，解决旧fitz在部分环境下的路径问题)
            
            text = ""
            with fitz.open(file_path) as doc:
                for page in doc:
                    text += page.get_text()
            
            return text.strip()
            
        except ImportError:
            logger.warning("PyMuPDF未安装，尝试使用pdfplumber")
            import pdfplumber
            
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
            
            return text.strip()
    
    async def _parse_word(self, file_path: str) -> str:
        """解析Word文件"""
        try:
            from docx import Document
            
            doc = Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
            
            return text.strip()
            
        except ImportError:
            logger.error("python-docx未安装")
            raise ImportError("需要安装python-docx库: pip install python-docx")
    
    async def _parse_image(self, file_path: str) -> str:
        """解析图片文件（OCR）"""
        try:
            import pytesseract
            from PIL import Image
            
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image, lang='chi_sim+eng')
            
            return text.strip()
            
        except ImportError:
            logger.error("pytesseract或PIL未安装")
            raise ImportError("需要安装pytesseract和Pillow库")
    
    async def _parse_text(self, file_path: str) -> str:
        """解析文本文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    
    async def _extract_info(self, text: str) -> Dict[str, Any]:
        """
        从文本中提取结构化信息
        
        Args:
            text: 简历文本
            
        Returns:
            结构化人才数据
        """
        # TODO: 使用LLM进行信息提取
        # 这里先返回基础结构，后续集成LangChain
        
        import re
        
        talent_data = {
            "name": None,
            "phone": None,
            "email": None,
            "education": None,
            "major": None,
            "experience_years": None,
            "current_company": None,
            "current_position": None,
            "self_introduction": None
        }
        
        # 提取手机号
        phone_pattern = r'(?:手机|电话|联系方式)[：:\s]*(\d{11})'
        phone_match = re.search(phone_pattern, text)
        if phone_match:
            talent_data["phone"] = phone_match.group(1)
        else:
            # 直接查找11位数字
            phone_match = re.search(r'1[3-9]\d{9}', text)
            if phone_match:
                talent_data["phone"] = phone_match.group(0)
        
        # 提取邮箱
        email_pattern = r'[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+'
        email_match = re.search(email_pattern, text)
        if email_match:
            talent_data["email"] = email_match.group(0)
        
        # 提取姓名（通常在简历开头）
        lines = text.split('\n')
        if lines:
            # 假设第一行是姓名
            first_line = lines[0].strip()
            if len(first_line) <= 4 and not re.search(r'\d', first_line):
                talent_data["name"] = first_line
        
        # 提取学历
        edu_pattern = r'(本科|硕士|博士|大专|高中)'
        edu_match = re.search(edu_pattern, text)
        if edu_match:
            talent_data["education"] = edu_match.group(1)
        
        # 提取工作年限
        exp_pattern = r'(\d+)\s*年.*经验'
        exp_match = re.search(exp_pattern, text)
        if exp_match:
            talent_data["experience_years"] = int(exp_match.group(1))
        
        return talent_data


# 全局实例
resume_parser = ResumeParser()
