# 参考截图的三维场景版本

本版本依据 `assets/reference/target-scene.png` 重建场景，入口为：

```powershell
& 'D:\xwchen\butter-spread-demo\render-scene.ps1' -Samples 32
```

此入口直接读取已求解的 MPM 状态，不重复进行求解。视频为 `outputs/butter-spread.mp4`，关键帧为 `outputs/frame-000.png`、`frame-036.png`、`frame-072.png`；拼图为 `outputs/verified-keyframes.jpg`。`outputs/scene-v1/` 保留更新前的视频和拼图。完整运行记录在 `outputs/scene-v2/final-render.log`。

最终视频使用 32 samples/pixel、每批 2 samples 的路径追踪。Windows 上避免把全部 samples 放进单个 GPU 批次，长批次曾触发设备丢失。脚本在场景初始化后重新设置并核验采样总数，防止场景初始化把总数覆盖成每批的数量；实际参数记录在视频旁的 JSON 文件中。

场景脚本是 `scripts/scene_reference.py`。它替换了原来的长方形白盘、零散背景吐司和拼接式握刀手：

- 两只带深蓝青海波纹的立体陶瓷圆盘，左侧四片重叠吐司。
- 上方金属糖碗及细小糖粒，右上蓝白黄油盒及刮取后有起伏的黄油表面。
- 灰色台面、较高的俯视镜头、矩形柔光与金属反射光。
- 带不规则边缘、薄面包皮和细小起伏的吐司网格，使用新白吐司面包瓤纹理。
- 连续曲面的扶盘手、较薄的指甲和关节褶线，替代旧的分离几何体。
- 银色抹刀的微弧刀面；Isaac RTX PathTracing 输出。

主要道具都是可编辑三维网格与材质，没有把参考照片作为场景背景。面包和黄油及刀具一起旋转以适应构图；原始 MPM 状态、刀具轨迹和材料参数不变。主面包的显示轮廓是柔化后的吐司形状，物理接触仍使用已有的矩形刚体近似。

黄油表面完全来自 `mpm-surface.npz`；没有按刀路补画额外涂层。手、糖碗、黄油盒是显示资产，不参与接触求解。手仍为程序化模型，尚非扫描资产；镜头和物体尺寸由单张照片估计，不能视为精确标定或照片级数字孪生。当前 MPM 黄油的覆盖面积与参考截图也不完全一致，本次着重于场景和材质。

`scripts/prepare_scene_assets.py` 可重建花纹、台面贴图、盒体标签和连续手部网格，使用 Genesis 虚拟环境运行。`assets/textures/bread-crumb-v2.png` 由内置 imagegen 生成，完整提示词见同目录的 `bread-crumb-v2.prompt.txt`；其他新花纹由代码绘制。原始材质与脚本保存在 `assets/visual-v1/`（脚本）及原贴图文件中。

工作区另有 `render_matched.py` 摄影平面版本，其用途与本三维重建不同；本文的结果与验证只指 `render_isaac.py` 直接渲染三维场景的输出。
