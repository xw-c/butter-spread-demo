# 小刀抹黄油：Genesis MPM + Isaac Sim

最新三维资产版为 **scene-v3**：采用 CD-MPM 开源的多孔面包几何，重建薄片圆头餐刀，并移除手模型。运行 `render-scene.ps1`，输出 `outputs/scene-v3/butter-spread.mp4`；面包近景为 `outputs/scene-v3/bread-detail.png`。来源、运行方法和物理复现边界见 [SCENE-V3.zh-CN.md](SCENE-V3.zh-CN.md)。下文的默认 `run-demo.ps1` 仍是此前的摄影投影模式。

目标是复现[参考视频](https://www.youtube.com/watch?v=KC-QHA_xxEY)的 16–19 秒。用户提供了其中一帧截图，位于 `assets/reference/16-19s-user-frame.png`。当前工作以该帧为场景依据：灰色台面、两只深蓝波纹盘、左侧叠放的吐司、黑色糖碗、右上打开的黄油盒、手扶住的操作面包和银色抹刀。

## 运行与输出

```powershell
& 'D:\xwchen\butter-spread-demo\run-demo.ps1'
```

默认生成 `outputs/butter-spread-matched.mp4`（73 帧、24 fps、1280×720）和 `matched-frame-*.png`。`-Frames 24` 可先生成一秒；`-Gui` 打开 Isaac 窗口。`-Procedural` 生成更新后的三维网格场景 `outputs/butter-spread.mp4`，含花纹圆盘、叠放吐司、糖碗和黄油盒；细节见 [SCENE-V2.zh-CN.md](SCENE-V2.zh-CN.md)。如只更新画面，可运行 `render-scene.ps1`，复用既有 MPM 数据。

物理结果为 `outputs/mpm-state.npz`、`mpm-state.json`、`mpm-surface.npz` 和 `physics-audit.json`。Isaac 保存最终 USD 场景为 `outputs/butter-spread-matched.usda`。

## 物理与画面来源

`scripts/simulate_mpm.py` 通过 Genesis `MPM.ElastoPlastic` 求解软黄油，面包和刀片是刚体接触边界。14 个底层粒子通过软约束粘附面包，其余粒子自由形变。当前 440 个粒子均保持有限且在面包区域内；沿刀具方向的跨度从 25.5 mm 增至 54.8 mm，二维覆盖范围约为初始的 2.96 倍，数值审计通过。刀具轨迹是人工规定的，没有从视频逐帧提取。

`scripts/render_matched.py` 在 Isaac Sim 中使用摄影材质平面重建所给截图的镜头布局。`assets/matched/clean-scene.png` 是在截图上去掉旧刀具与面包表面旧黄油后的摄影底图；`buttered-scene.png` 保留参考画面的黄油涂层；`butter-knife.png` 是透明背景的银色抹刀。三张图由 imagegen 对用户截图局部编辑或提取，均已保存到项目。编辑要求分别为：保留其他场景对象并移除旧刀；只移除操作面包上的旧黄油；只提取带黄油残留的银色抹刀。

照片黄油涂层按 Genesis 保存的刀具位置和 MPM 粒子铺展范围逐帧显现，因此画面与给定截图更接近。**照片涂层是外观近似，不是直接由 MPM 粒子网格渲染的物理厚度场。** `scripts/render_isaac.py` 可显示直接由粒子重建的三维表面，便于区分物理求解结果和高保真画面。摄影底图意味着糖碗、黄油盒、盘子、叠放吐司和扶面包的手保持静止；相机也是固定的。

运行依赖复用同工作区的 `genesis-garment-demo/.venv`、`coffee-milk-demo/reference/genesis-world-mopping-simplified` 和 `lw-runtime` 中的 Isaac Sim 5.0。用户若提供更多连续帧，可进一步校准刀具轨迹、手的动作和涂层显现时序。
