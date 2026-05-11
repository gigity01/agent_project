校验
校验
"""校验
保证单例
"""
def singleton(cls):
    _instances = {}
    def get_instance(*args, **kwargs) :
        if cls not in _instances:
            _instances[cls] = cls(*args, **kwargs)

        return _instances[cls]
    return get_instance