"""处理失败后清理已创建文件的辅助函数。"""

from pathlib import Path

def cleanup_file(path:Path)-> bool:
    """尽力删除文件；文件已经不存在时返回 False。"""
    try :
        path.unlink(missing_ok=True)
        return True
    except FileNotFoundError:
        return False
