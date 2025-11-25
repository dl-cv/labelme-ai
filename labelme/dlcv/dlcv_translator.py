class DlcvTrObject:
    # 2025年11月25日 已弃用，直接使用 dlcv_tr(text) 即可

    # 兼容成类似 qt 的 tr 函数
    @staticmethod
    def tr(text):
        from labelme.dlcv import dlcv_tr
        return dlcv_tr(text)


class DlcvTranslator:

    def __call__(self, *args, **kwargs):
        text = args[0]
        return tr_map.get(self.lang, {}).get(text, text)

    def set_lang(self, lang):
        self.lang = lang

    def get_lang(self):
        return self.lang

    def __init__(self):
        import locale
        local_lang = locale.getdefaultlocale()[0]
        # 如果系统语言不在支持的语言列表中，则默认为英文
        self.lang =  'en_US'


tr_map = {
    'en_US': {
        # ======菜单栏======
        'ai processing...': 'ai processing...',
        'ai process done': 'ai process done',
        '使用文档': 'Documentation',
        '复制图片': 'Copy Image',
        '开发者模式': 'Developer Mode',
        '开发者密码': 'Developer Password',
        '确定': 'Confirm',
        '加载标签文件': 'Load Label File',
        '保存标签文件': 'Save Label File',
        '刷新(F5)': 'Refresh (F5)',
        '刷新文件夹': 'Refresh Folder',
        '创建旋转框': 'Create Rotated Box',
        '开始绘制旋转框 (R)': 'Start Drawing Rotated Box (R)',
        '查看属性': 'View Attributes',
        '系统设置': 'System Settings',
        '语言(Language)': '语言(Language)',
        '简体中文': 'Simplified Chinese',
        '英文': 'English',
        '字体大小': 'Font Size',
        '已切换为 English': 'Switched to English',
        '已切换为 简体中文': 'Switched to Simplified Chinese',
        '语言设置': 'Language',
        '已设置为 {point_size}': 'Set to {point_size}',

        # ======工具栏======
        '标签文件为空': 'Label file is empty',
        '该标签文件没有任何标签。':
            'This label file does not contain any labels.',
        '标签加载完成': 'Labels loaded',
        '成功加载 {count} 个新标签。':
            'Successfully loaded {count} new labels.',
        '未发现新标签，所有标签已存在。':
            'No new labels found; all labels already exist.',
        '加载标签文件失败': 'Failed to load label file',
        '提示': 'Notice',
        '请先选中一张图片。': 'Please select an image first.',
        '复制成功': 'Copy successful',
        '图片已复制到剪贴板，可直接粘贴为文件。':
            'Image copied to clipboard; paste it directly as a file.',
        '复制失败': 'Copy failed',
        '请先选中要复制的形状': 'Please select shapes to copy first.',
        '已复制 {count} 个形状到剪贴板':
            'Copied {count} shapes to the clipboard.',
        '粘贴的形状超出当前图像边界，已自动调整':
            'Pasted shapes exceeded the current image boundary and were adjusted automatically.',
        '粘贴成功': 'Paste successful',
        '已粘贴 {count} 个形状': 'Pasted {count} shapes.',
        '剪贴板中没有可粘贴的内容':
            'The clipboard does not contain any content to paste.',
        '粘贴失败': 'Paste failed',
        '无法打开图片，请检查文件是否已损坏':
            'Unable to open image. Please check whether the file is corrupted.',
        'Json 文件数据错误！': 'JSON file data error!',
        '当前 Json 文件中的 imagePath 与图片路径不一致，请检查！':
            'imagePath inside the current JSON does not match the image path. Please check!',
        '显示RGB值失败!': 'Failed to display RGB values!',
        '功能互斥': 'Conflicting features',
        '已禁用画笔标注功能': 'Brush annotation has been disabled.',
        '画笔功能提示': 'Brush feature notice',
        '画笔标注功能仅在多边形标注模式下可用，将在下次进入多边形模式时自动启用':
            'Brush annotation is only available in polygon mode and will be enabled the next time you enter it.',
        '已禁用滑动标注功能': 'Slide annotation has been disabled.',
        '预测失败': 'Prediction failed',
        '请检查模型文件是否正确': 'Please check whether the model files are correct.',
        '预测完成, 开始自动标注': 'Prediction completed, starting auto labeling.',
        '请稍等...': 'Please wait...',
        '自动标注完成': 'Auto labeling completed',
        '请检查标注结果': 'Please review the labeling result.',
        '自动标注失败': 'Auto labeling failed',
        '请先进行一次标注': 'Please complete at least one annotation first.',
        '请先进行一次标注后再切换编辑模式':
            'Please finish an annotation before switching to edit mode.',
        '3D 视图提示': '3D View Notice',
        '当前图片不是3D数据，无法显示3D视图':
            'The current image is not 3D data, so the 3D view cannot be displayed.',
        '存在不合法多边形': 'Invalid polygons detected',
        '存在不合法多边形,是否切换图片?':
            'Invalid polygons detected. Do you want to switch image?',
        '获取标签文件失败': 'Failed to obtain label file',
        '代码不应该运行到这里': 'Code should not reach here.',
        '文件大小为0': 'File size is 0',
        '选择要加载的标签txt文件': 'Choose a label txt file to load',
        '标签文件 (*.txt)': 'Label files (*.txt)',
        '保存标签文件': 'Save label file',
        '标签/文本标记数量统计': 'Label/Text Flag Statistics',
        '统计当前文件夹标签/文本标记总数':
            'Count labels/text flags in the current folder',
        '未检测到有效的图片文件夹，请先导入文件夹。':
            'No valid image folder detected. Please import a folder first.',
        '未找到任何JSON文件，请先进行标注。':
            'No JSON files were found. Please annotate first.',
        '找到 {count} 个JSON文件，但未统计到任何标签。':
            'Found {count} JSON files but no labels were counted.',
        '统计结果（共扫描 {count} 个JSON文件）：\n':
            'Statistics (scanned {count} JSON files):\n',
        '\n文本标记统计:\n': '\nText flag statistics:\n',
        '文本标记总数: {count}\n': 'Total text flags: {count}\n',
        '\n标签统计:\n': '\nLabel statistics:\n',
        '标签总数: {count}': 'Total labels: {count}',
        '\n\n总数: {count}': '\n\nTotal: {count}',
        '当前文件统计结果：\n': 'Current file statistics:\n',
        '\n总数: {count}': '\nTotal: {count}',
        '\n当前文件暂无标注数据': '\nNo annotation data in the current file.',
    },

    'zh_CN': {
        'ai processing...': 'ai分析中...',
        'ai process done': 'ai分析完成',
        'setting dock': '设置面板',

        # 其他设置
        'display shape label': '显示标签名称',
        'shape label font size': '标签字体大小',
        'convert img to gray': '将标注图片转换为灰度图',
        'keep prev scale': '图片缩放',
        'points to crosshair': '将点转换为十字线',

        'change color': '更改颜色',
        'change the color of the selected polygon': '更改选中形状的标注颜色',

        'label setting': '标注设置',
        'auto setting': '自动标注设置',
        'other setting': '其他设置',
        'slide label': '滑动标注多边形',
        'slide distance': '滑动标注距离',
        'brush enabled': '启用画笔标注（按+/-调整大小）',
        'fill closed region': '填充闭合区域',
        'brush size': '画笔大小',
        'Flags': '文本标记',
        'Add Text Flag': '添加文本标记',
        'Please enter the text flag': '请输入文本标记',
        'open next image': '下一幅',
        'open previous image': '上一幅',
        'highlight start point': '高亮起始点',
        'ai polygon simplify epsilon': 'AI多边形简化参数设置',

        'copy images': '复制图片',

        # 项目类型
        'project setting': '项目设置',
        'project type': '项目类型',
        'normal': '常规',
        '3D': '3D',

        # 系统设置
        'System Setting': '系统设置',
        'Language': '语言',
        'Font Size': '字体大小',
    },
}

dlcv_tr = DlcvTranslator()
