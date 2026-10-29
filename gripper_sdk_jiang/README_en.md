# DM Robotics Gripper SDK

## 1. Overview

This SDK controls the DM Robotics V3 gripper in two modes:

- `local`: run on the edge device and control the gripper through CAN-FD.
- `remote`: run on a PC and call the edge device through gRPC. The edge device then controls the gripper through CAN-FD.

The SDK provides connection management, open, close, stop, initialization, position/speed/force commands, cached state reading, error decoding, timeout handling, retries, and safe resource cleanup.

## 2. Communication Architecture

The communication path remains unchanged:

```text
PC / host
    -> gRPC
edge device / server
    -> CAN-FD
gripper
```

The PC never talks to CAN-FD directly. The edge device owns CAN-FD access, command serialization, state polling, state caching, and error handling.

## 3. CAN-FD and gRPC

The CAN-FD payload follows a Modbus RTU-like register protocol without Modbus ID and CRC:

- Read registers: function code `0x03`
- Write single register: function code `0x06`
- Write multiple registers: function code `0x10`

Standard CAN-FD frame IDs:

- Command frame: `0x600 + motor_id`
- Feedback frame: `0x200 + motor_id`

Recommended CAN-FD settings:

```bash
sudo ip link set can0 down
sudo ip link set can0 type can \
  bitrate 1000000 sample-point 0.80 \
  dbitrate 5000000 dsample-point 0.75 \
  fd on
sudo ip link set can0 up
```

gRPC exposes the same high-level control semantics to the PC. A remote client can call `Open()`, `Close()`, `Stop()`, and `GetAllState()` as if it were using a local gripper object.

## 4. Installation

Python requirement: `>=3.10`.

Install the package:

```bash
cd gripper_sdk
pip install .
```

Or install dependencies directly:

```bash
pip install -r requirements.txt
```

Main dependencies:

- `python-can` for SocketCAN access in local mode.
- `grpcio` for gRPC communication.
- `grpcio-tools` for regenerating protobuf code.
- `protobuf` for message serialization.

Regenerate gRPC code:

```bash
cd gripper_sdk
bash build.sh
```

## 5. Start the Server

Run this on the edge device:

```bash
cd gripper_sdk
bash can_restart.sh
python server.py
```

The default gRPC port is `50008`.

If startup fails, check whether the port is already in use, whether the CAN-FD interface exists, and whether the process has enough permission to access SocketCAN.

## 6. Client Example

Remote mode:

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

    print(gripper.GetAllState())
finally:
    gripper.disconnect()
```

Local mode:

```python
from dmgripper.gripper import Gripper

gripper = Gripper(mode="local", channel="can0", motor_id=1)

if gripper.connect():
    gripper.enable()
    gripper.Open()
    gripper.Close()
    gripper.disconnect()
```

## 7. API Reference

Connection:

| API | Description |
|---|---|
| `connect()` | Connect to the local gripper or remote server |
| `disconnect()` | Disconnect and release resources |

Control:

| API | Description |
|---|---|
| `enable()` | Enable gripper control |
| `disable()` | Disable gripper control |
| `Initialization()` / `initialize()` / `calibrate()` | Full calibration and initialization, writes `0x0100 = 0xA5` |
| `home()` | One-direction homing, writes `0x0100 = 1` |
| `Open()` | Open the gripper, default target position `1000` |
| `Close()` | Close the gripper, default target position `0` |
| `move_to(pos, speed=None, force=None)` | Move to a target position, optionally setting speed and force first |
| `Stop()` | Planned stop, writes `0x0502 = 1` |
| `Resume()` | Resume the target before planned stop, writes `0x0502 = 2` |
| `SetJog(direction)` | Jog control. `-1` reverse, `0` stop, `1` forward |
| `SetFollowMode(enabled)` | Enable or disable position-follow mode |
| `Clear_error()` | Clear the current error |

Parameters:

| API | Range |
|---|---|
| `SetTargetPosition(pos)` | `0~1000` |
| `SetTargetSpeed(speed)` | `1~100` |
| `SetTargetForce(force)` | `20~100` |

State:

| API | Description |
|---|---|
| `GetAllState()` / `get_state()` | Return the latest cached state |
| `refresh_state()` | Force one state refresh |
| `GetCurrentPosition()` | Feedback position |
| `GetInitState()` | Initialization state |
| `GetGripState()` | Grip state |
| `GetCurrentSpeed()` | Feedback speed |
| `GetCurrentCurrent()` | Motor current feedback |
| `GetCurrentForce()` | Compatibility API. It currently returns motor current feedback |
| `GetErrorCode()` | Current error code |
| `GetLastMessage()` | Last operation message |
| `GetLastError()` | Last error message |

Wait helpers:

| API | Description |
|---|---|
| `wait_until_initialized(timeout_s=10)` | Wait until initialization succeeds |
| `wait_until_position(target, tolerance=10, timeout_s=5)` | Wait until the target position is reached |

Low-level local debug APIs:

| API | Description |
|---|---|
| `read_registers(start_addr, count=1)` | Read registers in local mode |
| `write_register(reg_addr, value)` | Write one register in local mode |
| `write_registers(start_addr, values)` | Write multiple registers in local mode |

## 8. State Fields

`GetAllState()` returns a dictionary:

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

Notes:

- `valid` describes communication freshness, not whether the gripper has an internal error.
- `stale=True` means the cached state has not been updated for too long.
- `current` is the internal motor current feedback. It is not the actual power-supply current.

## 9. Status and Error Codes

Initialization state:

| Value | Meaning |
|---:|---|
| `0` | Not initialized |
| `1` | Initialization succeeded |
| `2` | Initializing |
| `0xFFFF` | Travel calibration error |

Grip state:

| Value | Meaning |
|---:|---|
| `0` | Moving |
| `1` | Reached target |
| `2` | Object gripped |
| `3` | Object dropped |
| `0xFFFF` | Not initialized |

Error code:

| Value | Meaning |
|---:|---|
| `0` | No error |
| `1` | Undervoltage, below 15V |
| `2` | Overvoltage, above 28V |
| `3` | Overcurrent |
| `4` | Overtemperature |
| `5` | Motor disconnected |
| `8` | Overload |
| `11` | Overspeed |
| `15` | Startup error |
| `32` | Magnetic encoder error |

## 10. Robustness Design

- A background thread periodically reads the gripper state in local mode.
- Normal state APIs return the latest cache first, avoiding blocking control flows.
- CAN-FD read/write operations use a unified transaction path with timeout, retry, and frame validation.
- Control commands are serialized with a software lock, preventing command disorder from multiple threads or concurrent gRPC requests.
- Repeated identical commands are rate-limited by `command_min_interval_s`.
- Long no-response periods are reported as `valid=False` and `stale=True` instead of hanging.
- `disconnect()` is idempotent and releases CAN-FD or gRPC resources safely.

## 11. Troubleshooting

Connection failure:

- Check `ip -details link show can0`.
- Run `bash can_restart.sh`.
- Check gripper power and CAN_H/CAN_L wiring.
- Check `motor_id`.
- Check SocketCAN permissions.

gRPC failure:

- Confirm `python server.py` is running on the edge device.
- Confirm port `50008`.
- Check network reachability and firewall rules.

`Open()` or `Close()` fails:

- Initialize first with `Initialization()` and `wait_until_initialized()`.
- Check `GetAllState()["message"]`.
- Check `GetErrorCode()` and `error_text`.

State is always stale:

- The edge device is not receiving valid CAN-FD feedback from the gripper. Check CAN-FD settings, wiring, termination, and power.

## 12. Verification

```bash
cd gripper_sdk
python -m compileall dmgripper server.py test_demo.py cycle_position_frequency_test.py
python -m unittest discover -s tests
```
