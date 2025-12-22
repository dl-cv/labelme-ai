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
    # 1. 第一步：初步分组
    groups = {}
    for f in file_list:
        if not f.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
        product_id = f[:6]  # 提取 SXXXXX 作为分组键
        if product_id not in groups:
            groups[product_id] = []
        groups[product_id].append(f)

    results = {}

    # 2. 第二步：计算每组的 LCP 并生成 JSON 名
    for pid, files in groups.items():
        # 获取该组图片的最长公共前缀
        lcp = get_lcp(files)
        
        # 3. 优化命名：去除末尾可能残余的特殊符号（如 _ 或 -）
        json_base_name = lcp.rstrip('_-. ')
        
        json_filename = f"{json_base_name}.json"
        results[json_filename] = files

    return results

def assign_json(input_dir):
    """分配JSON文件，返回文件名到JSON文件名的映射"""
    file_names = os.listdir(input_dir)
    output = process_product_data(file_names)
    
    # 创建文件名到JSON文件名的映射
    file_to_json = {}
    for json_name, imgs in output.items():
        for img_name in imgs:
            file_to_json[img_name] = json_name
    
    return file_to_json
    
    

if __name__ == "__main__":
    # 测试数据
    json_files = assign_json('test', 'outputJson')
    print(json_files)