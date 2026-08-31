Feature: 复制粘贴多边形
  作为标注用户
  我希望 Ctrl+C / Ctrl+V 按选中状态与图像边界正确工作

  Scenario: 选中形状时复制多边形而不是图片
    Given 画布上有选中的多边形
    When 用户按下 Ctrl+C
    Then 复制目标是多边形

  Scenario: 未选中形状时复制图片
    Given 画布上没有选中的多边形
    When 用户按下 Ctrl+C
    Then 复制目标是图片

  Scenario: 同一张图粘贴向右下偏移
    Given 剪贴板中有来自当前图像的多边形
    And 复制多边形跟随鼠标已关闭
    When 用户在同一张图按下 Ctrl+V
    Then 多边形向右下偏移 5 像素
    And 多边形仍在图像内

  Scenario: 其他图像按原坐标粘贴
    Given 剪贴板中有来自其他图像的多边形
    And 复制多边形跟随鼠标已关闭
    When 用户在当前图按下 Ctrl+V
    Then 多边形保持原坐标

  Scenario: 粘贴超出边界时裁切
    Given 剪贴板中有超出当前图像的多边形
    And 复制多边形跟随鼠标已关闭
    When 用户按下 Ctrl+V
    Then 多边形被裁切到图像边界内

  Scenario: 完全在图像外的多边形被丢弃
    Given 剪贴板中有完全位于图像外的多边形
    And 复制多边形跟随鼠标已关闭
    When 用户按下 Ctrl+V
    Then 没有形状被粘贴

  Scenario: 开启跟随鼠标时左上角对齐光标
    Given 剪贴板中有多边形
    And 复制多边形跟随鼠标已开启
    And 鼠标位于图像坐标 50,60
    When 用户按下 Ctrl+V
    Then 多边形左上角对齐鼠标
