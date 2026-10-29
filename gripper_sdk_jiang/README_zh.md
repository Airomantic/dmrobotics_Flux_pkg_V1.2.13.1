# DM Robotics 夹爪 SDK

## 1. 项目功能

本项目用于控制 DM Robotics V3 夹爪，支持两种使用方式：

- `local`：程序直接运行在边缘设备上，通过 CAN-FD 控制夹爪。
- `remote`：上位机通过 gRPC 调用边缘设备，边缘设备再通过 CAN-FD 控制夹爪。

SDK 提供连接、断开、张开、闭合、停止、初始化、位置/速度/力设置、状态读取、错误解析、后台周期状态缓存等能力。

## 2. 通信架构

通信链路保持不变：

```text
PC / 上位机
    -> gRPC
边缘设备 / 服务端
    -> CAN-FD
夹爪
```

PC 不直接访问 CAN-FD。边缘设备负责 CAN-FD 初始化、指令串行化、状态缓存和异常处理。gRPC 服务端向 PC 暴露与本地 SDK 基本一致的控制接口。

## 3. CAN-FD 与 gRPC 的关系

CAN-FD 负责边缘设备到夹爪的实时控制。协议沿用 Modbus RTU 数据段格式，但去掉设备 ID 和 CRC：

- 读寄存器：功能码 `0x03`
- 写单寄存器：功能码 `0x06`
- 写多寄存器：功能码 `0x10`

标准帧 ID：

- 发送帧：`0x600 + motor_id`
- 反馈帧：`0x200 + motor_id`

推荐 CAN-FD 参数：

```bash
sudo ip link set can0 down
sudo ip link set can0 type can \
  bitrate 1000000 sample-point 0.80 \
  dbitrate 5000000 dsample-point 0.75 \
  fd on
sudo ip link set can0 up
```

gRPC 负责 PC 到边缘设备的远程调用。远程模式下，客户端调用 `Open()`、`Close()`、`Stop()`、`GetAllState()` 等方法，服务端会在本地执行对应 CAN-FD 操作。

## 4. 环境依赖与安装

Python 版本要求：`>=3.10`。

安装依赖：

```bash
cd gripper_sdk
pip install .
```

或：

```bash
pip install -r requirements.txt
```

主要依赖：

- `python-can`：local 模式访问 SocketCAN。
- `grpcio`：remote 模式和服务端 gRPC 通信。
- `grpcio-tools`：重新生成 proto 代码。
- `protobuf`：gRPC 消息序列化。

重新生成 gRPC 代码：

```bash
cd gripper_sdk
bash build.sh
```

## 5. 服务端启动

在边缘设备上配置 CAN-FD：

```bash
cd gripper_sdk
bash can_restart.sh
```

启动 gRPC 服务：

```bash
python server.py
```

默认监听端口：`50008`。

如果端口绑定失败，服务端会输出明确错误信息。请检查端口是否被占用、防火墙是否允许访问、边缘设备 IP 是否正确。

## 6. 客户端调用

远程控制示例：

```python
from dmgripper.gripper import Gripper

gripper = Gripper(
    mode="remote",
    remote_ip="192.168.127.10",
    remote_port=50008,
)

if not gripper.connect():
    print(gripper.GetLastError())
    raise SystemExit(1)

try:
    gripper.enable()
    gripper.Initialization()
    gripper.wait_until_initialized(timeout_s=10.0)

    gripper.SetTargetSpeed(50)
    gripper.SetTargetForce(60)
    gripper.Open(wait=True)
    gripper.Close(wait=True)
    gripper.Stop()

    state = gripper.GetAllState()
    print(state)
finally:
    gripper.disconnect()
```

本地控制示例：

```python
from dmgripper.gripper import Gripper

gripper = Gripper(mode="local", channel="can0", motor_id=1)

if gripper.connect():
    gripper.enable()
    gripper.Open()
    gripper.Close()
    gripper.disconnect()
```

## 7. 主要接口说明

连接与资源：

| 接口 | 说明 |
|---|---|
| `connect()` | 建立 local CAN-FD 连接或 remote gRPC 连接 |
| `disconnect()` | 断开连接并释放资源 |

基础控制：

| 接口 | 说明 |
|---|---|
| `enable()` | 系统使能 |
| `disable()` | 系统失能 |
| `Initialization()` / `initialize()` / `calibrate()` | 完整初始化和重新标定，写入 `0x0100 = 0xA5` |
| `home()` | 单向回零，写入 `0x0100 = 1` |
| `Open()` | 夹爪张开，默认目标位置 `1000` |
| `Close()` | 夹爪闭合，默认目标位置 `0` |
| `move_to(pos, speed=None, force=None)` | 按目标位置运动，可同时设置速度和力 |
| `Stop()` | 规划性停转，写入 `0x0502 = 1` |
| `Resume()` | 恢复停转前目标，写入 `0x0502 = 2` |
| `SetJog(direction)` | 点动控制，`-1` 反向，`0` 停止，`1` 正向 |
| `SetFollowMode(enabled)` | 开启或关闭位置跟随 |
| `Clear_error()` | 清除当前错误 |

参数设置：

| 接口 | 说明 |
|---|---|
| `SetTargetPosition(pos)` | 设置目标位置，范围 `0~1000` |
| `SetTargetSpeed(speed)` | 设置速度，范围 `1~100` |
| `SetTargetForce(force)` | 设置夹持力，范围 `20~100` |

状态读取：

| 接口 | 说明 |
|---|---|
| `GetAllState()` / `get_state()` | 返回最近一次有效状态缓存 |
| `refresh_state()` | 主动刷新一次状态 |
| `GetCurrentPosition()` | 当前反馈位置 |
| `GetInitState()` | 初始化状态 |
| `GetGripState()` | 夹持状态 |
| `GetCurrentSpeed()` | 当前反馈速度 |
| `GetCurrentCurrent()` | 当前电流反馈 |
| `GetCurrentForce()` | 兼容旧接口，当前返回电流反馈 |
| `GetErrorCode()` | 当前错误码 |
| `GetLastMessage()` | 最近一次操作消息 |
| `GetLastError()` | 最近一次错误消息 |

等待接口：

| 接口 | 说明 |
|---|---|
| `wait_until_initialized(timeout_s=10)` | 等待初始化完成 |
| `wait_until_position(target, tolerance=10, timeout_s=5)` | 等待到达目标位置 |

底层调试接口：

| 接口 | 说明 |
|---|---|
| `read_registers(start_addr, count=1)` | local 模式读取寄存器 |
| `write_register(reg_addr, value)` | local 模式写单寄存器 |
| `write_registers(start_addr, values)` | local 模式写多寄存器 |

## 8. 状态字段说明

`GetAllState()` 返回字典：

```python
{
    "valid": True,
    "connected": True,
    "stale": False,
    "message": "状态读取成功",
    "init_state": 1,
    "init_state_text": "初始化成功",
    "grip_state": 1,
    "grip_state_text": "到达位置",
    "position": 1000,
    "speed": 0,
    "current": 30,
    "error": 0,
    "error_text": "无错误",
    "update_age_ms": 12.3,
}
```

字段含义：

- `valid`：通信状态是否有效。错误码非 0 不代表 `valid=False`，它只表示夹爪自身有错误。
- `stale`：状态缓存是否过期。过期时说明夹爪长时间无响应。
- `update_age_ms`：状态缓存距离当前的时间。
- `current`：内部电机电流反馈，不是电源实际消耗电流。

## 9. 错误码与状态码

初始化状态：

| 数值 | 含义 |
|---:|---|
| `0` | 未初始化 |
| `1` | 初始化成功 |
| `2` | 初始化中 |
| `0xFFFF` | 行程标定异常 |

夹持状态：

| 数值 | 含义 |
|---:|---|
| `0` | 运动中 |
| `1` | 到达位置 |
| `2` | 夹住物体 |
| `3` | 物体掉落 |
| `0xFFFF` | 初始化未完成 |

错误码：

| 数值 | 含义 |
|---:|---|
| `0` | 无错误 |
| `1` | 欠压，低于 15V |
| `2` | 超压，高于 28V |
| `3` | 过流 |
| `4` | 过热 |
| `5` | 电机断线 |
| `8` | 过载 |
| `11` | 过速 |
| `15` | 启动异常 |
| `32` | 磁编异常 |

## 10. 稳定性设计

SDK 做了以下保护：

- 后台线程周期性读取状态，普通状态接口优先返回缓存，避免阻塞控制流程。
- CAN-FD 读写统一入口，带超时、重试和返回帧完整性校验。
- 控制指令通过写锁串行化，避免边缘设备内部多线程或多个 gRPC 请求导致指令乱序。
- 重复相同指令会按 `command_min_interval_s` 限频。
- 夹爪长时间无响应时，状态会标记为 `valid=False`、`stale=True`，并返回明确消息。
- `disconnect()` 可重复调用，程序退出时会停止状态线程并释放 CAN-FD/gRPC 资源。

## 11. 常见问题

### 连接失败

检查：

- `can0` 是否存在：`ip -details link show can0`
- 是否已启用 CAN-FD：`bash can_restart.sh`
- 夹爪供电和 CAN_H/CAN_L 是否正常
- `motor_id` 是否正确
- 边缘设备是否有权限访问 SocketCAN

### gRPC 连接失败

检查：

- 服务端是否已运行：`python server.py`
- 服务端端口是否为 `50008`
- PC 能否 ping 通边缘设备 IP
- 防火墙是否阻止端口访问

### `Open()` 或 `Close()` 返回失败

常见原因：

- 夹爪未初始化，先调用 `Initialization()` 并等待 `wait_until_initialized()`
- 当前状态缓存过期，检查 `GetAllState()["message"]`
- 夹爪存在错误码，先查看 `GetErrorCode()` 和 `error_text`

### 状态一直过期

说明边缘设备到夹爪的 CAN-FD 读取失败。检查 CAN-FD 配置、接线、终端电阻和夹爪供电。

## 12. 验证

语法和单元测试：

```bash
cd gripper_sdk
python -m compileall dmgripper server.py test_demo.py cycle_position_frequency_test.py
python -m unittest discover -s tests
```
