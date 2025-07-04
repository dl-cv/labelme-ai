# 简介
深度视觉LabelmeAI是一款基于LabelMe开源版进行深度重开发的更加智能的标注工具。 如名所示，这个工具与开源吧=版最大的不同在于他的AI自动标注功能， 这让你能够快速构建你的数据集。

# ✌️我们做了什么
* json 文件保存差异：开源版 labelme 不能自动保存 json 文件，需手动点击保存，且文件大小大于 100KB 。而深度视觉 LabelmeAI 可自动保存 json 文件，其文件大小仅在 5KB - 15KB 。例如在大量标注任务中，手动保存 json 文件会耗费时间，且较大文件占用更多存储空间，深度视觉 LabelmeAI 自动保存及较小文件大小则更具优势。
* 图像显示与切换：深度视觉 LabelmeAI 的图片可显示标签名称、RGB，且加载、切换 4K 大图速度快，切换图像不卡顿。开源版 Labelme 切换图像速度慢且卡顿明显。在处理高清图像时，深度视觉 LabelmeAI 能流畅操作，为标注人员提供更好体验，如在标注 4K 分辨率的医学影像时，卡顿的开源版 labelme 会影响标注效率。
* 标注功能对比：深度视觉 LabelmeAI 增加了画笔功能，并可调节滑动标注距离，而开源版 labelme 无此画笔功能，只能一直点击鼠标左键创建多边形点完成标注。例如在标注不规则图形时，深度视觉 LabelmeAI 的画笔功能可更灵活绘制，提高标注效率。
* 标签修改便捷性：深度视觉 LabelmeAI 双击标签就能修改标签名称，开源版 labelme 则需选中标签后在多边形标签栏进行修改。深度视觉 LabelmeAI 这种更简易的修改方式，在需要快速修改大量标签时，能节省不少时间。
* 其他特色功能：深度视觉 LabelmeAI 可实现图片像素级显示，可右键打开文件夹，还新增创建圆形、直线、控制点、AI 多边形等标注快捷键，并且支持将原图转换成灰度图以消除颜色干扰、降低眼睛疲劳。开源版 labelme 不具备这些功能。像右键打开文件夹这一便捷操作，在频繁查找文件时能减少操作步骤，提高工作效率。

# 具体来说
**1、深度视觉LabelmeAI自动保存json文件** \
Labelme**无法自动保存json文件**，需手动点击保存，文件大小通常 >100KB；\
深度视觉LabelmeAI可**自动化保存json文件**，**文件大小在5KB-15KB**；

**开源版labelme保存标注过程如下所示：**
![img.png](LabelmeImages/img.png)
![img_1.png](LabelmeImages/img_1.png)
**生成的json文件对比：** \
![img_2.png](LabelmeImages/img_2.png)

**2、深度视觉LabelmeAI 图片可显示标签名称、RGB**
![img_3.png](LabelmeImages/img_3.png)
**3、深度视觉LabelmeAI加载、切换>4k大图速度较快
深度视觉LabelmeAI切换图像，速度快、不卡顿**
![img_4.png](LabelmeImages/3_1图像切换.gif)
**开源版Labelme切换图像，速度较慢、卡顿明显：**
![img_5.png](LabelmeImages/3_2图像切换.gif)
**4、深度视觉LabelmeAI增加画笔功能** \
深度视觉LabelmeAI**增加画笔功能**，还可**调节滑动标注距离**。开源版labelme无此画笔功能，需要一直点击鼠标左键创建多边形点完成标注。\
![img_6.png](LabelmeImages/4画笔.gif)
**5、深度视觉LabelmeAI更简易修改标签**\
深度视觉LabelmeAI,**双击标签，可修改标签名称**。
![img_7.png](LabelmeImages/5_1修改标签.gif)
开源版labelme只能选中标签后，在多边形标签栏进行修改。
![img_8.png](LabelmeImages/5_2修改标签.gif)
**6、深度视觉LabelmeAI图片像素级显示**
![img_9.png](LabelmeImages/img_9.png)
**7、深度视觉LabelmeAI可右键打开文件夹**\
深度视觉LabelmeAI可**右键打开文件夹**，更便捷的打开文件方式。
![img_10.png](LabelmeImages/img_10.png)
开源版Labelme只能通过**打开labelme>打开目录>输入文件路径>选择文件夹，才可以打开文件**。\
![img_11.png](LabelmeImages/img_11.png)
**8、深度视觉labelmeAI增加许多创建标注快捷键**\
深度视觉labelmeAI新增创建圆形、直线、控制点、AI多边形快捷键,开源版labelme无这些快捷键。
![img_12.png](LabelmeImages/img_12.png)
**9、深度视觉labelmeAI支持将原图转换成灰度图**\
深度视觉labelmeAI支持将原图转换成灰度图，灰度图消除了颜色的干扰，使得图像的形状和纹理更明显，同时还降低标注人员的眼睛疲劳感。开源版labelme不支持转换。\
![img_13.png](LabelmeImages/img_13.png)
# 📑Acknowledgement
This repo is the fork of [labelme](https://github.com/wkentaro/labelme)