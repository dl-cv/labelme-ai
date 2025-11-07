class DlcvTrObject:

    # 兼容成类似 qt 的 tr 函数
    @staticmethod
    def tr(text):
        from labelme.dlcv import tr
        return tr(text)


class DlcvTranslator:

    def __call__(self, *args, **kwargs):
        text = args[0]
        return tr_map.get(self.lang, {}).get(text, text)

    def set_lang(self, lang):
        self.lang = lang

    def get_lang(self):
        return self.lang

    def __init__(self):
        # 获取系统语言
        import locale
        local_lang = locale.getdefaultlocale()[0]
        # 如果系统语言不在支持的语言列表中，则默认为英文
        self.lang = local_lang if local_lang in tr_map else 'en_US'


tr_map = {
    'en_US': {
        'ai processing...': 'ai processing...',
        'ai process done': 'ai process done',
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
    },
}

tr = DlcvTranslator()
