# 16 通道左手抓取运动想象：架构、算法与 Demo 设计

版本：1.0  
日期：2026-09-15  
存放位置：`E:\dijikeji\naojijiekou\MI_16CH_DESIGN`  
文档性质：开发设计说明。本文描述计划实现的文件和功能，不表示这些 Python 文件或训练模型已经生成。

## 1. 目标与设计原则

构建一个本地运行、通过 OpenBCI GUI 的 LSL EEG 输出工作的运动想象应用。用户想象左手抓取物体，系统识别意图后触发网页中的左手抓取动画。

系统只有一个正向控制目标：`LEFT_HAND_GRASP`。训练任务采用 `left_hand_grasp` 与 `rest` 两种标签；Rest 是背景和拒识类别，不是第二种控制动作。两类训练不能省略背景数据。

采用多模块、单在线运行进程、离线训练与在线解码分离的架构。模块化方便定位采集、滤波、模型和通信问题；在线数据通过内存传递，避免各模块分别开进程转发 EEG。

主要原则：

- 以真实通道映射、单位、时间戳和采样率为基础，不从硬件名称推断所有数据属性。
- 训练、验证、在线运行使用同一套预处理定义。
- 先验证单模型，再比较辅助模型与融合模型；不存在对所有用户都最好的固定算法。
- 信号质量不合格、断流、模型不兼容时进入阻断状态，禁止输出控制事件。
- 每次持续的抓取意图最多触发一次；释放到 Rest 后才能重新武装。
- 演示事件和真实 EEG 事件在来源、界面和记录中明确区分。
- 原始数据保持不变，滤波和单位换算只处理分析副本。

## 2. OpenBCI 采集约束与采样率修正

当前假设设备为 Cyton + Daisy，使用常规无线 USB Dongle 连接 OpenBCI GUI，再通过 Networking Widget 输出 LSL。

**必须修正此前“16 通道统一按 250 Hz 处理”的说法：常规 Cyton+Daisy 无线 16 通道流通常为每通道 125 Hz。** 芯片以 250 SPS 采集、无线交替发送主板和 Daisy 包，与完整 16 通道帧率不是同一个概念。官方 SD 卡记录说明也区分了无线流的 125 Hz 和 SD 卡原始采集的 250 Hz。[OpenBCI 产品组合与采样率](https://docs.openbci.com/FAQ/HowProductsGoTogether/)、[Cyton+Daisy SD 卡记录说明](https://docs.openbci.com/Cyton/CytonSDCard/)

实现必须：

1. 读取 LSL `nominal_srate()`、通道数、流名称和 source_id。
2. 用足够长的时间戳序列核对实际帧率和连续性；不能仅用 chunk 到达速度估计采样率。
3. 如果采样率为零、单位未知或存在多个候选 EEG 流，要求配置明确指定，不静默选择。
4. 支持已核实的 125 Hz、250 Hz 或其他设备帧率，按实际帧率生成滤波器和窗口长度。
5. 如上游进行了插值/重复样本，记录该过程；插值到 250 Hz 不等于新增了真实时间信息。
6. 模型包记录训练数据来源与帧率；SD 卡原始数据不能直接当作无线实时流的等价训练数据。

125 Hz 下 2 秒窗口约为 250 个样本；250 Hz 下约为 500 个样本。所有频带上限须低于实际 Nyquist 频率，并预留滤波过渡带。

OpenBCI GUI 提供设备连接、记录和数据输出；Networking Widget 可以选择 LSL，接收端应选择时域 EEG 流，而不是 FFT 或汇总频带功率流。[OpenBCI GUI 文档](https://docs.openbci.com/Software/OpenBCISoftware/GUIDocs/)、[OpenBCI LSL 文档](https://docs.openbci.com/Software/CompatibleThirdPartySoftware/LSL/)

## 3. 整体架构

```text
Cyton + Daisy / 16 通道 EEG
          ↓
OpenBCI GUI → LSL 时域 EEG
          ↓
acquisition_lsl.py → recorder.py 保存原始样本和时间戳
          ↓
固定容量内存队列 / 环形缓存
          ↓
原始质量检查 → 单位转换 → 重参考 → 有状态因果滤波
          ↓
窗口质量检查 / 2 秒滑动窗口
          ├─ features_fbcsp.py → 正则化 CSP → Shrinkage LDA
          └─ features_riemann.py → 收缩协方差 → 切空间 → Logistic Regression
          ↓
经验证选定的模型 / 校准后的概率融合
          ↓
decoder.py：候选、确认、锁存、释放、冷却、阻断
          ↓
server.py：WebSocket 事件与遥测、HTTP 页面与健康检查
          ↓
frontend：左手抓取实验室 Demo
```

训练分支：

```text
protocol.py 生成平衡随机试次和任务标记
          ↓
recorder.py 保存 EEG、标记、session 元信息
          ↓
training.py 调用相同预处理，按 trial/session 划分数据
          ↓
训练 CSP / 切空间参考 / 分类器 / 概率校准 / 决策阈值
          ↓
独立 session 测试和连续静息测试
          ↓
合格模型包 → 在线加载
```

## 4. 计划目录与每个文件的职责

以下目录是未来实现建议；当前方案文件夹只保存本文档。

```text
MI_16CH/
├─ config.py
├─ acquisition_lsl.py
├─ preprocessing.py
├─ quality_control.py
├─ recorder.py
├─ protocol.py
├─ features_fbcsp.py
├─ features_riemann.py
├─ models.py
├─ decoder.py
├─ training.py
├─ server.py
├─ mi_config.json
├─ requirements.txt
├─ train_mi.bat
├─ start_mi_real.bat
├─ start_mi_demo.bat
├─ frontend/
│  ├─ index.html
│  ├─ app.js
│  └─ styles.css
├─ data/
├─ artifacts/
└─ tests/
```

| 文件/目录 | 具体职责 | 输入与输出/边界 |
|---|---|---|
| `config.py` | 加载 JSON、校验参数、解析路径、生成配置摘要与哈希 | 拒绝重复/越界索引、非法频带、未知单位；不采集 EEG |
| `acquisition_lsl.py` | 精确选择流、创建 inlet、pull_chunk、核对时间戳、断流与重连 | 输出原始 chunk、LSL 时间戳和流元信息；不滤波、不分类 |
| `preprocessing.py` | 确定性单位换算、重参考、陷波、滤波器组、跨 chunk 状态管理 | 同一组件供训练重放和在线使用；不修改原始数组 |
| `quality_control.py` | 检查饱和、平线、非有限值、幅度、方差、线噪声、时间间断和运动伪迹指标 | 输出是否可用及原因列表；不将伪迹解释为 Rest 生理状态 |
| `recorder.py` | 保存原始 EEG、样本时间戳、任务标记、配置和事件日志 | 磁盘写入使用有界队列；原始样本与分析数据分开 |
| `protocol.py` | 生成平衡随机试次、安排静息/提示/想象/休息、记录实际显示标记 | 管理 trial_id、session_id、类别；标签不能依据模型预测生成 |
| `features_fbcsp.py` | 从滤波器组学习正则化 CSP，提取对数归一化方差 | CSP 仅在训练 fold 拟合；在线只做 transform |
| `features_riemann.py` | 收缩协方差估计、SPD 检查、训练几何参考、切空间映射 | 参考点只用训练数据拟合；CAR 后处理秩不足 |
| `models.py` | 包装 LDA、Logistic Regression、概率校准、可选融合、模型包加载校验 | 输出 MI 分数或校准概率；不负责事件防抖 |
| `decoder.py` | 滑动窗口调度、平滑、质量阻断、确认、锁存、释放、冷却 | 将模型结果转换成至多一次抓取事件；不启动 HTTP |
| `training.py` | 按 session/trial 划分、内层调参、特征选择、校准、评估、导出模型 | 训练入口；测试数据不参与任何拟合或阈值选择 |
| `server.py` | 在线入口，启动采集/处理线程与 HTTP、WebSocket，分发状态和事件 | 一个在线进程；通信故障不阻塞采集；管理停机和资源释放 |
| `mi_config.json` | 流标识、物理通道映射、单位、参考、频带、窗口、决策和端口参数 | 采样率允许自动读取，但异常值不能静默回退 |
| `requirements.txt` | 锁定验证过的依赖与版本范围 | 建议 NumPy、SciPy、pylsl、scikit-learn、pyRiemann、websockets |
| `train_mi.bat` | 启动离线训练入口，打印数据与输出模型位置 | 不和真实在线控制自动混跑 |
| `start_mi_real.bat` | 启动 `server.py` 的真实 LSL 模式 | 模型不合格或缺失时允许诊断，禁止真实事件 |
| `start_mi_demo.bat` | 启动明确标记为模拟的展示模式 | 模拟数据与真实记录分开 |
| `frontend/index.html` | 页面结构、状态面板、Canvas、训练提示和模式标识 | 无 EEG 数值处理 |
| `frontend/app.js` | WebSocket 接收、事件去重、界面更新、抓取动画、任务显示与标记回传 | 重连不能重播旧事件；键盘事件标记为 MANUAL |
| `frontend/styles.css` | 页面布局、主题、响应式样式 | 不通过动画速度隐含模型置信度 |
| `data/` | 按 subject/session 保存采集数据和元信息 | 不混合模拟和真实 session |
| `artifacts/` | 版本化模型包、兼容性 manifest、验证报告 | 只有批准的版本进入真实在线解码 |
| `tests/` | 核验时间连续性、滤波状态、模型兼容性、阻断、释放、事件去重 | 合成数据测试验证工程行为，不能证明真实 MI 准确率 |

可以将 `mi_model.pkl` 或 joblib 文件作为模型包中的序列化文件，但仅一个裸 pkl 不足以交付模型。必须同时提供参数、数据来源、兼容性清单和独立验证结果；只加载可信本地模型。

## 5. 在线线程、数据契约与缓存

### 5.1 执行模型

`server.py` 负责生命周期，建议包含：采集工作线程、处理工作线程、记录写盘线程以及 asyncio 通信循环。训练由单独的离线入口运行，不在在线事件循环中进行。

模块之间用有界内存队列和固定容量缓存通信。队列长度、窗口新鲜度、处理耗时需要可观测。积压时不可把几秒前的预测当作当前意图发送。

发生队列溢出、重连、时间戳缺口或帧率切换时，进入 `BLOCKED`，清空未完成窗口、滤波状态和候选计数；连续有效数据重新覆盖完整窗口后再恢复。不要把间断前后的数据直接拼成一次 trial。

### 5.2 数据契约

| 数据对象 | 必须包含 |
|---|---|
| EEGChunk | samples、sample_timestamps、stream_id、channel_names、units、sample_rate、sequence |
| AnalysisWindow | window_id、开始/结束 LSL 时间、固定通道顺序、参考/滤波版本、各频带数组 |
| QualityResult | valid、bad_channels、原因、各通道指标、时间连续性 |
| Prediction | window_id、目标分数/概率、模型版本、质量状态、生成时间 |
| MIEvent | event_id、LEFT_HAND_GRASP、窗口末端时间、确认时间、模型版本、来源模式 |

NumPy 数组方向必须固定，例如输入 `(samples, channels)`，epoch `(trials, channels, samples)`。转换只在明确边界发生。

LSL 时间用于对齐 EEG 与任务标记；monotonic 时间用于本机耗时和冷却；wall-clock 时间用于显示和日志。三者不能混用。浏览器 performance.now 需要映射到服务端/LSL 时钟，不能直接当 LSL 时间戳。

## 6. 16 通道布局与硬件映射

建议覆盖双侧感觉运动区域，逻辑顺序如下：

| 零基索引 | 位置 | 零基索引 | 位置 |
|---|---|---|---|
| 0 | FC3 | 8 | FC4 |
| 1 | C3 | 9 | C4 |
| 2 | CP3 | 10 | CP4 |
| 3 | FC1 | 11 | FC2 |
| 4 | C1 | 12 | C2 |
| 5 | CP1 | 13 | CP2 |
| 6 | Cz | 14 | P3 |
| 7 | CPz | 15 | P4 |

左手想象的分析重点为右侧中央区域 C4、FC4、CP4，同时使用 C3、FC3、CP3 和中线通道作空间对照。实际 ERD 空间分布具有个体差异，不强制假定每个人均出现单一对侧模式。

这是建议 montage，必须根据实际帽子位置填写。`N1P–N8P` 是连接引脚名称，不是 EEG 头皮位置，也不能假定 LSL 已提供正确的 10–20 标签。GUI 通道 1–8 对应 Cyton，9–16 对应 Daisy，引脚与位置需逐一确认。[OpenBCI 电极帽通道映射](https://docs.openbci.com/AddOns/Headwear/ElectrodeCap/)

参考与 BIAS 接线遵循所用电极和硬件指南；先检查接触和饱和。CAR 是数字重参考，不替代正确的硬件参考接线。训练完成后不能随意在线删除坏通道：CSP、切空间和分类器依赖固定通道维数与顺序。临时坏通道应阻断；如确需降通道，使用经过独立训练验证的备用模型。

## 7. 预处理设计

正确顺序：

```text
原始 chunk / 时间戳检查与记录
      ↓
原始饱和、平线、幅度、线噪声与运动质量检查
      ↓
确定性单位转换 → 固定通道选择 → 数字重参考
      ↓
可选 50/60 Hz 陷波 → 有状态因果滤波器组
      ↓
滑动窗口与窗口质量检查 → 特征提取
```

### 7.1 单位

优先采用流元信息和采集端已知缩放；未知单位需显式配置确认。不要从第一小块样本幅度猜测 V、mV、µV 或 counts。统一分析单位可以为 µV，但避免对已缩放的 GUI/BrainFlow 数据再次乘缩放系数。原始 counts 的系数与 ADC 增益有关。[Cyton 计数与单位换算](https://docs.openbci.com/Cyton/CytonDataFormat/)

### 7.2 重参考与滤波

CAR 为默认候选；局部 Laplacian/局部平均参考可作为训练时比较方案。参考方法一旦随模型发布，在线固定使用。

建议初始滤波器组为 4–8、8–12、12–16、16–20、20–24、24–30、30–40 Hz；核心 μ/β 分析也可以只选 8–30 Hz 的子频带。是否保留 4–8 与 30–40 Hz 由内层验证决定。30–40 Hz 对肌电敏感，不应仅因提高离线分数就采用。

采用 SciPy 二阶节 SOS 形式的因果 IIR，跨 chunk 保留状态，不在每个窗口重新初始化。工频陷波按环境选择 50 或 60 Hz；在完整带通已充分衰减工频时可经验证关闭，避免冗余滤波。

最终训练与在线回放使用相同的因果处理链：对连续 session 滤波后再分窗，而不是对每个独立 epoch 随意重置状态。零相位结果可用于探索图，不作为未经在线一致性验证的部署依据。

### 7.3 质量门控

原始检查发现 NaN/Inf、饱和、平线、异常方差、严重工频或突变时给出具体原因；窗级检查结合前后的幅度、频带能量和运动指标。质量指标不是“真实 MI 概率”。

线噪声和高频肌电检查必须在相应频率仍存在的原始/宽带数据上做，不能先滤到 4–40 Hz 再判断被滤掉的 50 Hz 干扰。

不默认对每个 2 秒窗重新拟合 ICA。若需要 ICA/EOG 回归，必须有充分校准数据和稳定拟合规则，并纳入同一训练/在线处理链。

## 8. 算法 A：正则化 FBCSP + Shrinkage LDA

这是首个必须实现并独立评估的基线。FBCSP 将 EEG 分为多个频带，学习 CSP 空间滤波，再进行特征选择和分类；频带与时间窗需要针对使用者验证。[FBCSP 原始研究](https://doi.org/10.3389/fnins.2012.00039)

### 8.1 协方差与 CSP

对每个频带、每个有效 trial，计算去均值后的协方差，并按 trace 归一化。分别求 Rest 和左手抓取的类别平均协方差 C0、C1。采用收缩正则化，例如：

```text
C_regularized = (1 - α) C + α × trace(C)/n × I
C1 w = λ (C0 + C1) w
```

α 仅由训练集的内层验证选择。使用稳定的广义特征值求解器或白化流程，保护小特征值；如存在 CAR 导致的秩下降，应使用已验证的降秩或正则化方案。

每个频带初始保留两端各 2 个分量，共 4 个；分量数允许内层验证选择。

### 8.2 特征与分类器

```text
Z = W X
feature_i = log(variance(Z_i) / sum_j variance(Z_j) + ε)
```

7 个频带、每带 4 个分量，初始为 28 个特征。拼接后可用互信息或其他受控特征选择，再执行标准化和 Shrinkage LDA。CSP、选择器、标准化和 LDA 均只在当前训练 fold 拟合。

LDA 输出首先是分数，不能直接把手工 sigmoid 后的数值宣称为已校准概率。需要按 session/trial 独立留出的校准数据或交叉验证的 out-of-fold 分数进行校准。

## 9. 算法 B：收缩协方差 + Riemannian 切空间 + Logistic Regression

作为待比较的辅助路线，不能预先保证其跨天表现优于 FBCSP。

1. 从 8–30 Hz 或经验证选定的频带取相同时间窗口。
2. 估计每窗收缩协方差，确保矩阵对称正定。
3. 在训练数据上计算几何参考点。
4. 将协方差映射到参考点的切空间，生成向量特征。
5. 训练正则化 Logistic Regression，并验证其校准和泛化。

CAR 使协方差可能秩不足。必须通过收缩、固定降秩投影或其他已验证方案保证 SPD；在线不能改变投影和参考点。

使用 pyRiemann 的训练/transform 接口时，参考点必须仅从训练 fold 拟合；测试数据不能参与 fit。跨 session 是否更新参考点需作为单独适配方案验证，不默认在线无标签自更新。[pyRiemann 官方文档](https://pyriemann.readthedocs.io/)

## 10. 模型选择、校准和融合

比较三种候选：A 单模型、B 单模型、A+B 融合。选取满足误触发指标且独立 session 表现较好的方案，而不是默认双模型更好。

融合公式：

```text
p_final = w × p_fbcsp + (1 - w) × p_riemann
```

权重 0.6/0.4 只能作为待测试示例。权重、概率校准、阈值与拒识规则均在训练/验证范围内确定，测试 session 保持未触碰。数据不足时可先发布 A 单模型，将 B 与融合留到后续比较。

模型包必须包含：目标标签、通道列表与顺序、实际帧率、单位与缩放、参考方式、滤波器设计、特征选择、CSP/切空间参数、分类器、校准器、阈值、状态机参数、训练 subject/session、依赖版本、模型版本和验证报告。

加载时验证这些属性与当前输入匹配。模型缺失、帧率不兼容、通道错位或单位不一致时可展示 EEG 诊断，但禁止真实抓取事件。

## 11. 训练任务与实验设计

### 11.1 参与者任务

想象自己左手主动抓住物体的肌肉感觉和触觉；左手实际保持放松，避免握拳、手臂移动、咬牙或屏气。系统识别的是与任务相关的 EEG 模式，不能仅靠按钮动画证明检测到了运动想象。

建议采集同样提示形式的 Rest 对照试次，避免模型只学会看到“左手”文字、看球体或等待提示的视觉反应。训练标签来自预设任务，不由模型预测推导。

### 11.2 无歧义时间轴

以 cue_onset 为 t=0：

| 相对提示时间 | 阶段 | 内容 |
|---|---|---|
| -2 到 0 秒 | 基线 | 睁眼注视、自然放松 |
| 0 秒 | 提示 | 平衡随机显示 LEFT_HAND_GRASP 或 REST |
| 0 到 4 秒 | 任务 | 进行抓取想象或保持相同注视的静息 |
| 0.5 到 2.5 秒 | 候选训练窗 | 初始 2 秒窗口；由训练验证选择 |
| 4 到 6–8 秒 | 休息 | 返回静息，试次间隔轻度随机 |

0.5–2.5 秒窗是初始设计，不能保证适合所有用户。每类 60–100 个有效 trial 为起始目标，拆成短 run 并记录疲劳；被伪迹拒绝的 trial 不计入有效数量。

建议规划 4 个 session：1–2 用于训练与内层调参，3 用于外层验证/阈值评估，4 用于最终测试；如只有 3 个 session，需重新设计嵌套划分，不能声称有第四组独立测试。

### 11.3 标记与记录

记录 cue_onset、task_end、rest_start、trial_id、label、session_id 和实际显示时间。浏览器通过 requestAnimationFrame 报告显示时刻，再映射到服务端/LSL 时钟；对精确刺激同步要求更高时可增加硬件触发或光电测量。

同一个 trial 的所有重叠窗口必须处于同一个数据划分。更进一步，建议按 session 做外层拆分；调参、特征选择、校准与融合在内层完成。禁止用测试 session 选择频带、阈值或融合权重。

额外采集连续 Rest 和常见干扰段，例如自然眨眼、视线变化、小幅姿势变化，用于评估误触发和质量门控。不能只用提示式 Rest 的窗口准确率代表连续在线可靠性。

## 12. 在线决策与防重复触发

初始参数仅为验证起点：2 秒窗口，120–200 ms 更新，短时概率平滑，0.70–0.80 高阈值，低阈值小于高阈值，确认持续约 250–500 ms，最小冷却约 1 秒。所有值由独立验证的事件级误触发/延迟曲线选择。

高度重叠的相邻窗不独立。连续两次超过阈值只是防抖，不是两次独立证据；状态机应记录持续时间，而不仅是次数。

```text
WARMUP → REST → CANDIDATE → LATCHED（发出一次抓取）
                    └─ 条件不满足 → REST
LATCHED → 低于释放阈值并持续稳定 + 满足最小冷却 → REST
任何状态 → 质量异常/断流/模型不兼容 → BLOCKED
BLOCKED → 连续有效完整窗口 + 静息释放 → REST
```

关键规则：

- 持续高概率时保持锁存，不能每过 1 秒就重新抓取。
- 候选确认要求所有参与窗口质量有效、数据新鲜、模型兼容。
- 质量失败时清空平滑和候选；不能把失效窗口当作正常低概率 Rest 并立即重新武装。
- 超过允许数据年龄的窗口不产生事件。
- 每个确认事件分配唯一 event_id；浏览器按 event_id 去重。
- 冷却结束后还必须完成低阈值释放条件，才允许下一次事件。

2 秒窗口与 120 ms 更新不代表 120 ms 意图识别延迟。实际延迟包括生理响应、窗口证据、平滑、确认、采集批量和通信；应以有标记的实测结果报告。

## 13. WebSocket 与 HTTP 设计

建议本地默认端口：HTTP 页面与 `/health` 为 8000，WebSocket 为 8765；配置可修改。不要和同机正在运行的眨眼桥接器占用相同端口。

### 13.1 状态

```json
{
  "type": "status",
  "mode": "real",
  "lsl_connected": true,
  "stream": "obci_eeg1",
  "channel_count": 16,
  "sample_rate": 125,
  "model_ready": true,
  "model_version": "subject01_v1",
  "state": "REST",
  "message": "采集与模型可用"
}
```

### 13.2 遥测

```json
{
  "type": "mi_telemetry",
  "mode": "real",
  "target": "left_hand_grasp",
  "mi_probability": 0.82,
  "probability_calibrated": true,
  "state": "CANDIDATE",
  "quality_valid": true,
  "quality_reasons": [],
  "window_id": 208,
  "window_end_lsl": 12345.67,
  "data_age_ms": 95,
  "window_seconds": 2.0
}
```

### 13.3 事件

```json
{
  "type": "mi_event",
  "event_id": "session01-grasp-0007",
  "command": "LEFT_HAND_GRASP",
  "confidence": 0.86,
  "mode": "real",
  "simulated": false,
  "model_version": "subject01_v1",
  "window_end_lsl": 12345.67
}
```

`/health` 报告服务运行、流连接、模型兼
容、最近样本时间、质量阻断和队列积压。HTTP 能访问不代表 EEG 可用。遥测广播限制频率，慢客户端不能阻塞采集；断开后清理客户端和待发送任务。

## 14. NEURO GRIP LAB Demo 场景

### 14.1 页面布局

左侧为来源与模型状态、通道数、实际帧率、质量原因和 MI 分数/概率；中央为简洁左手轮廓与抓取目标；右侧显示已完成抓取数量；底部为事件与状态日志。

显示实际采样率，不能写死 250 Hz。未校准分数显示“模型分数”；质量不合格显示原因。不能用装饰性的神经环暗示已测量到皮层激活位置。

### 14.2 动画与状态绑定

| 系统状态 | 场景表现 | 是否允许抓取 |
|---|---|---|
| WARMUP | 手掌张开，显示初始化/缓存进度 | 否 |
| REST | 目标静置，提示可开始想象 | 否 |
| CANDIDATE | 环形指示逐渐充能，目标轻度高亮 | 否 |
| LATCHED / mi_event | 左手闭合，抓住目标球并移到收集区 | 唯一事件触发一次 |
| COOLDOWN/释放等待 | 手部动画完成，提示放松，等待重新武装 | 否 |
| BLOCKED | 场景暂停，显示接触、运动或断流原因 | 否 |

只有 `mi_event` 驱动抓取，telemetry 只更新状态与指标。不能看到高概率就由网页自行抓取，否则绕过服务端的确认、质量和释放规则。

### 14.3 真实、模拟与手动

真实来源显示 `REAL EEG · LSL`，必须具备可用流、合格模型和有效窗口。展示来源显示 `DEMO MODE · SIMULATED`，可用定时或按钮生成模拟事件；手动按钮标记 `MANUAL`。三种来源使用不同事件记录，不合并为真实 MI 成功次数。

演示模式分两级：场景事件回放验证动画和通信；合成 EEG 经完整 pipeline 验证工程行为。两者都不能用于报告真实用户识别率。

### 14.4 展示流程

选择模式 → 核对来源和模型 → 观察 Rest → 左手抓取想象/模拟候选 → 确认抓取 → 放松释放 → 再次抓取。真实训练时先不显示模型反馈，减少标签与反馈混淆；独立反馈 run 再显示概率与动画。

## 15. 验证与指标

### 工程验证

- LSL 流选择唯一且准确，采样率/单位/通道数可核验。
- 原始样本不变；同一连续数据整块处理和分 chunk 处理结果一致。
- 重连、时间缺口、队列溢出后不使用旧窗口，滤波状态正确重置。
- 训练回放与在线预处理输出可对齐。
- 模型包不兼容时阻断；坏通道不会静默改变特征维数。
- 持续高分只触发一次；低阈值释放完成后才可重新触发。
- 重连和广播重试不会造成重复动画。
- Demo、Manual、Real 模式标记一致，失去真实流时不自动伪装模拟连接。

### 真实 EEG 验证

报告 Balanced Accuracy、混淆矩阵、目标召回率、Rest 拒识率、有效数据比例、每分钟误触发次数和标记对齐的检测延迟分布。使用独立 session，并注明测试时长和被拒绝的窗口比例。

误触发率按事件计算：连续 Rest 中错误抓取事件数 / 有效测试分钟数，同时报告质量阻断时间；不能靠把大部分时间阻断来声称误触发很低。

应核对任务效果是否来自 EEG 而非手部微动、眼动、肌电或视觉提示。检查 C3/C4 周边 μ/β 功率变化及空间模式；必要时增加独立运动/肌电监测对照。所有指标应与同一划分上的简单 bandpower 基线比较。

具体发布门槛在采集前确定，例如可接受的每分钟误触发上限与目标召回率；数据没有达标时继续诊断，不宣称“算法最好”或保证个人准确率。

## 16. 实施顺序

1. 完成 LSL、原始记录、时间标记、单位和帧率核验。
2. 完成共享预处理、质量门控和诊断界面。
3. 完成平衡任务采集、按 session 划分与 FBCSP+LDA 基线。
4. 完成锁存/释放状态机、独立连续 Rest 测试和模型包校验。
5. 完成抓取 Demo、真实/模拟模式与事件去重。
6. 加入 Riemannian 路线，与基线公平比较；有独立收益才启用融合。
7. 固定模型与决策参数，在新 session 做完整在线展示和报告。

当前眨眼 `direct_eeg_bridge.py` 的窗口、特征和状态机服务于另一任务。MI 实现建议独立放在仓库根目录的 `MI_16CH` 中；可复用已验证的 LSL 接收与通信经验，重新实现记录、训练、协方差特征和抓取决策。

## 17. 给开发者/其他 Agent 的交付要求

以本文为实现规格，先核验实际硬件、流帧率、单位与物理通道映射，再实现各模块。首个发布模型为 target-vs-rest 的 FBCSP+Shrinkage LDA；Riemannian 与融合属于待验证候选。全部拟合步骤仅使用训练数据，在线处理复用训练定义，最终报告基于独立 session。

交付内容包括模块源代码、配置、可复现依赖、采集/训练/真实/演示启动流程、数据格式说明、带兼容性 manifest 的模型包、工程检查结果、真实测试报告以及 NEURO GRIP LAB 场景。没有真实数据时只交付工程验证结果和模拟演示，不附带虚构模型准确率。

## 18. 参考资料

- [OpenBCI GUI](https://docs.openbci.com/Software/OpenBCISoftware/GUIDocs/)：设备连接、记录、阻抗和外部数据输出。
- [OpenBCI LSL](https://docs.openbci.com/Software/CompatibleThirdPartySoftware/LSL/)：Networking Widget 和 LSL 接收。
- [OpenBCI 产品组合](https://docs.openbci.com/FAQ/HowProductsGoTogether/)：Cyton+Daisy 常规无线 125 Hz。
- [Cyton Data Format](https://docs.openbci.com/Cyton/CytonDataFormat/)：交替包、平均机制和单位换算。
- [Cyton SD Card](https://docs.openbci.com/Cyton/CytonSDCard/)：SD 原始 250 Hz 与无线 125 Hz 的区别。
- [OpenBCI 电极帽](https://docs.openbci.com/AddOns/Headwear/ElectrodeCap/)：主板/Daisy 引脚和通道映射。
- [Ang et al., 2012, FBCSP](https://doi.org/10.3389/fnins.2012.00039)：滤波器组、CSP、特征选择和训练/评估设计。
- [pyRiemann](https://pyriemann.readthedocs.io/)：协方差与切空间算法实现接口；部署时需锁定验证过的版本。
