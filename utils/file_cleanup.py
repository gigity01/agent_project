from pathlib import Path

def cleanup_file(path:Path)-> bool:
    try :
        path.unlink(missing_ok=True)
        return True
    except FileNotFoundError:
        return False