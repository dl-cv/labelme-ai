class DlcvTrObject:
    # 2025年11月25日 已弃用，直接使用 dlcv_tr(text) 即可

    # 兼容成类似 qt 的 tr 函数
    @staticmethod
    def tr(text):
        from labelme.dlcv import dlcv_tr
        return dlcv_tr(text)


class DlcvTranslator:
    lang = None

    def __call__(self, *args, **kwargs):
        if self.lang is None:
            self.__lazy_init()
            print(f'@@@当前语言设置为: {self.lang}')
        text = args[0]
        return tr_map.get(self.lang, {}).get(text, text)

    def set_lang(self, lang):
        self.lang = lang

    def get_lang(self):
        return self.lang

    def __lazy_init(self):
        """初始化语言设置，优先级：用户设置 > 系统语言 > 默认英文"""
        from labelme.dlcv.store import STORE
        from PyQt5 import QtCore

        supported_langs = tr_map.keys()
        self.lang = "en_US"

        # 优先使用用户设置的语言
        try:
            saved_lang = STORE.main_window.settings.value(
                "ui/language", type=str)
            if saved_lang in supported_langs:
                self.lang = saved_lang
        except (AttributeError, RuntimeError):
            # 其次使用系统语言
            try:
                system_lang = QtCore.QLocale.system().name()
                lang_code = system_lang.split('.')[0].replace('-', '_')
                if lang_code in supported_langs:
                    self.lang = lang_code
                elif lang_code.startswith('zh'):
                    self.lang = "zh_CN"
            except Exception:
                pass

        # 加载翻译数据
        if STORE.q_translator and self.lang == "zh_CN":
            from labelme.translate.zh_CN import translate_data
            STORE.q_translator.loadFromData(translate_data)


tr_map = {
    'en_US': {
        # ======菜单栏======
        'ai processing...':
        'ai processing...',
        'ai process done':
        'ai process done',
        '使用文档':
        'Documentation',
        '复制图片':
        'Copy Image',
        '开发者模式':
        'Developer Mode',
        '开发者密码':
        'Developer Password',
        '确定':
        'Confirm',
        '加载标签文件':
        'Load Label File',
        '保存标签文件':
        'Save Label File',
        '刷新(F5)':
        'Refresh (F5)',
        '刷新文件夹':
        'Refresh Folder',
        '创建旋转框':
        'Create Rotated Box',
        '开始绘制旋转框 (R)':
        'Start Drawing Rotated Box (R)',
        '查看属性':
        'View Attributes',
        '系统设置':
        'System Settings',
        '语言(Language)':
        '语言(Language)',
        '简体中文':
        'Simplified Chinese',
        '英文':
        'English',
        '字体大小':
        'Font Size',
        '已切换为 English':
        'Switched to English',
        '已切换为 简体中文':
        'Switched to Simplified Chinese',
        '已设置为':
        'Set to',
        '重置所有视图位置':
        'Reset all view positions',
        '重启软件':
        'Restart software',
        '是否重启软件以应用修改？':
        'Would you like to restart the software to apply the changes?',

        # ======工具栏======
        '标签文件为空':
        'Label file is empty',
        '该标签文件没有任何标签。':
        'This label file does not contain any labels.',
        '标签加载完成':
        'Labels loaded',
        '成功加载 {count} 个新标签。':
        'Successfully loaded {count} new labels.',
        '未发现新标签，所有标签已存在。':
        'No new labels found; all labels already exist.',
        '加载标签文件失败':
        'Failed to load label file',
        '存在不合法多边形':
        'Invalid polygons detected',
        '存在不合法多边形,是否切换图片?':
        'Invalid polygons detected. Do you want to switch image?',
        '获取标签文件失败':
        'Failed to obtain label file',
        '代码不应该运行到这里':
        'Code should not reach here.',
        '文件大小为0':
        'File size is 0',
        '选择要加载的标签txt文件':
        'Choose a label txt file to load',
        '标签文件 (*.txt)':
        'Label files (*.txt)',
        '保存标签文件':
        'Save label file',

        # ===AI widget 自动标注模块===
        '加载模型':
        'Load model',
        '标注所有':
        'Label all',
        '选择模型文件':
        'Select model file',
        '加载模型失败':
        'Load model failed',
        '加载模型出错(unknow error) 请检查是否开启了代理软件':
        'Load model error (unknown error). Please check whether the proxy software is enabled.',
        '预测失败':
        'Prediction failed',
        '未获取到预测结果':
        'No prediction result',
        '自动标注提示':
        'Auto labeling prompt',
        '是否覆盖原始标注?':
        'Whether to overwrite the original annotation?',
        '自动标注完成':
        'Auto labeling completed',
        '自动标注失败':
        'Auto labeling failed',
        '请检查标注结果':
        'Please review the labeling result.',
        '请检查模型文件是否正确':
        'Please check whether the model files are correct.',
        '预测完成, 开始自动标注':
        'Prediction completed, starting auto labeling.',
        '请稍等...':
        'Please wait...',

        # ======文件树======
        "展开所有子文件夹":
        "Expand all subfolders",
        "输入关键字过滤 - Enter键搜索":
        "Input keywords to filter - Enter to search",
        "Enter键搜索":
        "Enter to search",
        "复制文件到剪贴板成功":
        "Copy file to clipboard successfully",
        "已将文件复制到剪贴板":
        "The file has been copied to the clipboard",
        "打开文件":
        "Open file",
        "打开所在目录":
        "Open directory",
        "复制文件名":
        "Copy file name",
        "复制路径":
        "Copy path",
        "复制文件到剪贴板":
        "Copy file to clipboard",
        "未找到 {text} 文件路径":
        "File path not found: {text}",
        "代码不应该运行到这里":
        "Code should not reach here.",

        # ======画布======
        '提示':
        'Notice',
        '请先选中一张图片。':
        'Please select an image first.',
        '复制成功':
        'Copy successful',
        '图片已复制到剪贴板，可直接粘贴为文件。':
        'Image copied to clipboard; paste it directly as a file.',
        '复制失败':
        'Copy failed',
        '请先选中要复制的形状':
        'Please select shapes to copy first.',
        '已复制 {count} 个形状到剪贴板':
        'Copied {count} shapes to the clipboard.',
        '粘贴的形状超出当前图像边界，已自动调整':
        'Pasted shapes exceeded the current image boundary and were adjusted automatically.',
        '粘贴成功':
        'Paste successful',
        '已粘贴 {count} 个形状':
        'Pasted {count} shapes.',
        '剪贴板中没有可粘贴的内容':
        'The clipboard does not contain any content to paste.',
        '粘贴失败':
        'Paste failed',
        '无法打开图片，请检查文件是否已损坏':
        'Unable to open image. Please check whether the file is corrupted.',
        'Json 文件数据错误！':
        'JSON file data error!',
        '当前 Json 文件中的 imagePath 与图片路径不一致，请检查！':
        'imagePath inside the current JSON does not match the image path. Please check!',
        '显示RGB值失败!':
        'Failed to display RGB values!',
        '请先进行一次标注':
        'Please complete at least one annotation first.',
        '请先进行一次标注后再切换编辑模式':
        'Please finish an annotation before switching to edit mode.',
        '3D 视图提示':
        '3D View Notice',
        '当前图片不是3D数据，无法显示3D视图':
        'The current image is not 3D data, so the 3D view cannot be displayed.',
        '创建文本标记':
        'Create text flag',

        # ======right_widget 右侧dock模块======
        # ===flags 文本标记===
        '删除':
        'Delete',

        # ===标签列表===
        '删除标签':
        'Delete label',
        '是否确定要删除选中的 {count} 个标签？\n注意：这只会从标签列表中删除，不会影响已经标注的形状。':
        'Are you sure you want to delete the selected {count} labels? \nNote: This will only remove them from the label list and will not affect the already annotated shapes.',
        '确认删除':
        'Confirm deletion',

        # ===多边形标签===
        '选择颜色':
        'Select color',

        # ===label_count 标签/文本标记数量统计===
        '标签/文本标记数量统计':
        'Label/Text Flag Statistics',
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
        '\n文本标记统计:\n':
        '\nText flag statistics:\n',
        '文本标记总数: {count}\n':
        'Total text flags: {count}\n',
        '\n标签统计:\n':
        '\nLabel statistics:\n',
        '标签总数: {count}':
        'Total labels: {count}',
        '\n\n总数: {count}':
        '\n\nTotal: {count}',
        '当前文件统计结果：\n':
        'Current file statistics:\n',
        '\n总数: {count}':
        '\nTotal: {count}',
        '\n当前文件暂无标注数据':
        '\nNo annotation data in the current file.',

        # ===设置面板===
        '功能互斥':
        'Conflicting features',
        '已禁用画笔标注功能':
        'Brush annotation has been disabled.',
        '画笔功能提示':
        'Brush feature notice',
        '画笔标注功能仅在多边形标注模式下可用，将在下次进入多边形模式时自动启用':
        'Brush annotation is only available in polygon mode and will be enabled the next time you enter it.',
        '已禁用滑动标注功能':
        'Slide annotation has been disabled.',
        '显示标签名称':
        'Display shape label',
        '标签字体大小':
        'Shape label font size',
        '将标注图片转换为灰度图':
        'Convert annotated image to grayscale',
        '图片缩放':
        'Image scaling',
        '将点转换为十字线':
        'Convert points to crosshair',
        '更改颜色':
        'Change color',
        '更改选中形状的标注颜色':
        'Change the color of the selected polygon',
        '启用画笔标注（按+/-调整大小）':
        'Enable brush annotation (adjust size with +/-)',
        '填充闭合区域':
        'Fill closed region',
        "常规":
        "Normal",
        "保持上次缩放比例":
        "Keep previous scale",
        "3D":
        "3D",
        "自动缩放":
        "Auto scale",
        "保持缩放比例":
        "Keep scale",
        "蓝色线段标注":
        "Blue line annotation",
        "显示旋转框箭头与角度":
        "Display rotation box arrow and angle",
        "启用滑动标注将禁用画笔标注功能，两者互斥":
        "Enabling slide annotation will disable brush annotation and they are mutually exclusive",
        "滑动标注距离":
        "Slide annotation distance",
        "启用后，将高亮标注线段为蓝色":
        "Enabled, the highlighted annotation line will be blue",
        "启用后，闭合区域内部将被填充，否则仅保留轮廓":
        "Enabled, the closed region will be filled, otherwise only the outline will be retained",
        "画笔大小":
        "Brush size",
        "启用后，将点转换为十字线":
        "Enabled, the points will be converted to crosshair",
        "启用后，将点转换为十字线":
        "Enabled, the points will be converted to crosshair",
        'AI多边形点数简化设置':
        'AI polygon simplify epsilon setting',
        '简化程度说明':
        'Simplification degree description',
        '0.001: 轻微简化':
        '0.001: Mild simplification',
        '0.005: 默认简化':
        '0.005: Default simplification',
        '0.01: 较多简化':
        '0.01: Significant simplification',
        '0.05: 大量简化':
        '0.05: Substantial simplification',
        '0.1: 极度简化':
        '0.1: Extreme simplification',
        '使用Bbox进行自动标注':
        'Use Bbox for auto annotation',
        '请输入需要自动标注的类别':
        'Please enter the categories to be automatically annotated',
        # ======其他处理======
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
