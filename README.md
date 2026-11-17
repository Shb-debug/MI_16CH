# MI_16CH：左手抓取运动想象

## 1. 文件职责

- config.py：读取配置并检查通道、频带和端口。
- acquisition_lsl.py：发现 OpenBCI GUI 的 LSL 流并低延迟收取样本。
- preprocessing.py：单位缩放、CAR 重参考、50 Hz 陷波和有状态因果带通。
- quality_control.py：检查 NaN、峰值、平线和异常窗口；异常窗口只阻断，不触发事件。
- recorder.py：把每个 trial 保存为 X=(trial, channel, sample)、y 和时间戳。
- protocol.py：生成随机平衡试次和提示。
- features_fbcsp.py：正则化 CSP 和 log-variance 特征。
- models.py：滤波器组 CSP + StandardScaler + shrinkage LDA，保存模型元数据。
- training.py：采集或训练；0=rest，1=left_hand_grasp。
- decoder.py：2 秒滑动窗口、概率平滑、阈值判断、冷却和再次触发阻断；当前抓取阈值为 probability > 0.4。
- server.py：启动实时处理、WebSocket、HTTP 页面和演示模式。
- frontend：浏览器演示页面。

当前在线配置为 probability > 0.4 触发、probability <= 0.25 重新武装、单次确认；实时概率和状态会写入 Python 终端日志。
完整的学员授课流程见 [TEACHING_TUTORIAL.md](TEACHING_TUTORIAL.md)。

## 2. 安装

在 PowerShell 中执行：

    cd E:\dijikeji\naojijiekou\MI_16CH
    python -m pip install -r requirements.txt

先启动 OpenBCI GUI，连接 ExpandableEEG 16 通道模块，启用 Networking Widget 的 LSL 输出。本项目当前配置使用流名 `obci_eeg1`、source_id `openbcigui`；如果电脑上名称不同，应改成 OpenBCI GUI 中实际显示的流名和 source_id。

## 3. 采集训练数据

    python training.py --config mi_config.json --collect --trials-per-class 40 --data data\left_hand.npz

每次按 Enter 后，程序先收 2 秒静息基线，再显示任务并收 4 秒。任务期间保持身体放松、眼睛自然睁开，只想象左手抓住一个物体，不要真的动手。建议每个用户至少 60--100 个 task trial 和同等数量 rest trial，分 3 次 session 采集；当前脚本是单次 session 的可运行 MVP。

## 4. 训练模型

    python training.py --config mi_config.json --data data\left_hand.npz --model artifacts\mi_model.joblib

训练使用 4--40 Hz 滤波器组、正则化 CSP 和 shrinkage LDA，输出验证集 balanced accuracy。部署前还应使用独立 session 和连续静息测试检查误触发。

合并多个 session 或多次采集的数据：

    python merge_datasets.py data\left_hand.npz data\session1.npz --output data\merged_left_hand.npz

然后用合并文件训练：

    python training.py --config mi_config.json --data data\merged_left_hand.npz --model artifacts\mi_model.joblib

## 5. 运行

真实 EEG：

    python server.py --config mi_config.json

演示模式（不需要 OpenBCI/LSL）：

    python server.py --config mi_config.json --demo

浏览器打开 http://127.0.0.1:8000/。WebSocket 默认是 ws://127.0.0.1:8765。

## 6. 通道选择（按 ExpandableEEG 16 通道说明书）

默认算法通道顺序为：

    通道1 Fp1，通道2 Fp2
    通道3 C3， 通道4 C4
    通道5 T5， 通道6 T6
    通道7 O1， 通道8 O2
    通道9 F7， 通道10 F8
    通道11 F3，通道12 F4
    通道13 T3，通道14 T4
    通道15 P3，通道16 P4

左手运动想象重点观察右侧中央感觉运动区 C4（程序索引 3），辅助使用 F4（索引 11）和 P4（索引 15）；C3（索引 2）、F3（索引 10）、P3（索引 14）作为左右对照。实际接线如果不是这个顺序，必须修改 channel_indices，不能只修改 channel_order 标签。

说明书指出：ExpandableEEG 16 通道的底层接口是通道 1--8，上层扩展接口是通道 9--16；BIAS、SRB 等是参考/偏置连接，不应当作为普通 EEG 通道放入这 16 个数据通道。

## 7. 采样率

程序读取 LSL 的 nominal_srate()，并把实际值写入数据和模型；训练和在线运行必须使用同一个实际采样率。

- ExpandableEEG 说明书给出的采样率为 250/500/1000 Hz。
- 你的截图显示 OpenBCI GUI 当前为 16 通道、250 Hz，因此本项目默认配置改为 250 Hz。
- 250 Hz 对 8--30 Hz 运动想象频段已经足够，优先选择它以降低数据量和处理负担。

程序仍以 LSL 的实际 nominal_srate() 为准。如果启动日志不是 250 Hz，先记录实际值；训练和在线都必须使用同一个值。不要手动插值来补成另一个采样率。

## 8. 稳定性注意

训练与在线必须保持相同的通道顺序、采样率、参考方式、滤波频带和单位缩放。电极阻抗、眨眼、咬牙、手部真实移动都会影响结果；坏窗口会阻断事件而不是猜测。模型只输出 left_hand_grasp 与 rest，浏览器事件仅在概率连续超过阈值后产生。

## 9. 机械臂 USB 桥接

机械臂的 USB 连接如果使用 USB-TTL 或 USB-RS485 适配器，在程序中仍表现为一个
Windows COM 口。`arm_bridge.py` 默认是 dry-run，不打开串口，也不移动舵机。

先运行安全模拟桥接：

    python arm_bridge.py --config arm_config.json

另一个终端验证本机桥接：

    python -c "from arm_client import ArmBridgeClient; print(ArmBridgeClient().request({'command':'PING'}))"

真实动作前可单独测试一个已标定姿态。`home`、`approach`、`grasp`、`lift`、`hold`
已按 ServoStudio 截图写入配置，但首次运动仍应清空工作区、准备急停，并从 `home`
或 `approach` 单姿态开始：

    python -c "from arm_client import ArmBridgeClient; print(ArmBridgeClient().request({'command':'MOVE_POSE','pose':'home'}))"

真实串口诊断需要先安装 `pyserial`，并把 `arm_config.json` 中的 `serial_port` 改成
设备管理器显示的实际 COM 口：

    python arm_bridge.py --config arm_config.json --real

只要执行真实位置动作，还必须在确认机械臂周围安全、准备急停后显式加上
`--allow-motion`：

    python arm_bridge.py --config arm_config.json --real --allow-motion

随后另开一个 PowerShell 启动脑机服务：

    python server.py --config mi_config.json

最后打开 http://127.0.0.1:8000/。OpenBCI GUI 的 LSL 流应为 `obci_eeg1`、source_id
为 `openbcigui`。第一次实际运行前，ServoStudio 必须断开 COM9（机械臂继续上电），并且
8766 端口只能有一个 `arm_bridge.py` 进程；否则 Windows 会出现 COM 口拒绝访问。

程序在第一个满足阈值的 `CANDIDATE` 窗口产生一次抓取事件，机械臂会完整执行
`home → approach → grasp → lift → hold`。每个姿态都等待舵机位置进入容差范围后才发送
下一个姿态；硬件故障时会在超时后报错。脑机状态后续回到 REST 不会取消已经开始的宏。
点击网页“放下水杯”会请求机械臂回到 `home`；如果抓取宏尚未结束，该请求会等待宏结束后再回 home。

OpenBCI 暂停采集时，可用模拟 LSL 流检查 MI 实时链路：

    python simulate_lsl.py

另一个终端使用 `mi_sim_config.json` 启动服务：

    python server.py --config mi_sim_config.json

模拟配置使用独立的 LSL 名称、WebSocket 端口和 HTTP 端口，不连接机械臂。
