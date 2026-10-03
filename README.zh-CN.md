# 小刀抹黄油：Genesis MPM + Isaac Sim

最新三维资产版为 **scene-v3**：采用 CD-MPM 开源的多孔面包几何，重建薄片圆头餐刀，并移除手模型。物理状态由 `run-demo.ps1 -PhysicsOnly` 生成；安装和首次资源准备见下文，新克隆无需作者的本地目录。来源和物理/视觉边界见 [SCENE-V3.zh-CN.md](SCENE-V3.zh-CN.md)。

当前面包变形版视频为 `outputs/butter-spread-deformable-bread-v8.mp4`；默认输出同步更新。上一轮黄油涂层修正视频保留为 `outputs/butter-spread-contact-v7.mp4`。涂层排查记录见 [DEBUG-COATING.zh-CN.md](DEBUG-COATING.zh-CN.md)。

目标是复现[参考视频](https://www.youtube.com/watch?v=KC-QHA_xxEY)的 16–19 秒。用户提供了其中一帧截图，位于 `assets/reference/16-19s-user-frame.png`。当前工作以该帧为场景依据：灰色台面、两只深蓝波纹盘、左侧叠放的吐司、黑色糖碗、右上打开的黄油盒、手扶住的操作面包和银色抹刀。

## 从新电脑运行

仓库现在包含 `physics/` 中的黄油/面包本构、接触实现，以及 `vendor/` 中的完整求解器补丁。**不需要同级 `genesis-world` 或 `lw-runtime` 文件夹，也不需要获取作者未提交的代码。** 仍需安装公开的软件依赖；“独立运行”不表示仓库自带 Python、CUDA 或 Isaac Sim。

准备 Python **3.11**、Git、Blender（本机验证为 5.2），以及支持 Isaac Sim RTX 的 NVIDIA 显卡/驱动。物理和渲染使用两个环境，避免 Genesis 与 Isaac 的 NumPy/Numba 版本冲突。固定引擎版本与校验值见 `vendor/genesis-lock.json`，来源许可见 `vendor/NOTICE.txt`。

### Windows / PowerShell

```powershell
git clone https://github.com/xw-c/butter-spread-demo.git
cd butter-spread-demo
# 指向 Python 3.11；安装物理、Isaac 两个环境。首次会下载较大的公开依赖。
.\setup-demo.ps1 -Python python -WithIsaac
# 阅读并接受 NVIDIA Omniverse 许可协议后，自行设置：
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
# 首次从仓库自带的 VDB 自动生成面包网格；Blender 在 PATH 或标准安装目录即可。
.\run-demo.ps1
```

Blender 不在标准位置时使用 `-Blender '你的 Blender 可执行文件完整路径'`。也可以先做短测试：

```powershell
.\run-demo.ps1 -Frames 2
# 再计算完整的 97 帧，覆盖短测试的输出
.\run-demo.ps1
# 已有完整轨迹时重渲染
.\render-scene.ps1
```

只有物理环境时可运行 `.\setup-demo.ps1` 和 `.\run-demo.ps1 -PhysicsOnly`；不需要 Blender 或 Isaac。无 GPU 的物理测试使用安装选项 `-Cpu`，运行选项 `-Backend cpu -Frames 2 -PhysicsOnly`，完整 CPU 模拟会慢很多。

已有环境时不必重装 Isaac：在物理环境运行 `python scripts/bootstrap_genesis.py`，再运行 `python -m pip install -r requirements-physics.txt -e .vendor/genesis`，另行确认 CUDA PyTorch 已安装。随后给入口传入 `-PhysicsPython '物理环境的 python.exe' -IsaacPython 'Isaac 环境的 python.exe'`。Isaac 环境应安装 `requirements-render.txt` 中的辅助库。也支持 `BUTTER_PHYSICS_PYTHON`、`BUTTER_ISAAC_PYTHON` 和 `BLENDER_EXE` 环境变量。

### Linux

```bash
python3.11 scripts/setup_demo.py --with-isaac
# 阅读并接受许可后设置
export OMNI_KIT_ACCEPT_EULA=YES
.venv-physics/bin/python scripts/run_demo.py --blender /path/to/blender
```

安装流程按 Windows 实测；Linux 入口使用相同 Python 脚本，但本轮没有在 Linux/另一台 GPU 上执行验证。Isaac 的系统要求及安装说明见 [NVIDIA 官方文档](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_python.html)，许可协议见 [NVIDIA 协议页面](https://docs.omniverse.nvidia.com/platform/latest/common/NVIDIA_Omniverse_License_Agreement.html)。脚本不会替其他使用者接受许可。

### 输出与故障定位

- 默认输出为 `outputs/mpm-state.npz`、`mpm-surface.npz`、`physics-audit.json`、`butter-spread.mp4` 和 `butter-spread.usdc`。97 帧完整三维视频会生成 `video-validation.json`。
- `outputs/` 中的视频、模拟缓存和预处理面包网格没有提交。新克隆必须先运行流程生成；不能直接用 `-ReusePhysics`。
- 面包源文件 `assets/reference/cdmpm/breadxxx.vdb.zip` 已提交。网格缺失时，`scripts/prepare_assets.py` 自动解压、调用 Blender 提取、再归一化；无需别人传给你 `cdmpm-bread-hero-ready.npz`。
- `.vendor/genesis` 由公开上游固定提交生成，随后应用仓库内补丁。加载时校验补丁文件；不会悄悄改用系统里另一份 Genesis。若校验失败，先保留该目录中的个人改动，再在新的克隆中重建。
- `-Frames 2` 等短测试仅验证可执行流程，不代替完整涂抹的物理/画面验收。
- 摄影投影模式 `-PhotoMatched` 仅供参考画面对比；默认三维视频才是模拟结果。

本轮独立性验证：从暂存的仓库文件导出干净目录，创建不继承系统包的新物理 venv，下载公开 Genesis、应用补丁，并从提交的 VDB 重新生成 3,017,626 顶点的面包。GPU 两帧模拟、物理审计、表面重建、Isaac 640×360 视频输出及解码均通过；运行入口从仓库外目录调用。Isaac 使用显式指定的已有 5.1 运行时，本轮没有重装 Isaac，也没有重算完整 97 帧。混合 MPM 采样的质量/压缩回归、面包网格变形回归及 `pip check` 均通过。

## 物理与画面来源

`scripts/simulate_mpm.py` 使用本仓库 `physics/cream_materials.py` 中的 `HerschelBulkleyButter` 与 `PorousBread`，接触实现为 `physics/cream_contact.py`。黄油本构参数保持 G=20 kPa、K=150 kPa、Y=80 Pa、c=25 Pa·s^0.5、n=0.5。求解仍为 Genesis MPM/CPIC，dt=35 μs、grid_density=512；面包粒子间距 1.0 mm，黄油单独加密到 0.5 mm。Genesis 的 MPM 材料现支持可选 `particle_size`，粒子质量及应力积分使用各自的参考体积，避免加密时错误地增加质量或内力。`scripts/check_mpm_quadrature.py` 验证混合采样的质量、自由落体和压缩响应。初始黄油采用分层采样，每个材料单元内一个积分点，固定随机种子 17；这样减少规则晶格被拉伸后形成的周期性采样条纹。仅初始化时采样，运行中不再添加随机扰动。

当前初始黄油为 40 × 30 × 18 mm，约 19.4 g，含 172,800 个物质点。这次同时增加了实际黄油量，以保留足够厚的涂层；并非仅增加粒子数。刀片保持平放：0–0.9 秒缓慢按压，0.9–1.65 秒边加速移动边逐渐降低，继续涂抹至 3.5 秒，再于 3.5–4 秒抬起。最大下压速度约 25 mm/s，涂抹末段刀位比旧版高 2.8 mm。调整入口为 `scripts/knife_motion.py` 中的时间和高度常量，以及 `scripts/simulate_mpm.py` 中的 `BUTTER_SIZE`。面包、餐刀和背景资产保持原场景设置。

接触使用有限范围的平衡黏附区与有界切向滑移。已经接触或重叠时，不再持续施加向内黏附拉力；接触层的牵引力积分也与黄油采样密度解耦。初始黄油与面包的物质点中心按两者半间距之和放置，消除旧版半格重叠。刀片仍有单侧法向速度约束，防止薄碰撞体吞入粒子；修正以固定物理时间响应，避免时间步变小后接触修正反而变强。盘面下固定支撑体厚 20 mm；具体本构、接触、质量及采样参数均记录在 `outputs/mpm-state.json`。

`scripts/prepare_surface.py` 调用连续质量密度重建：各粒子以真实参考体积加权，使用固定 B 样条核和固定半密度等值面。光照法线取自同一密度场的梯度，避免每帧三角形划分变化干扰光照。没有逐帧归一化、连通域删除、粒子删除、时间滤波或额外涂层。上一版固定连接初始材料边界的方法已撤下，因为它可能跨过实际稀疏区。`physics-audit.json` 检查完整粒子轨迹；视频验证额外检查表面连通数、孔洞、体积变化、黑帧、刀片穿透和沉积区域的法向位移，并以文件哈希确保视频、表面、物理状态及审计属于同一轮运行。真实粒子仍有小幅残余松弛，代码没有冻结它们。

操作面包继续使用 Genesis 原版相同的 `PorousBread` 本构及全部参数。`scripts/bread_deformation.py` 将约 302 万个外观顶点绑定到初始规则 MPM 粒子晶格，以固定材料坐标的三线性位移插值驱动全部孔隙表面；边界半个粒子单元作线性外推，位移倍率为 1。法线使用位移映射的逆转置更新，UV、孔隙拓扑和面包材质分区不变。绑定在 `/World/Task` 坐标中计算，与刀具、黄油共用场景旋转。操作面包解除共享实例，仅覆盖自身的顶点、法线和包围盒，背景面包不受影响。`scripts/check_bread_deformation.py` 检查刚体运动、压缩/剪切、边界、法线及 Genesis 参数一致性；渲染报告记录每帧网格变形和 USD 回读检查。该网格是宏观 MPM 软体的外观，不将每个可见孔隙作为独立物理空腔求解。

`scripts/render_matched.py` 在 Isaac Sim 中使用摄影材质平面重建所给截图的镜头布局。`assets/matched/clean-scene.png` 是在截图上去掉旧刀具与面包表面旧黄油后的摄影底图；`buttered-scene.png` 保留参考画面的黄油涂层；`butter-knife.png` 是透明背景的银色抹刀。三张图由 imagegen 对用户截图局部编辑或提取，均已保存到项目。编辑要求分别为：保留其他场景对象并移除旧刀；只移除操作面包上的旧黄油；只提取带黄油残留的银色抹刀。

照片黄油涂层按 Genesis 保存的刀具位置和 MPM 粒子铺展范围逐帧显现，因此画面与给定截图更接近。**照片涂层是外观近似，不是直接由 MPM 粒子网格渲染的物理厚度场。** `scripts/render_isaac.py` 可显示直接由粒子重建的三维表面，便于区分物理求解结果和高保真画面。摄影底图意味着糖碗、黄油盒、盘子、叠放吐司和扶面包的手保持静止；相机也是固定的。

物理部分默认使用 `.venv-physics` 和本项目固定的 `.vendor/genesis`；渲染默认使用独立的 `.venv-isaac` Isaac Sim 5.1 环境，也可显式指定解释器。原场景视频 `outputs/butter-spread.mp4` 默认按 1280 × 720、24 fps、97 帧、64 samples 渲染；完整验证结果记录在 `outputs/video-validation.json`。摄影投影渲染沿用原有照片涂层显示逻辑，不能作为黄油几何形状的物理验证；应查看三维场景视频及 `mpm-state.npz`、`mpm-surface.npz`。操作面包的 CD-MPM 外观网格现已随 MPM 粒子逐帧变形；背景叠放的面包保持静态。当前文件夹内也没有机械臂关节/控制器，只有给刀具规定的位姿轨迹。
