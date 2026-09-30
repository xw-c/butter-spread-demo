# 面包与餐刀资产改版（scene-v3）

本版根据用户提供的 4.2 秒录屏与 CD-MPM 面包示例，替换真正的三维资产，并在 Isaac Sim RTX 中渲染。视频关键帧见 `assets/reference/video/contact-sheet.jpg`。

## 本版改动

- 面包直接采用论文开源仓库中的 `Data/LevelSets/breadxxx.vdb.zip`，通过 Blender Volume to Mesh 提取原始分辨率表面，保留 3,017,626 个顶点、6,035,978 个三角面，包括内部孔隙壁。最终没有采用会损失薄壁的降采样版本。
- 面包尺寸规范为约 140 × 114 × 16 mm；独立划分外皮材质，加入细纤维颜色纹理、微法线和弱次表面散射。背景面包共享同一网格，采用不同摆放和轻微缩放。
- 餐刀改为圆头、宽而平的薄刀片、窄刀颈与圆润金属刀柄，加入倒角和拉丝法线。刀片长约 95 mm、宽约 20 mm、厚约 1.2 mm，尺寸依据视频外观估计，没有真实标尺校准。
- 移除手部模型；保留参考图中的花纹盘、灰色台面、黄油盒和糖碗。

## 输出与运行

```powershell
cd D:\StartupDemo\butter-spread-demo
.\run-demo.ps1 -PhysicsOnly
$env:OMNI_KIT_ACCEPT_EULA = 'YES'  # 阅读并接受 NVIDIA 协议后
.\run-demo.ps1 -ReusePhysics
```

- 物理轨迹：`outputs/mpm-state.npz`、`outputs/mpm-state.json`
- 物理审计与表面：`outputs/physics-audit.json`、`outputs/mpm-surface.npz`
- 已生成并验证的原场景视频及 USD：`outputs/butter-spread.mp4`、`outputs/butter-spread.usdc`

主视频为 1280 × 720、24 fps、97 帧，路径追踪每帧累计 64 samples；每次 GPU 更新使用 2 samples，避免 Windows 长 GPU 任务超时。近景诊断使用 128 samples。

## 复现边界

目前黄油状态由 Genesis MPM 中的 Herschel–Bulkley 本构驱动，面包物理层使用多孔压实本构，二者通过有限范围湿接触相互作用。三维渲染使用保存的黄油粒子及其重建表面，没有额外贴在面包上的假涂抹层。CD-MPM 面包网格仅用于外观；其损伤、断裂求解没有移植。物理面包对齐可见面包的尺寸与盘面高度；碰撞刀片按可见刀片的平面轮廓尺寸校准，并使两者下表面对齐。操作面包的外观网格由保存的 MPM 粒子位移驱动：在初始材料坐标中作三线性插值，边界作半单元线性外推，并以逆转置变换更新法线。形变不放大，孔隙拓扑、UV 和材质分区保留；背景面包仍为静态实例。

动画为 4 秒单次涂抹：刀片保持平放，先用 0.9 秒缓慢按压，再边移动边逐渐降低；3.5 秒完成行程后才抬起。初始黄油改为 40 × 30 × 18 mm，以保留厚涂层。面包粒子间距为 1.0 mm，黄油为 0.5 mm；每个物质点使用相应参考体积，密度和本构参数不因加密改变。

表面由连续质量密度直接重建，固定核宽和等值面，光照法线取密度梯度，不删连通域或粒子，不强制保留初始表面拓扑。上一版固定拓扑表面可能跨过实际稀疏区，已停止使用。验证会拒绝独立碎块、薄层孔洞和明显表面抖动；残余的连续材料松弛以粒子运动报告给出，不通过冻结隐藏。

它不是录屏中完整多次涂抹动作的逐帧六自由度重建。当前源码未包含机械臂关节或控制器。黄油用量、厚度和涂抹范围与录屏仍有差异。USD 导出的是最后一帧场景；完整时间过程由 NPZ 状态与渲染脚本重放。

## 数据来源与许可

- 论文主页：https://joshuahwolper.com/cdmpm
- 开源代码：https://github.com/penn-graphics-research/ziran2019
- 原始面包数据：`Data/LevelSets/breadxxx.vdb.zip`，上游 Git blob `d2bd04fc3afeba050e95a6812deb56cea27c6d0f`
- 下载压缩包 SHA256：`b4e9a2c2f5690bf541016b52d15f631bbc1c5a42e187308fcf381f956fee8116`
- MIT 许可与署名保存在 `assets/reference/cdmpm/LICENSE`（Penn Graphics Research，2020）。
- 提取脚本：`scripts/inspect_bread_vdb.py`；规范化、表面法线与外皮分类：`scripts/prepare_cdmpm_mesh.py`；USD 材质与餐刀建模：`scripts/bread_knife_assets.py`。

论文的源几何被用于外观重建，不代表复现了论文的断裂物理结果。
