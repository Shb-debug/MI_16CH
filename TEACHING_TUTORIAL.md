# MI_16CH 教学教程：从自己的脑电数据到左手抓取

这份教程面向第一次接触“脑电 + 机器学习 + 机械臂”的学员。建议教学顺序是：

```text
先看见结果 → 再理解数据 → 再训练自己的模型 → 最后连接真实机械臂
```

不要第一节课就让学员控制真实机械臂。先用模拟 LSL 和网页 Demo 建立成功体验，
再逐步增加难度。

## 一、学员最后要完成什么

每位学员完成四个小目标：

1. 能从 OpenBCI GUI 通过 LSL 收到自己的 16 通道 EEG。
2. 能采集两类自己的数据：`rest` 和 `left_hand_grasp`。
3. 能训练并保存自己的模型，在网页中看到自己的 MI 事件。
4. 能在 dry-run 中看到完整动作；经过教师检查后，再连接真实机械臂。

这里的“抓取”不是读懂思想，而是分类器根据一段 EEG 窗口给出一个控制分数。
概率分数是模型输出，不能直接当作医学意义上的真实概率。

## 二、先用一句话讲清楚架构

```text
OpenBCI GUI
    ↓ LSL 时域 EEG
acquisition_lsl.py
    ↓ 质量检查、CAR、陷波、带通
preprocessing.py + quality_control.py
    ↓ 2 秒窗口
FBCSP + LDA 模型
    ↓ probability
decoder.py
    ↓ mi_event
server.py → 浏览器网页
    ↓ LEFT_HAND_GRASP
arm_bridge.py → USB-RS485 → 6 个舵机
```

训练时，`training.py` 使用相同的预处理和特征流程训练模型；在线运行时，
`decoder.py` 加载这个模型进行实时判断。

## 三、项目文件职责

### 学员必须理解的脑机文件

| 文件 | 职责 |
|---|---|
| `mi_config.json` | EEG 流名称、16 通道顺序、采样率、频带、阈值、模型路径和服务端口。 |
| `__init__.py` | 标记当前目录可以作为 Python 包导入；不承担算法逻辑。 |
| `config.py` | 读取并检查配置。 |
| `acquisition_lsl.py` | 搜索 OpenBCI GUI 的 LSL 流并持续接收 EEG；训练采集和在线解码都使用它的 LSL 工具。 |
| `preprocessing.py` | 单位缩放、CAR 重参考、50 Hz 陷波和带通滤波。 |
| `quality_control.py` | 检查 NaN、峰值过大、平线等异常；异常窗口不会触发机械臂。 |
| `protocol.py` | 生成随机平衡试次并显示 REST/左手抓取提示。 |
| `recorder.py` | 将 EEG trial 保存为 `.npz` 数据集。 |
| `training.py` | `--collect` 采集数据；不加 `--collect` 时训练模型。 |
| `features_fbcsp.py` | 计算正则化 CSP 和 log-variance 特征。 |
| `models.py` | 训练 FBCSP + StandardScaler + shrinkage LDA，并保存模型元数据。 |
| `decoder.py` | 2 秒滑动窗口、概率平滑、阈值判断、释放、冷却和去重。 |
| `server.py` | 启动 LSL 在线处理、WebSocket、网页服务，并把事件转给机械臂桥接。 |
| `frontend/index.html` | 页面结构、欢迎页、状态面板、实验区和控制按钮。 |
| `frontend/app.js` | WebSocket 收消息、更新网页状态、记录事件和发送开始/放下/结束命令。 |
| `frontend/styles.css` | 页面基础布局和颜色。 |
| `frontend/motion.css` | 水杯、手和场景的抓取动画。 |
| `frontend/visual-overrides.css` | 当前版本的视觉主题覆盖样式。 |
| `frontend/first-person-water-cup.png` | 网页实验场景背景图。 |

### 机械臂文件

| 文件 | 职责 |
|---|---|
| `arm_config.json` | COM 口、波特率、舵机 ID、速度、五个姿态和动作顺序。 |
| `arm_protocol.py` | FT-SCS/STS 数据包的组包、校验和解析。 |
| `servo_bus.py` | 通过 pyserial 在 USB-RS485 上发送 PING、读位置、同步写位置等命令。 |
| `arm_motion.py` | 把姿态组合成 `home → approach → grasp → lift → hold`，并等待实际到位。 |
| `arm_bridge.py` | 本地 TCP JSON 桥接服务；默认 dry-run，真实动作必须显式 `--real --allow-motion`。 |
| `arm_client.py` | `server.py` 调用机械臂桥接服务的客户端。 |
| `start_arm_bridge.bat` | 快速启动安全的 dry-run 桥接；真实机械臂建议手动输入命令。 |

### 辅助、数据和测试文件

| 文件/目录 | 职责 |
|---|---|
| `simulate_lsl.py` | 生成模拟 EEG 的 LSL 流，OpenBCI 暂停时用于检查通信链路。 |
| `mi_sim_config.json` | 模拟 LSL 配置，使用独立端口，不连接真实机械臂。 |
| `merge_datasets.py` | 合并多个 session，检查采样率、通道顺序和数据形状是否兼容。 |
| `data/` | 采集得到的 `.npz` 数据，不是程序源代码。 |
| `artifacts/` | 训练得到的 `.joblib` 模型，不同学员应训练自己的模型。 |
| `tests/` | 协议和动作控制的自动测试。 |
| `tests/test_arm_protocol.py` | 检查舵机数据包校验、解析和拆包。 |
| `tests/test_arm_motion.py` | 检查 dry-run 动作和重复事件去重。 |
| `MI_16CH_DESIGN/` | 架构设计、算法说明和扩展思路，适合教师备课或学员深入阅读。 |
| `requirements.txt` | Python 依赖。 |
| `README.md` | 快速安装和运行说明。 |
| `*.bat` | Windows 快捷启动脚本。 |
| `__pycache__/` | Python 自动生成的缓存，不需要分发。 |

当前 `data/` 中的 `left_hand.npz`、`session1.npz`、`session2.npz` 和各个 `merged_*.npz`
都是已经采集的数据；`artifacts/` 中的 `mi_model.joblib` 和
`mi_model_3sessions.joblib` 都是已经训练的模型。它们适合教师演示，不应替代学员自己的
采集和训练。

## 四、推荐的六次课

### 第 1 次：先让大家看到成功

目标：不用脑电帽、不碰机械臂，也能看到完整软件链路。

```powershell
cd E:\dijikeji\naojijiekou\MI_16CH
python -m pip install -r requirements.txt
python simulate_lsl.py
```

另开 PowerShell：

```powershell
cd E:\dijikeji\naojijiekou\MI_16CH
python server.py --config mi_sim_config.json
```

浏览器打开 `http://127.0.0.1:8010/`。让学员观察 LSL、概率、状态和网页事件，
并画出自己的数据流图。此时不接真实机械臂。

### 第 2 次：连接 OpenBCI，确认 LSL

打开 OpenBCI GUI，连接设备并开启 LSL 输出。检查流名、source_id、通道数和实际
`nominal_srate()`。如果学员的流名不同，只修改配置中的
`lsl_stream_name` 和 `lsl_source_id`，不要修改算法代码。

### 第 3 次：采集每个人自己的数据

建议每位学员至少采集 3 个 session，每个 session 有同等数量的 REST 和左手抓取：

```powershell
python training.py --config mi_config.json --collect --trials-per-class 40 --data data\student01_session1.npz
```

采集时 REST 要身体放松、不想象抓取；LEFT HAND 要只想象左手抓住物体、不真的动手。
眼睛自然睁开，尽量减少眨眼、咬牙和身体动作。文件名使用姓名或编号加 session，
例如 `student01_session2.npz`。

REST 不是“没用的数据”，它是拒识类别，帮助系统知道什么时候不要抓取。

### 第 4 次：训练自己的模型

单个 session：

```powershell
python training.py --config mi_config.json --data data\student01_session1.npz --model artifacts\student01_model.joblib
```

多个 session：

```powershell
python merge_datasets.py data\student01_session1.npz data\student01_session2.npz data\student01_session3.npz --output data\student01_merged.npz
python training.py --config mi_config.json --data data\student01_merged.npz --model artifacts\student01_model.joblib
```

让学员记录 `validation_balanced_accuracy`，但提醒她们：验证分数不是实际使用保证，
还要用没有参与训练的 session 做独立测试。

把 `mi_config.json` 的模型路径改为自己的模型：

```json
"model_path": "artifacts/student01_model.joblib"
```

然后启动：

```powershell
python server.py --config mi_config.json
```

先不开机械臂，只观察 probability、`REST`、`CANDIDATE` 和 `COOLDOWN`。

### 第 5 次：做一个安全的小创新

每组只改一个变量并比较结果：阈值 `0.4/0.5/0.6`、窗口 `1.5/2.0/3.0` 秒、更新步长、
通道子集、单 session 与三 session 模型，或增加网页 probability 曲线、误触发计数、
反应时间统计。也可以做一个先采集 REST、再自动估计个人阈值的校准模式。

每次实验记录数据文件、配置文件、模型文件、验证分数、独立测试结果和误触发次数。

### 第 6 次：dry-run 后再接真实机械臂

先测试桥接，不接真实运动：

```powershell
python arm_bridge.py --config arm_config.json
python -c "from arm_client import ArmBridgeClient; print(ArmBridgeClient(port=8766).request({'command':'PING'}))"
```

真实机械臂必须由教师操作：机械臂上电、清空工作区、准备急停；ServoStudio 断开 COM9；
确认 8766 只有一个桥接进程；再执行：

```powershell
python arm_bridge.py --config arm_config.json --real --allow-motion
```

先单独测试 `home`，再测试 `approach`，最后才测试脑机抓取。真实动作是：

```text
第一个 probability > 0.4 的有效 candidate
    → home → approach → grasp → lift → hold
点击“放下水杯” → home
```

脑机状态回到 REST 不会取消已经开始的动作；通信和姿态超时保护仍然有效。

## 五、概率问题怎么教

当前设置为：

```json
"probability_high": 0.4,
"probability_low": 0.25,
"confirmations": 1,
"cooldown_seconds": 1.0
```

分数严格大于 0.4 时可能触发；分数降到 0.25 或以下后，系统才重新武装。0.25 到 0.4
之间是滞回区，用来减少阈值附近抖动。降低阈值会提高灵敏度，也可能增加误抓取。

学员应同时统计真阳性、漏检、REST 误触发和触发延迟，而不是只追求“抓得多”。

## 六、教师发哪些文件给学员

### 第一阶段：只教脑机

建议发送：

```text
README.md
TEACHING_TUTORIAL.md
requirements.txt
config.py
acquisition_lsl.py
preprocessing.py
quality_control.py
protocol.py
recorder.py
features_fbcsp.py
models.py
training.py
merge_datasets.py
decoder.py
server.py
frontend/
simulate_lsl.py
mi_config.json
mi_sim_config.json
start_mi_collect.bat
start_mi_demo.bat
start_mi_real.bat
train_mi.bat
tests/
```

同时发送空的 `data/` 和 `artifacts/` 目录，或者让学员自己创建；不要直接发送教师的
个人 EEG 数据作为她们的训练数据。

### 第二阶段：机械臂单独教学

可以发送 `arm_protocol.py`、`servo_bus.py`、`arm_motion.py`、`arm_bridge.py` 和
`arm_client.py` 作为接口学习材料，但不要让学员盲目使用教师的真实
`arm_config.json`、COM 口、姿态位置和速度。建议制作一份只有占位符的
`arm_config_template.json`，真实姿态由教师现场标定。

### 不建议发送

```text
__pycache__/
data/*.npz
artifacts/*.joblib
```

模型可以作为基线演示模型单独提供，但要说明它不是学员自己的模型，也不保证对别人的
脑电有效。`MI_16CH_DESIGN/` 可发给想深入研究的学员，初学者第一阶段不必读完。

## 七、学员验收清单

- [ ] 能解释一条 EEG 样本如何变成 `mi_event`。
- [ ] 能独立采集 REST 和左手抓取数据。
- [ ] 能训练自己的 `.joblib` 模型。
- [ ] 能用模拟 LSL 复现网页事件。
- [ ] 能说明为什么需要 REST 类别、质量检查和释放阈值。
- [ ] 能修改一个参数并用数据比较结果。
- [ ] 能在 dry-run 中完成桥接测试。
- [ ] 经过教师确认后，才能操作真实机械臂。

学员的成就感来自：她们采集的是自己的信号，模型是自己训练的，参数变化有自己的
实验结果，最后还能把一个安全的小创新展示给同学。
