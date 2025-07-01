def copy_file_to_clipboard(file_path):
    import ctypes
    import os
    from ctypes import wintypes

    file_path = os.path.abspath(file_path).replace("/", "\\")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    CF_HDROP = 15
    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040
    GHND = GMEM_MOVEABLE | GMEM_ZEROINIT

    # 强制结构体按1字节对齐，避免编译器填充
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

    # 配置API参数类型
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
    dropfiles.fWide = True  # 使用Unicode

    # 关键修正：路径后添加双空字符（4字节）
    path_bytes = file_path.encode("utf-16le")
    data = path_bytes + b"\x00\x00\x00\x00"  # 两个UTF-16空字符

    total_size = ctypes.sizeof(DROPFILES) + len(data)
    h_global = kernel32.GlobalAlloc(GHND, total_size)
    if not h_global:
        raise MemoryError("全局内存分配失败")

    ptr = kernel32.GlobalLock(h_global)
    if not ptr:
        kernel32.GlobalFree(h_global)
        raise RuntimeError("无法锁定内存")

    try:
        ctypes.memmove(ptr, ctypes.byref(dropfiles), ctypes.sizeof(DROPFILES))
        ctypes.memmove(ptr + ctypes.sizeof(DROPFILES), data, len(data))
    finally:
        kernel32.GlobalUnlock(h_global)

    if not user32.OpenClipboard(None):
        raise RuntimeError("无法打开剪贴板")
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_HDROP, h_global)
    finally:
        user32.CloseClipboard()


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


if __name__ == "__main__":
    # 测试文件路径复制
    file_path = r"C:\dlcv\datasets\dogs_vs_cats\狗\dog.0.jpg"
    copy_file_to_clipboard(file_path)

    # 测试文件字节复制
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    copy_bytes_to_clipboard(file_bytes, "test.jpg")
