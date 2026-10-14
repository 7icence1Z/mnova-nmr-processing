# 默认显示设置：主谱与 Expansion 均应用

默认白色背景，无水平/垂直背景网格，无紫色多重峰标记，无紫色多重峰积分曲线或数值，无纵坐标轴、刻度、数字及轴标题。保留 ppm 横坐标、蓝色 Peak Picking、普通绿色积分曲线及其轴下蓝色数值。Expansion 可保留细边框；边框不等于背景网格。

隐藏多重峰叠加层不删除 `Multiplet` 对象、不取消分析、不删 J 或报告中的化学归属。普通 `integrals.*` 和多重峰自带的 `multiplets.integral.*` 是两套显示层，不能为隐藏紫色积分而关掉全部积分。

## 脚本设置

优先将 `scripts/display_style.qs` 内容纳入本次生成的 `.qs`；正常 GUI 路径也可设置相同原生属性，验收标准一致。在人工积分、峰、多重峰、Expansion 和模板创建完成后，对主谱调用 `applyCourseDisplayStyle(spec, false)`，对每个 Expansion 调用 `applyCourseDisplayStyle(expansion, true)`；此函数不是全谱分析入口，不会自行修改用户全局偏好。

关键属性可在当前 Mnova 的属性帮助和 `nmrPropertiesTest.qs` 等随附示例中核对：

| 显示项目 | 设置 |
| --- | --- |
| 背景网格 | `grid.showhorizontal = false`、`grid.showvertical = false` |
| 纵坐标 | `axes.vertical.visible = false`、`axes.vertical.showlabel = false` |
| 紫色多重峰标记 | `multiplets.show = false` |
| 多重峰积分 | `multiplets.integral.curve.show = false`、`multiplets.integral.label.show = false`、`multiplets.integral.methodlabel.show = false` |
| 普通积分 | `integrals.show = true`、`integrals.curve.show = true`、`integrals.label.show = true`、`integrals.label.position = "Segment"` |
| 峰拾取 | `peaks.show = true`；样品峰用蓝色，溶剂/内标可单独保留区别颜色 |

不是只写说明或依赖导入文件默认值：需在本次文档对象上显式设置。新版本属性需读回核对；不支持时查看该版本帮助/GUI 的对应显示项，不能静默忽略。

部分版本可能将 `grid.showframe` 读回为字符串 `"true"`/`"false"`，辅助脚本对此做布尔兼容。属性读回不替代实际成品的整页视觉检查。

## 保存后的验收

重新打开 `.mnova`，逐个枚举主谱与 Expansion，读回网格、纵轴、multiplet 显示及两类积分属性；原生积分、多重峰对象数和化学结果应保留。再渲染整页，确认四项关闭设置在所有谱图均生效、只有一套普通积分数值，且报告中的 δ、可靠 J、氢数或相对积分仍存在。

隐藏纵轴不取消纵向缩放；继续调整峰高和基线以下留白。确认无紫色叠加后再按 [layout-guide.md](layout-guide.md) 检查绿色积分与峰标间距、ppm 刻度和标签位置。GUI 回退路径同样执行这些设置和验收。
