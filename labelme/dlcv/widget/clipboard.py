from labelme.logger import logger
def copy_files_to_clipboard(file_paths):
    """
    将多个文件复制到剪贴板
    
    Args:
        file_paths (list): 文件路径列表
    """
    import ctypes
    import os
    from ctypes import wintypes

    if not file_paths:
        raise ValueError("文件路径列表不能为空")

    # 确保所有路径都存在且格式正确
    formatted_paths = []
    for path in file_paths:
        abs_path = os.path.abspath(path).replace("/", "\\")
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"文件不存在: {abs_path}")
        formatted_paths.append(abs_path)

    CF_HDROP = 15
    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040
    GHND = GMEM_MOVEABLE | GMEM_ZEROINIT

    class DROPFILES(ctypes.Structure):
        _pack_ = 1
        _fields_ = [
            ("pFiles", wintypes.DWORD),
            ("pt", wintypes.POINT),
            ("fNC", wintypes.BOOL),
            ("fWide", wintypes.BOOL),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

    dropfiles = DROPFILES()
    dropfiles.pFiles = ctypes.sizeof(DROPFILES)
    dropfiles.pt.x = 0
    dropfiles.pt.y = 0
    dropfiles.fNC = False
    dropfiles.fWide = True

    # 将所有路径合并成一个字节串，每个路径用null分隔
    paths_bytes = b""
    for path in formatted_paths:
        paths_bytes += path.encode("utf-16le") + b"\x00\x00"
    # 添加最后的双null终止符
    paths_bytes += b"\x00\x00"

    total_size = ctypes.sizeof(DROPFILES) + len(paths_bytes)
    h_global = kernel32.GlobalAlloc(GHND, total_size)
    if not h_global:
        raise MemoryError("全局内存分配失败")

    ptr = kernel32.GlobalLock(h_global)
    if not ptr:
        kernel32.GlobalFree(h_global)
        raise RuntimeError("无法锁定内存")

    try:
        ctypes.memmove(ptr, ctypes.byref(dropfiles), ctypes.sizeof(DROPFILES))
        ctypes.memmove(ptr + ctypes.sizeof(DROPFILES), paths_bytes, len(paths_bytes))
    finally:
        kernel32.GlobalUnlock(h_global)

    if not user32.OpenClipboard(None):
        raise RuntimeError("无法打开剪贴板")
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_HDROP, h_global)
    finally:
        user32.CloseClipboard()

def copy_file_to_clipboard(file_path):
    """
    将单个文件复制到剪贴板（向后兼容）
    
    Args:
        file_path (str): 文件路径
    """
    copy_files_to_clipboard([file_path])


all_temp_files = []


def copy_bytes_to_clipboard(file_bytes, file_name):
    """
    将文件字节数据复制到剪贴板

    Args:
        file_bytes (bytes): 文件的字节数据
        file_name (str): 文件名（包含扩展名）
    """
    import tempfile
    import os

    # 创建临时文件，使用指定的文件名
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, file_name)
    
    # 写入文件内容
    with open(temp_path, 'wb') as temp_file:
        temp_file.write(file_bytes)

    try:
        # 使用现有的copy_file_to_clipboard函数复制临时文件
        copy_file_to_clipboard(temp_path)
    finally:
        all_temp_files.append(temp_path)


def clear_temps():
    """
    清理所有临时文件
    """
    import os

    for temp_file in all_temp_files:
        try:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
        except Exception as e:
            print(f"删除临时文件 {temp_file} 失败: {e}")

    all_temp_files.clear()


def copy_shapes_to_clipboard(shapes_data, source_image_path=None):
    """
    将形状数据复制到剪贴板
    
    Args:
        shapes_data (list): 形状数据列表，每个形状是一个字典
        source_image_path (str): 源图像路径，用于判断是否在同一张图片上粘贴
    """
    import json
    import tempfile
    import os
    
    try:
        # 为每个形状添加源图像路径信息
        shapes_data_with_source = []
        for shape_data in shapes_data:
            shape_with_source = shape_data.copy()
            shape_with_source['source_image_path'] = source_image_path
            shapes_data_with_source.append(shape_with_source)
        
        # 将形状数据序列化为JSON
        json_data = json.dumps(shapes_data_with_source, ensure_ascii=False, indent=2)
        
        # 创建临时文件
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "copied_shapes.json")
        
        # 写入JSON数据
        with open(temp_path, 'w', encoding='utf-8') as temp_file:
            temp_file.write(json_data)
        
        try:
            # 使用现有的copy_file_to_clipboard函数复制临时文件
            copy_file_to_clipboard(temp_path)
        finally:
            all_temp_files.append(temp_path)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise


def paste_shapes_from_clipboard():
    """
    从剪贴板读取形状数据
    
    Returns:
        list: 形状数据列表，如果失败返回None
    """
    import json
    import tempfile
    import os
    
    try:
        # 检查临时文件是否存在
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "copied_shapes.json")
        
        if not os.path.exists(temp_path):
            return None
            
        # 读取JSON数据
        with open(temp_path, 'r', encoding='utf-8') as temp_file:
            content = temp_file.read()
            shapes_data = json.loads(content)
            
        return shapes_data
        
    except Exception as e:
        logger.info(f"=== DEBUG: 从剪贴板读取形状数据失败: {e} ===")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # 测试单文件复制
    # file_path = r"C:\dlcv\datasets\dogs_vs_cats\狗\dog.0.jpg"
    # copy_file_to_clipboard(file_path)

    # 测试多文件复制
    file_paths = [
        r"C:\dlcv\datasets\dogs_vs_cats\狗\dog.0.jpg",
        r"C:\dlcv\datasets\dogs_vs_cats\狗\dog.1.jpg",
        r"C:\dlcv\datasets\dogs_vs_cats\狗\dog.2.jpg"
    ]
    copy_files_to_clipboard(file_paths)

    # 测试文件字节复制
    # with open(file_path, "rb") as f:
    #     file_bytes = f.read()
    # copy_bytes_to_clipboard(file_bytes, "test.jpg")
