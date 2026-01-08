import os
import json

def get_lcp(str_list):
    """计算一组字符串的最长公共前缀"""
    if not str_list:
        return ""
    
    # 取最短的字符串作为基准
    s1 = min(str_list)
    s2 = max(str_list)
    
    for i, char in enumerate(s1):
        if char != s2[i]:
            return s1[:i]
    return s1

def process_product_data(file_list):
    # 1. 第一步：按文件夹和文件名前缀分组
    groups = {}  # key: (dir_path, product_id), value: [file_paths]
    for f in file_list:
        # f 现在是完整路径
        file_name = os.path.basename(f)
        if not file_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
        product_id = file_name[:6]  # 提取 SXXXXX 作为分组键
        dir_path = os.path.dirname(f)  # 获取文件所在目录
        
        # 使用 (目录路径, product_id) 作为分组键，确保不同文件夹的文件分开处理
        group_key = (dir_path, product_id)
        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(f)  # 保存完整路径
    
    results = {}
    
    # 2. 第二步：计算每组的 LCP 并生成 JSON 名
    for (dir_path, pid), files in groups.items():
        # 提取文件名列表（去除扩展名）用于计算lcp
        file_names_without_ext = []
        for f in files:
            file_name = os.path.basename(f)
            # 去除扩展名
            file_name_without_ext = os.path.splitext(file_name)[0]
            file_names_without_ext.append(file_name_without_ext)
        
        # 获取该组图片的最长公共前缀（基于去除扩展名后的文件名）
        lcp = get_lcp(file_names_without_ext)
        
        # 3. 优化命名：去除末尾可能残余的特殊符号（如 _ 或 -）
        json_base_name = lcp.rstrip('_-. ')
        
        # 确保不会为空
        if not json_base_name:
            # 如果为空，使用第一个文件名的前缀部分
            json_base_name = file_names_without_ext[0].rsplit('_', 1)[0] if '_' in file_names_without_ext[0] else file_names_without_ext[0]
        
        json_filename = f"{json_base_name}.json"
        results[json_filename] = files  # 保存完整路径列表
    
    return results

def assign_json(input_dir):
    """分配JSON文件，返回文件路径到JSON文件名的映射"""
    from pathlib import Path

    file_paths = []
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')

    for root,dirs,files in os.walk(input_dir):
        for file in files:
            if file.lower().endswith(image_extensions):
                # 统一路径格式为 linux风格
                file_path = str(Path(os.path.join(root, file)).absolute().as_posix())
                file_paths.append(file_path)
                
    output = process_product_data(file_paths)
    
    # 创建文件路径到JSON文件名的映射
    file_to_json = {}
    for json_name, img_paths in output.items():
        for img_path in img_paths:
            file_to_json[img_path] = json_name
    return file_to_json
    
if __name__ == "__main__":
    # 测试数据
    json_files = assign_json('test', 'outputJson')
    print(json_files)