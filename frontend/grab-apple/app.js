(() => {
  const $ = id => document.getElementById(id);
  const apples = [
    [27, 31], [37, 24], [48, 28], [59, 33], [68, 26], [22, 45], [34, 42],
    [45, 47], [57, 44], [71, 43], [30, 57], [41, 56], [53, 57], [64, 55], [76, 52]
  ];
  const appleLayer = $('appleLayer');
  const remaining = new Map();
  const handledEvents = new Set();
  const pendingEvents = new Set();
  let ws, running = false, picked = 0, demo = false;

  apples.forEach(([x, y], index) => {
    const apple = document.createElement('span');
    apple.className = 'apple'; apple.dataset.index = index;
    apple.style.left = `${x}%`; apple.style.top = `${y}%`;
    appleLayer.append(apple); remaining.set(index, apple);
  });

  function pill(id, label, state) {
    const el = $(id); el.textContent = label; el.className = `state-pill ${state}`;
  }
  function feedback(message, state = '') {
    $('feedbackText').textContent = message;
    $('feedback').className = `feedback ${state}`.trim();
  }
  function setConnection(ok, text) {
    $('connectionDot').className = `live-dot ${ok ? 'connected' : 'error'}`;
    $('connectionText').textContent = text;
    pill('bciState', ok ? (demo ? '演示模式' : '已连接') : '未连接', ok ? 'ok' : 'bad');
    $('bciDetail').textContent = ok ? (demo ? '接收模拟脑电数据' : 'WebSocket 实时数据') : '无法连接脑机服务';
  }
  function setRunning(value) {
    running = value;
    $('startBtn').disabled = value;
    $('stopBtn').disabled = !value;
    $('startBtn').textContent = value ? '采摘进行中…' : '▶开始采摘';
    if (!value) { $('intentState').textContent = '已暂停'; $('intentHint').textContent = '点击“开始采摘”继续'; }
  }
  function eventId(event) {
    return event.event_id == null ? `${event.timestamp || Date.now()}-${event.command || 'grasp'}` : String(event.event_id);
  }
  function onTelemetry(x) {
    demo = x.mode === 'demo' || Boolean(x.simulated);
    $('state')?.remove();
    $('signalDetail').textContent = `${x.sample_rate || '--'} Hz · ${x.quality_valid ? '信号有效' : '质量阻断'}`;
    pill('signalState', x.quality_valid ? '良好' : '阻断', x.quality_valid ? 'ok' : 'bad');
    const p = Math.max(0, Math.min(1, Number(x.mi_probability) || 0));
    $('probabilityText').textContent = `${Math.round(p * 100)}%`;
    $('probabilityBar').style.width = `${p * 100}%`;
    $('intentDisplay').classList.toggle('active', x.state === 'CANDIDATE');
    $('intentEmoji').textContent = x.state === 'CANDIDATE' ? '✊' : '☝';
    $('intentState').textContent = x.state === 'CANDIDATE' ? '检测到抓取意图' : x.state || '等待信号';
    $('intentHint').textContent = x.state === 'CANDIDATE' ? '正在等待脑机事件及机械臂确认' : '保持放松，尝试想象左手抓握';
    if (demo) { setConnection(true, '脑机接口：演示数据'); pill('armState', '演示无动作', 'neutral'); $('armDetail').textContent = '演示模式不会驱动机械臂'; }
    else setConnection(true, '脑机接口：已连接');
  }
  function onMiEvent(x) {
    if (!running) return;
    const id = eventId(x);
    if (handledEvents.has(id) || pendingEvents.has(id)) return;
    handledEvents.add(id);
    if (x.command && x.command !== 'LEFT_HAND_GRASP') return;
    if (x.simulated || x.mode === 'demo') {
      feedback('演示：已识别抓取意图，未执行机械臂', 'active');
      $('armDetail').textContent = '演示事件不会产生机械臂动作';
      pill('armState', '演示模式', 'neutral');
      return;
    }
    pendingEvents.add(id);
    feedback('检测到左手抓取意图，机械臂执行中…', 'active');
    $('armDetail').textContent = `执行事件 ${id}`;
    pill('armState', '执行中', 'waiting');
    $('intentState').textContent = '机械臂正在执行抓取';
  }
  function onArmStatus(x) {
    const id = x.event_id == null ? null : String(x.event_id);
    if (x.pose === 'home') return;
    if (id && !pendingEvents.has(id)) return;
    if (x.state === 'COMPLETED') {
      if (id) pendingEvents.delete(id);
      const index = remaining.keys().next().value;
      if (index !== undefined) {
        const apple = remaining.get(index);
        apple.style.setProperty('--dx', `${$('basket').offsetLeft - apple.offsetLeft + 45}px`);
        apple.style.setProperty('--dy', `${$('basket').offsetTop - apple.offsetTop + 28}px`);
        apple.classList.add('picked');
        window.setTimeout(() => apple.remove(), 700);
        remaining.delete(index);
      }
      picked += 1; $('pickedCount').textContent = picked;
      const mini = document.createElement('i'); mini.className = 'mini-apple'; $('basketApples').append(mini);
      feedback('机械臂抓取成功 · 苹果已入篮', 'active');
      $('armDetail').textContent = x.simulated ? '桥接已确认（模拟动作）' : '桥接已确认抓取完成';
      pill('armState', x.simulated ? '模拟成功' : '抓取成功', 'ok');
      $('intentState').textContent = '抓取成功';
    } else {
      if (id) pendingEvents.delete(id);
      const reason = x.reason || (x.state === 'BUSY' ? '机械臂正忙，请稍候' : `机械臂返回 ${x.state || '未知状态'}`);
      feedback(`机械臂抓取失败：${reason}`, 'error');
      $('armDetail').textContent = reason;
      pill('armState', x.state === 'ERROR' ? '动作失败' : (x.state || '失败'), 'bad');
      $('intentState').textContent = '机械臂未成功抓取';
    }
  }
  function onMessage(raw) {
    let x; try { x = JSON.parse(raw); } catch (_) { return; }
    if (x.type === 'status') {
      demo = x.mode === 'demo' || Boolean(x.simulated);
      setConnection(Boolean(x.lsl_connected) || demo, demo ? '脑机接口：演示模式' : (x.lsl_connected ? '脑机接口：已连接' : '等待脑电信号'));
      $('bciDetail').textContent = demo ? '接收模拟脑电数据' : (x.message || (x.lsl_connected ? 'LSL 已连接' : '等待 LSL 脑电流'));
      if (demo) { pill('armState', '演示无动作', 'neutral'); $('armDetail').textContent = '演示模式不会驱动机械臂'; }
    } else if (x.type === 'mi_telemetry') onTelemetry(x);
    else if (x.type === 'mi_event') onMiEvent(x);
    else if (x.type === 'arm_status') onArmStatus(x);
  }
  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.hostname || '127.0.0.1'}:8765`);
    ws.onopen = () => setConnection(true, demo ? '脑机接口：演示数据' : '脑机接口：已连接');
    ws.onmessage = e => onMessage(e.data);
    ws.onerror = () => setConnection(false, '无法连接脑机服务');
    ws.onclose = () => { setConnection(false, '脑机接口：连接已断开'); pill('armState', '服务离线', 'bad'); $('armDetail').textContent = '无法接收机械臂状态'; window.setTimeout(connect, 2500); };
  }
  $('startBtn').addEventListener('click', () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) { feedback('脑机服务未连接，请先启动服务', 'error'); return; }
    setRunning(true); feedback('请开始想象左手抓取苹果'); $('intentState').textContent = '等待左手抓取意图'; $('intentHint').textContent = '放松身体，只在脑中想象握住苹果';
    ws.send(JSON.stringify({ action: 'start' }));
  });
  $('stopBtn').addEventListener('click', () => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action: 'end' }));
    setRunning(false); feedback('采摘已暂停');
  });
  connect();
})();
