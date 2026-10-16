# -*- coding: utf-8 -*-
"""
MinIO对象存储客户端
复用参考项目 D:\\PythonHayson\\ai_health\\0821\\app\\utils\\minio_client.py 逻辑
适配当前项目 config（pydantic-settings）+ 懒加载（@property）
"""
import logging
import os
from datetime import timedelta
from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error, InvalidResponseError

from app.core.config import settings

logger = logging.getLogger("MinioClient")


class MinioClient:
    """MinIO客户端（懒加载，MinIO不可用时不影响后端启动）"""

    def __init__(self, bucket_name: str = None):
        self._bucket_name = bucket_name
        self._client = None

    @property
    def client(self) -> Minio:
        """懒加载创建Minio客户端"""
        if self._client is None:
            self._client = Minio(
                endpoint=settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE
            )
        return self._client

    @property
    def bucket_name(self) -> str:
        return self._bucket_name or settings.MINIO_BUCKET

    def _ensure_bucket_exists(self):
        """确保默认桶存在，不存在则创建"""
        return self._ensure_custom_bucket(self.bucket_name)

    def _ensure_custom_bucket(self, bucket_name: str):
        """确保指定桶存在，不存在则创建"""
        if not self.client.bucket_exists(bucket_name):
            try:
                self.client.make_bucket(bucket_name)
                logger.info(f"创建MinIO存储桶: {bucket_name}")
                return True
            except S3Error as e:
                logger.error(f"创建MinIO存储桶失败: {e}")
                raise

    def _get_content_type(self, file_name: str) -> str:
        """根据文件名获取MIME类型"""
        ext = os.path.splitext(file_name)[1].lower()
        content_types = {
            '.txt': 'text/plain',
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.zip': 'application/zip',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.md': 'text/markdown; charset=utf-8',
            '.sql': 'text/plain; charset=utf-8',
            '.html': 'text/html; charset=utf-8',
            '.htm': 'text/html; charset=utf-8',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.svg': 'image/svg+xml',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.webp': 'image/webp',
        }
        return content_types.get(ext, 'application/octet-stream')

    def upload_file(self, file_object, original_name: str,
                    minio_object_name: Optional[str] = None) -> Optional[str]:
        """
        上传文件到默认桶
        :param file_object: 文件对象（字节流或带read方法的对象）
        :param original_name: 原始文件名（用于推断content_type）
        :param minio_object_name: MinIO中的存储名称（可选）
        :return: 存储的对象名称
        """
        try:
            if hasattr(file_object, 'read'):
                file_content = file_object.read()
                file_size = len(file_content)
                file_object.seek(0)
            else:
                file_content = file_object
                file_size = len(file_content)

            data_stream = BytesIO(file_content)
            object_name = minio_object_name if minio_object_name else original_name

            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=data_stream,
                length=file_size,
                content_type=self._get_content_type(original_name)
            )

            logger.info(f"文件上传成功: {self.bucket_name}/{object_name}")
            return object_name
        except (S3Error, InvalidResponseError) as e:
            logger.error(f"MinIO上传失败: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"文件处理错误: {str(e)}")
            raise

    def upload_file_for_bucket(self, file_object, original_name: str,
                               bucket_name: str,
                               minio_object_name: Optional[str] = None) -> Optional[str]:
        """
        上传文件到指定桶
        :param file_object: 文件对象（字节流或带read方法的对象）
        :param original_name: 原始文件名
        :param bucket_name: 目标桶名
        :param minio_object_name: MinIO中的存储名称（可选）
        :return: 存储的对象名称
        """
        try:
            if hasattr(file_object, 'read'):
                file_content = file_object.read()
                file_size = len(file_content)
                file_object.seek(0)
            else:
                file_content = file_object
                file_size = len(file_content)

            data_stream = BytesIO(file_content)
            object_name = minio_object_name if minio_object_name else original_name
            self._ensure_custom_bucket(bucket_name)

            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data_stream,
                length=file_size,
                content_type=self._get_content_type(original_name)
            )

            logger.info(f"文件上传成功: {bucket_name}/{object_name}")
            return object_name
        except (S3Error, InvalidResponseError) as e:
            logger.error(f"MinIO上传失败: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"文件处理错误: {str(e)}")
            raise

    def get_presigned_url(self, object_name: str, expires_in: timedelta) -> str:
        """获取默认桶的预签名访问URL"""
        try:
            return self.client.presigned_get_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                expires=expires_in
            )
        except S3Error as e:
            logger.error(f"生成预签名URL失败: {str(e)}")
            raise e

    def get_presigned_url_for_bucket(self, object_name: str, expires_in: timedelta,
                                     bucket_name: str,
                                     disposition: str = "inline") -> str:
        """
        获取指定桶的预签名访问URL
        :param disposition: "inline"在线预览, "attachment"触发下载
        """
        try:
            return self.client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=expires_in,
                response_headers={
                    "response-content-disposition": disposition,
                }
            )
        except S3Error as e:
            logger.error(f"生成预签名URL失败: {str(e)}")
            raise e

    def get_object(self, object_name: str):
        """获取默认桶的文件流"""
        return self.get_object_bucket(self.bucket_name, object_name)

    def get_object_bucket(self, bucket_name: str, object_name: str):
        """获取指定桶的文件流"""
        try:
            return self.client.get_object(
                bucket_name=bucket_name,
                object_name=object_name
            )
        except S3Error as e:
            logger.error(f"获取文件失败: {str(e)}")
            raise e

    def download_file(self, object_name: str, file_path: str) -> str:
        """从默认桶下载文件到本地路径"""
        try:
            self.client.fget_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                file_path=file_path
            )
            return file_path
        except S3Error as e:
            logger.error(f"MinIO下载失败: {str(e)}")
            raise e

    def download_file_from_bucket(self, bucket_name: str, object_name: str,
                                  file_path: str) -> str:
        """从指定桶下载文件到本地路径"""
        try:
            self.client.fget_object(
                bucket_name=bucket_name,
                object_name=object_name,
                file_path=file_path
            )
            return file_path
        except S3Error as e:
            logger.error(f"MinIO下载失败: {str(e)}")
            raise e


# 桶名常量（与.env配置一致）
#
# 测试隔离：这些桶名此前是硬编码的，导致 pytest 里用 SQLite 内存库、
# 自增 id 从 1 开始的用例，仍把上传文件写进**运行中的真实桶**，
# 每次跑测试都会在生产 MinIO 里留下一批无人引用的孤儿对象
# （实测 resumes / imports / knowledge-docs 三个桶各积压若干）。
# 与 Milvus 集合名同理，测试统一加 -test 后缀，会话结束时由 conftest 删除。
# 注意：S3/MinIO 的桶名规则不允许下划线（会报 InvalidBucketName），
# 所以这里必须用连字符而不是 _test。
_TESTING = os.getenv("TESTING", "").lower() in ("true", "1", "yes")
_SUFFIX = "-test" if _TESTING else ""

BUCKET_RESUMES = "resumes" + _SUFFIX            # 简历文件
BUCKET_KNOWLEDGE = "knowledge-docs" + _SUFFIX   # 知识文档
BUCKET_IMPORTS = "imports" + _SUFFIX            # 数据导入文件
