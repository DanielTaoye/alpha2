"""响应数据传输对象"""
from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class ApiResponse:
    """API响应DTO"""
    code: int
    data: Any
    message: str = 'success'
    
    def to_dict(self):
        """转换为字典"""
        return {
            'code': self.code,
            'data': self.data,
            'message': self.message
        }


class ResponseBuilder:
    """响应构建器"""
    
    @staticmethod
    def success(data: Any, message: str = 'success') -> dict:
        """成功响应"""
        return ApiResponse(code=200, data=data, message=message).to_dict()
    
    @staticmethod
    def error(message: str, code: int = 500, data: Any = None) -> dict:
        """错误响应"""
        return ApiResponse(code=code, data=data, message=message).to_dict()

