# 面包与餐刀资产改版（scene-v3）

本版根据用户提供的 4.2 秒录屏与 CD-MPM 面包示例，替换真正的三维资产，并在 Isaac Sim RTX 中渲染。视频关键帧见 `assets/reference/video/contact-sheet.jpg`。

## 本版改动

- 面包直接采用论文开源仓库中的 `Data/LevelSets/breadxxx.vdb.zip`，通过 Blender Volume to Mesh 提取原始分辨率表面，保留 3,017,626 个顶点、6,035,978 个三角面，包括内部孔隙壁。最终没有采用会损失薄壁的降采样版本。
- 面包尺寸规范为约 140 × 114 × 16 mm；独立划分外皮材质，加入细纤维颜色纹理、微法线和弱次表面散射。背景面包共享同一网格，采用不同摆放和轻微缩放。
- 餐刀改为圆头、宽而平的薄刀片、窄刀颈与圆润金属刀柄，加入倒角和拉丝法线。刀片长约 95 mm、宽约 20 mm、厚约 1.2 mm，尺寸依据视频外观估计，没有真实标尺校准。
- 移除手部模型；保留参考图中的花纹盘、灰色台面、黄油盒和糖碗。

## 输出与运行

```powershell
cd D:\xwchen
.\butter-spread-demo\render-scene.ps1 -Samples 32
```

- 新视频：`outputs/scene-v3/butter-spread.mp4`
- 可编辑 USD 场景（最后一帧静态状态）：`outputs/scene-v3/butter-spread.usdc`
- 面包近景：`outputs/scene-v3/bread-detail.png`
- 渲染设置与场景审计：`outputs/scene-v3/butter-spread.json`
- 视频解码及数据一致性检查：`outputs/scene-v3/video-validation.json`
- 原版对照：`outputs/scene-v3/previous-v2.mp4`

主视频为 1280 × 720、24 fps、73 帧，路径追踪每帧累计 32 samples；每次 GPU 更新使用 2 samples，避免 Windows 长 GPU 任务超时。近景使用 24 samples。

## 复现边界

本次修改集中在资产与材质。黄油仍由已有 Genesis MPM 状态及其重建表面驱动，没有使用额外贴在面包上的假涂抹层。面包在物理层仍使用原有刚体碰撞代理，没有移植 CD-MPM 的损伤、断裂或可压缩多孔面包求解。可见餐刀比原有碰撞代理更薄，碰撞代理尚未按新刀片重新标定。

动画仍为原有 3 秒单次涂抹轨迹，并非录屏中完整多次涂抹动作的逐帧六自由度重建。黄油厚度、涂抹范围与录屏仍有差异。USD 导出的是最后一帧场景；完整时间过程由 NPZ 状态与渲染脚本重放。

## 数据来源与许可

- 论文主页：https://joshuahwolper.com/cdmpm
- 开源代码：https://github.com/penn-graphics-research/ziran2019
- 原始面包数据：`Data/LevelSets/breadxxx.vdb.zip`，上游 Git blob `d2bd04fc3afeba050e95a6812deb56cea27c6d0f`
- 下载压缩包 SHA256：`b4e9a2c2f5690bf541016b52d15f631bbc1c5a42e187308fcf381f956fee8116`
- MIT 许可与署名保存在 `assets/reference/cdmpm/LICENSE`（Penn Graphics Research，2020）。
- 提取脚本：`scripts/inspect_bread_vdb.py`；规范化、表面法线与外皮分类：`scripts/prepare_cdmpm_mesh.py`；USD 材质与餐刀建模：`scripts/bread_knife_assets.py`。

论文的源几何被用于外观重建，不代表复现了论文的断裂物理结果。
