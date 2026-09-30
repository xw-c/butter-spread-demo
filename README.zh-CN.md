# 小刀抹黄油：Genesis MPM + Isaac Sim

最新三维资产版为 **scene-v3**：采用 CD-MPM 开源的多孔面包几何，重建薄片圆头餐刀，并移除手模型。物理状态由 `run-demo.ps1 -PhysicsOnly` 生成；本工作区已在 `../lw-runtime` 安装 Isaac Sim 5.1 并预处理 CD-MPM 面包网格，可用 `run-demo.ps1 -ReusePhysics` 渲染该三维场景。来源和物理/视觉边界见 [SCENE-V3.zh-CN.md](SCENE-V3.zh-CN.md)。

当前面包变形版视频为 `outputs/butter-spread-deformable-bread-v8.mp4`；默认输出同步更新。上一轮黄油涂层修正视频保留为 `outputs/butter-spread-contact-v7.mp4`。涂层排查记录见 [DEBUG-COATING.zh-CN.md](DEBUG-COATING.zh-CN.md)。

目标是复现[参考视频](https://www.youtube.com/watch?v=KC-QHA_xxEY)的 16–19 秒。用户提供了其中一帧截图，位于 `assets/reference/16-19s-user-frame.png`。当前工作以该帧为场景依据：灰色台面、两只深蓝波纹盘、左侧叠放的吐司、黑色糖碗、右上打开的黄油盒、手扶住的操作面包和银色抹刀。

## 运行与输出

```powershell
cd D:\StartupDemo\butter-spread-demo
.\run-demo.ps1 -PhysicsOnly
# 阅读并接受 NVIDIA Omniverse 许可协议后，在当前终端设置：
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
.\run-demo.ps1 -ReusePhysics
# 只重渲染已有物理轨迹（不重新求解/重建表面）：
.\render-scene.ps1 -Samples 64 -Width 1280 -Height 720 -Output (Join-Path $PWD 'outputs\butter-spread.mp4')
```

`-PhysicsOnly` 生成新的 Genesis MPM 轨迹、审计和表面数据，不需要 Isaac Sim。`-Frames 24` 可先生成一秒；`-ReusePhysics` 复用已有轨迹。默认直接渲染 MPM 粒子重建的三维场景，输出 `outputs/butter-spread.mp4`。旧摄影投影模式需显式传入 `-PhotoMatched`，输出 `outputs/butter-spread-matched.mp4`，仅用于与照片比对，不可用于验证物理。粒子诊断图可用 `conda run -n genesis-world python scripts/preview_physics.py` 生成。Isaac Sim 许可协议见 NVIDIA 官方页面：https://docs.omniverse.nvidia.com/platform/latest/common/NVIDIA_Omniverse_License_Agreement.html 。

物理结果为 `outputs/mpm-state.npz`、`mpm-state.json`、`mpm-surface.npz` 和 `physics-audit.json`。原三维场景视频为 `outputs/butter-spread.mp4`，对应的 USD 场景为 `outputs/butter-spread.usdc`；摄影投影模式另输出 `outputs/butter-spread-matched.mp4`。

## 物理与画面来源

`scripts/simulate_mpm.py` 使用同工作区 `genesis-world/examples/cream` 的 `HerschelBulkleyButter` 与 `PorousBread`。黄油本构参数保持 G=20 kPa、K=150 kPa、Y=80 Pa、c=25 Pa·s^0.5、n=0.5。求解仍为 Genesis MPM/CPIC，dt=35 μs、grid_density=512；面包粒子间距 1.0 mm，黄油单独加密到 0.5 mm。Genesis 的 MPM 材料现支持可选 `particle_size`，粒子质量及应力积分使用各自的参考体积，避免加密时错误地增加质量或内力。`scripts/check_mpm_quadrature.py` 验证混合采样的质量、自由落体和压缩响应。初始黄油采用分层采样，每个材料单元内一个积分点，固定随机种子 17；这样减少规则晶格被拉伸后形成的周期性采样条纹。仅初始化时采样，运行中不再添加随机扰动。

当前初始黄油为 40 × 30 × 18 mm，约 19.4 g，含 172,800 个物质点。这次同时增加了实际黄油量，以保留足够厚的涂层；并非仅增加粒子数。刀片保持平放：0–0.9 秒缓慢按压，0.9–1.65 秒边加速移动边逐渐降低，继续涂抹至 3.5 秒，再于 3.5–4 秒抬起。最大下压速度约 25 mm/s，涂抹末段刀位比旧版高 2.8 mm。调整入口为 `scripts/knife_motion.py` 中的时间和高度常量，以及 `scripts/simulate_mpm.py` 中的 `BUTTER_SIZE`。面包、餐刀和背景资产保持原场景设置。

接触使用有限范围的平衡黏附区与有界切向滑移。已经接触或重叠时，不再持续施加向内黏附拉力；接触层的牵引力积分也与黄油采样密度解耦。初始黄油与面包的物质点中心按两者半间距之和放置，消除旧版半格重叠。刀片仍有单侧法向速度约束，防止薄碰撞体吞入粒子；修正以固定物理时间响应，避免时间步变小后接触修正反而变强。盘面下固定支撑体厚 20 mm；具体本构、接触、质量及采样参数均记录在 `outputs/mpm-state.json`。

`scripts/prepare_surface.py` 调用连续质量密度重建：各粒子以真实参考体积加权，使用固定 B 样条核和固定半密度等值面。光照法线取自同一密度场的梯度，避免每帧三角形划分变化干扰光照。没有逐帧归一化、连通域删除、粒子删除、时间滤波或额外涂层。上一版固定连接初始材料边界的方法已撤下，因为它可能跨过实际稀疏区。`physics-audit.json` 检查完整粒子轨迹；视频验证额外检查表面连通数、孔洞、体积变化、黑帧、刀片穿透和沉积区域的法向位移，并以文件哈希确保视频、表面、物理状态及审计属于同一轮运行。真实粒子仍有小幅残余松弛，代码没有冻结它们。

操作面包继续使用 Genesis 原版相同的 `PorousBread` 本构及全部参数。`scripts/bread_deformation.py` 将约 302 万个外观顶点绑定到初始规则 MPM 粒子晶格，以固定材料坐标的三线性位移插值驱动全部孔隙表面；边界半个粒子单元作线性外推，位移倍率为 1。法线使用位移映射的逆转置更新，UV、孔隙拓扑和面包材质分区不变。绑定在 `/World/Task` 坐标中计算，与刀具、黄油共用场景旋转。操作面包解除共享实例，仅覆盖自身的顶点、法线和包围盒，背景面包不受影响。`scripts/check_bread_deformation.py` 检查刚体运动、压缩/剪切、边界、法线及 Genesis 参数一致性；渲染报告记录每帧网格变形和 USD 回读检查。该网格是宏观 MPM 软体的外观，不将每个可见孔隙作为独立物理空腔求解。

`scripts/render_matched.py` 在 Isaac Sim 中使用摄影材质平面重建所给截图的镜头布局。`assets/matched/clean-scene.png` 是在截图上去掉旧刀具与面包表面旧黄油后的摄影底图；`buttered-scene.png` 保留参考画面的黄油涂层；`butter-knife.png` 是透明背景的银色抹刀。三张图由 imagegen 对用户截图局部编辑或提取，均已保存到项目。编辑要求分别为：保留其他场景对象并移除旧刀；只移除操作面包上的旧黄油；只提取带黄油残留的银色抹刀。

照片黄油涂层按 Genesis 保存的刀具位置和 MPM 粒子铺展范围逐帧显现，因此画面与给定截图更接近。**照片涂层是外观近似，不是直接由 MPM 粒子网格渲染的物理厚度场。** `scripts/render_isaac.py` 可显示直接由粒子重建的三维表面，便于区分物理求解结果和高保真画面。摄影底图意味着糖碗、黄油盒、盘子、叠放吐司和扶面包的手保持静止；相机也是固定的。

物理部分使用 conda 环境 `genesis-world` 及同工作区的 `genesis-world` 源码；渲染使用独立的 `../lw-runtime` Isaac Sim 5.1 环境。原场景视频 `outputs/butter-spread.mp4` 默认按 1280 × 720、24 fps、97 帧、64 samples 渲染；完整验证结果记录在 `outputs/video-validation.json`。摄影投影渲染沿用原有照片涂层显示逻辑，不能作为黄油几何形状的物理验证；应查看三维场景视频及 `mpm-state.npz`、`mpm-surface.npz`。操作面包的 CD-MPM 外观网格现已随 MPM 粒子逐帧变形；背景叠放的面包保持静态。当前文件夹内也没有机械臂关节/控制器，只有给刀具规定的位姿轨迹。
