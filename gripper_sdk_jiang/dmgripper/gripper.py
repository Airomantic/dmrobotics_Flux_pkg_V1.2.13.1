import threading
import time
from typing import Dict, List, Optional

try:
    import can
except ImportError:
    can = None

try:
    import grpc
    from google.protobuf import empty_pb2
    from . import gripper_pb2
    from . import gripper_pb2_grpc
except ImportError:
    grpc = None
    empty_pb2 = None
    gripper_pb2 = None
    gripper_pb2_grpc = None


class Reg:
    INIT_ACTION = 0x0100
    SET_FORCE = 0x0101
    TARGET_POS = 0x0103
    SET_SPEED = 0x0104
    JOG_MODE = 0x010A
    FB_INIT_STATE = 0x0200
    FB_GRIP_STATE = 0x0201
    FB_POS = 0x0202
    FB_SPEED = 0x0203
    FB_CURRENT = 0x0204
    FB_ERROR = 0x0205
    FB_RESET_STATE = 0x0206
    FB_ENCODER_STATE = 0x020E
    FB_MOTOR_TEMP = 0x020F
    DIR_SWITCH = 0x0500
    UNIT_SWITCH = 0x0501
    STOP_NOW = 0x0502
    CLEAR_ERR = 0x0503
    FOLLOW_MODE = 0x0508
    SYS_ENABLE = 0x050F
    BUS_VOLTAGE = 0x0600


INIT_STATE_TEXT = {
    0: "not initialized",
    1: "initialized",
    2: "initializing",
    0xFFFF: "travel calibration error",
}

GRIP_STATE_TEXT = {
    0: "moving",
    1: "target reached",
    2: "object gripped",
    3: "object dropped",
    0xFFFF: "initialization incomplete",
}

ERROR_TEXT = {
    0: "no error",
    1: "undervoltage, below 15V",
    2: "overvoltage, above 28V",
    3: "overcurrent",
    4: "overtemperature",
    5: "motor disconnected",
    8: "overload",
    11: "overspeed",
    15: "startup error",
    32: "magnetic encoder error",
}


def _clip(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, int(value)))


def _to_u16(value: int) -> int:
    return int(value) & 0xFFFF


class Gripper:
    def __init__(
        self,
        mode="local",
        channel="can0",
        motor_id=1,
        remote_ip="192.168.127.10",
        remote_port=50008,
        read_interval_s=0.05,
        read_timeout_s=0.1,
        retry_count=2,
        stale_timeout_s=0.5,
        command_min_interval_s=0.02,
        open_position=1000,
        close_position=0,
        strict_init_check=True,
    ):
        """
        :param mode: local uses CAN-FD directly; remote talks to the edge device through gRPC
        :param channel: SocketCAN channel used in local mode
        :param motor_id: gripper motor ID
        :param remote_ip: server IP used in remote mode
        :param remote_port: server port used in remote mode
        :param read_interval_s: background status polling interval
        :param read_timeout_s: timeout for one CAN-FD response
        :param retry_count: retry count after read/write failure
        :param stale_timeout_s: mark cached status stale after this interval
        :param command_min_interval_s: minimum interval for repeated same-register commands
        :param strict_init_check: require initialization before motion and jog commands
        """
        if mode not in ("local", "remote"):
            raise ValueError("mode must be 'local' or 'remote'")

        self.mode = mode
        self.motor_id = int(motor_id)
        self.channel = channel
        self.read_interval_s = max(0.005, float(read_interval_s))
        self.read_timeout_s = max(0.005, float(read_timeout_s))
        self.retry_count = max(0, int(retry_count))
        self.stale_timeout_s = max(self.read_interval_s, float(stale_timeout_s))
        self.command_min_interval_s = max(0.0, float(command_min_interval_s))
        self.open_position = _clip(open_position, 0, 1000)
        self.close_position = _clip(close_position, 0, 1000)
        self.strict_init_check = bool(strict_init_check)

        self._connected = False
        self._last_error = ""
        self._last_message = ""
        self._last_send_times: Dict[tuple, float] = {}
        self._io_lock = threading.RLock()
        self._command_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._state_cache = self._empty_state("no gripper status has been read yet")

        if self.mode == "local":
            if can is None:
                raise ImportError("local mode requires python-can")
            self.tx_id = 0x600 + self.motor_id
            self.rx_id = 0x200 + self.motor_id
            self.bus = None
            self._status_stop = threading.Event()
            self._status_thread = None
        else:
            if grpc is None or gripper_pb2 is None or gripper_pb2_grpc is None:
                raise ImportError("remote mode requires grpcio, protobuf, and generated gRPC code")
            self.remote_addr = f"{remote_ip}:{int(remote_port)}"
            self.grpc_channel = grpc.insecure_channel(self.remote_addr)
            self.stub = gripper_pb2_grpc.GripperServiceStub(self.grpc_channel)

    # ================= Connection and resource management =================

    def connect(self) -> bool:
        """Open the local CAN-FD connection or the remote gRPC connection."""
        if self.mode == "local":
            return self._connect_local()
        return self._connect_remote()

    def disconnect(self) -> bool:
        """Disconnect and release CAN-FD or gRPC resources."""
        if self.mode == "local":
            return self._disconnect_local()
        return self._disconnect_remote()

    def _connect_local(self) -> bool:
        if self._connected and self.bus is not None:
            self._set_command_result(True, "gripper is already connected")
            return True

        try:
            if self.bus is None:
                self.bus = can.Bus(channel=self.channel, interface="socketcan", fd=True)
        except OSError as exc:
            return self._fail(f"CAN-FD interface initialization failed: {exc}")
        except Exception as exc:
            return self._fail(f"CAN-FD initialization error: {exc}")

        values = self._read_registers_raw(Reg.FB_INIT_STATE, 6)
        if values is None:
            self._disconnect_local()
            return self._fail(f"gripper ID {self.motor_id} has no response; check power, CAN-FD wiring, and interface settings")

        self._connected = True
        self._update_state_from_feedback(values, "connected and initial status read")
        self._start_status_reader()
        self._set_command_result(True, f"local gripper ID {self.motor_id} connected")
        print(f"local gripper ID {self.motor_id} connected.")
        return True

    def _connect_remote(self) -> bool:
        if self._connected:
            self._set_command_result(True, "remote gripper is already connected")
            return True

        try:
            self.grpc_channel = grpc.insecure_channel(self.remote_addr)
            self.stub = gripper_pb2_grpc.GripperServiceStub(self.grpc_channel)
            grpc.channel_ready_future(self.grpc_channel).result(timeout=3)
            req = gripper_pb2.ConnectConfig(
                channel=self.channel,
                motor_id=self.motor_id,
                read_interval_s=self.read_interval_s,
                read_timeout_s=self.read_timeout_s,
                retry_count=self.retry_count,
                stale_timeout_s=self.stale_timeout_s,
                command_min_interval_s=self.command_min_interval_s,
            )
            resp = self.stub.Connect(req, timeout=5)
            self._apply_response(resp)
            self._connected = bool(resp.success)
            if resp.success:
                print(f"remote gripper {self.remote_addr} connected.")
            else:
                print(f"remote gripper connection failed: {resp.message}")
            return bool(resp.success)
        except grpc.RpcError as exc:
            return self._fail(f"gRPC connection failed: {exc}")
        except Exception as exc:
            return self._fail(f"remote connection error: {exc}")

    def _disconnect_local(self) -> bool:
        with self._command_lock:
            self._status_stop.set()
            thread = self._status_thread
            if thread is not None and thread.is_alive():
                thread.join(timeout=max(1.0, self.read_timeout_s * 2))
            self._status_thread = None

            try:
                if self.bus is not None:
                    self.bus.shutdown()
            except Exception as exc:
                self._set_command_result(False, f"error while releasing CAN-FD resources: {exc}")
                self.bus = None
                self._connected = False
                return False

            self.bus = None
            self._connected = False
            self._state_cache = self._empty_state("connection disconnected")
            self._set_command_result(True, "connection disconnected")
            return True

    def _disconnect_remote(self) -> bool:
        if not self._connected:
            try:
                self.grpc_channel.close()
            except Exception:
                pass
            self._set_command_result(True, "connection disconnected")
            return True

        ok = True
        try:
            resp = self.stub.Disconnect(empty_pb2.Empty(), timeout=3)
            self._apply_response(resp)
            ok = bool(resp.success)
        except grpc.RpcError as exc:
            ok = False
            self._fail(f"remote disconnect failed: {exc}")
        except Exception as exc:
            ok = False
            self._fail(f"remote disconnect error: {exc}")
        finally:
            try:
                self.grpc_channel.close()
            except Exception:
                pass
            self._connected = False
        return ok

    # ================= CAN-FD read/write transactions =================

    def _start_status_reader(self):
        self._status_stop.clear()
        self._status_thread = threading.Thread(
            target=self._status_loop,
            name=f"gripper-{self.motor_id}-status",
            daemon=True,
        )
        self._status_thread.start()

    def _status_loop(self):
        while not self._status_stop.wait(self.read_interval_s):
            self.refresh_state()

    def _ensure_local_ready(self) -> bool:
        if self.mode != "local":
            return self._fail("this operation is only available in local mode")
        if not self._connected or self.bus is None:
            return self._fail("gripper is not connected; CAN-FD command cannot be executed")
        return True

    def _make_msg(self, payload: List[int]):
        return can.Message(
            arbitration_id=self.tx_id,
            data=[_to_u16(v) & 0xFF for v in payload],
            is_fd=True,
            bitrate_switch=True,
            is_extended_id=False,
        )

    def _recv_until(self, predicate, timeout_s: float):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            remain = deadline - time.monotonic()
            if remain <= 0:
                break
            resp = self.bus.recv(remain)
            if resp is None:
                continue
            if predicate(resp):
                return resp
        return None

    def _read_registers_raw(self, start_addr: int, count: int) -> Optional[List[int]]:
        if self.bus is None:
            self._fail("CAN-FD bus is not initialized")
            return None
        if count <= 0:
            self._fail("register read count must be greater than 0")
            return None

        payload = [
            0x03,
            (start_addr >> 8) & 0xFF,
            start_addr & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF,
        ]
        expected_bytes = count * 2

        def expected(resp):
            data = list(resp.data)
            return (
                resp.arbitration_id == self.rx_id
                and len(data) >= expected_bytes + 2
                and data[0] == 0x03
                and data[1] == expected_bytes
            )

        with self._io_lock:
            for attempt in range(self.retry_count + 1):
                try:
                    self.bus.send(self._make_msg(payload))
                    resp = self._recv_until(expected, self.read_timeout_s)
                    if resp is not None:
                        data = list(resp.data)
                        values = []
                        for i in range(count):
                            idx = 2 + i * 2
                            values.append((data[idx] << 8) | data[idx + 1])
                        return values
                except can.CanError as exc:
                    self._last_error = f"CAN-FD read failed: {exc}"
                except Exception as exc:
                    self._last_error = f"register read error: {exc}"
                if attempt < self.retry_count:
                    time.sleep(0.002)

        self._last_error = f"reading register 0x{start_addr:04X} timed out or returned an invalid frame"
        return None

    def _write_register_raw(self, reg_addr: int, value: int) -> bool:
        if self.bus is None:
            return self._fail("CAN-FD bus is not initialized")

        value_u16 = _to_u16(value)
        payload = [
            0x06,
            (reg_addr >> 8) & 0xFF,
            reg_addr & 0xFF,
            (value_u16 >> 8) & 0xFF,
            value_u16 & 0xFF,
        ]

        def expected(resp):
            data = list(resp.data)
            return (
                resp.arbitration_id == self.rx_id
                and len(data) >= 5
                and data[:5] == payload
            )

        with self._io_lock:
            for attempt in range(self.retry_count + 1):
                try:
                    self.bus.send(self._make_msg(payload))
                    if self._recv_until(expected, self.read_timeout_s) is not None:
                        return True
                except can.CanError as exc:
                    self._last_error = f"CAN-FD write failed: {exc}"
                except Exception as exc:
                    self._last_error = f"register write error: {exc}"
                if attempt < self.retry_count:
                    time.sleep(0.002)

        self._last_error = f"writing register 0x{reg_addr:04X}=0x{value_u16:04X} timed out or returned an invalid frame"
        return False

    def _write_registers_raw(self, start_addr: int, values: List[int]) -> bool:
        if self.bus is None:
            return self._fail("CAN-FD bus is not initialized")
        if not values:
            return self._fail("values for multi-register write cannot be empty")
        if len(values) > 29:
            return self._fail("a CAN-FD standard-frame payload supports at most 29 registers per write")

        count = len(values)
        payload = [
            0x10,
            (start_addr >> 8) & 0xFF,
            start_addr & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF,
            count * 2,
        ]
        for value in values:
            value_u16 = _to_u16(value)
            payload.extend([(value_u16 >> 8) & 0xFF, value_u16 & 0xFF])

        expected_prefix = [
            0x10,
            (start_addr >> 8) & 0xFF,
            start_addr & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF,
        ]

        def expected(resp):
            data = list(resp.data)
            return (
                resp.arbitration_id == self.rx_id
                and len(data) >= 5
                and data[:5] == expected_prefix
            )

        with self._io_lock:
            for attempt in range(self.retry_count + 1):
                try:
                    self.bus.send(self._make_msg(payload))
                    if self._recv_until(expected, self.read_timeout_s) is not None:
                        return True
                except can.CanError as exc:
                    self._last_error = f"CAN-FD multi-register write failed: {exc}"
                except Exception as exc:
                    self._last_error = f"multi-register write error: {exc}"
                if attempt < self.retry_count:
                    time.sleep(0.002)

        self._last_error = f"writing {count} registers from 0x{start_addr:04X} timed out or returned an invalid frame"
        return False

    def _execute_write(
        self,
        reg_addr: int,
        value: int,
        action_name: str,
        require_initialized: bool = False,
        allow_rate_limit: bool = True,
    ) -> bool:
        if not self._ensure_local_ready():
            return False

        with self._command_lock:
            if require_initialized and self.strict_init_check and not self.is_initialized():
                return self._fail(f"{action_name} failed: gripper is not initialized or status is stale")

            value_u16 = _to_u16(value)
            key = (reg_addr, value_u16)
            now = time.monotonic()
            last_send = self._last_send_times.get(key, 0.0)
            if allow_rate_limit and now - last_send < self.command_min_interval_s:
                self._set_command_result(True, f"{action_name} is rate limited; duplicate command skipped")
                return True

            ok = self._write_register_raw(reg_addr, value)
            if ok:
                self._last_send_times[key] = time.monotonic()
                self._set_command_result(True, f"{action_name} command sent")
                return True
            return self._fail(f"{action_name} command failed: {self._last_error}")

    # ================= Status cache and decoding =================

    def _empty_state(self, message: str) -> Dict[str, object]:
        return {
            "valid": False,
            "connected": False,
            "stale": True,
            "message": message,
            "init_state": -1,
            "init_state_text": "unknown",
            "grip_state": -1,
            "grip_state_text": "unknown",
            "position": -1,
            "speed": -1,
            "current": -1,
            "error": -1,
            "error_text": "unknown",
            "timestamp": 0.0,
            "update_age_ms": -1.0,
        }

    def _update_state_from_feedback(self, values: List[int], message: str = "status read successfully"):
        if len(values) < 6:
            self._mark_state_error("insufficient feedback register count")
            return

        error = values[5]
        state = {
            "valid": True,
            "connected": self._connected,
            "stale": False,
            "message": message if error == 0 else self.decode_error(error),
            "init_state": values[0],
            "init_state_text": self.decode_init_state(values[0]),
            "grip_state": values[1],
            "grip_state_text": self.decode_grip_state(values[1]),
            "position": values[2],
            "speed": values[3],
            "current": values[4],
            "error": error,
            "error_text": self.decode_error(error),
            "timestamp": time.monotonic(),
            "update_age_ms": 0.0,
        }
        with self._state_lock:
            self._state_cache = state

    def _mark_state_error(self, message: str):
        with self._state_lock:
            if self._state_cache["timestamp"] == 0.0:
                self._state_cache = self._empty_state(message)
            else:
                self._state_cache["message"] = message
        self._last_error = message

    def _snapshot_state(self) -> Dict[str, object]:
        with self._state_lock:
            state = dict(self._state_cache)

        timestamp = float(state.get("timestamp", 0.0))
        if timestamp > 0.0:
            age = time.monotonic() - timestamp
            stale = age > self.stale_timeout_s
            state["update_age_ms"] = age * 1000.0
            state["stale"] = stale
            state["valid"] = bool(state.get("valid")) and not stale
            state["connected"] = self._connected
            if stale:
                state["message"] = f"status has not been updated for {self.stale_timeout_s:.3f}s; gripper may be unresponsive"
        else:
            state["update_age_ms"] = -1.0
            state["stale"] = True
            state["valid"] = False
            state["connected"] = self._connected
        return state

    def refresh_state(self) -> bool:
        """Refresh status once; normal read APIs return the cached status first."""
        if self.mode == "remote":
            if not self._connected:
                self._mark_state_error("remote gripper is not connected; status cannot be refreshed")
                return False
            try:
                resp = self.stub.GetAllState(empty_pb2.Empty(), timeout=2)
                self._update_state_from_response(resp)
                return bool(resp.valid)
            except grpc.RpcError as exc:
                self._mark_state_error(f"remote status read failed: {exc}")
                return False

        if not self._connected or self.bus is None:
            self._mark_state_error("gripper is not connected; status cannot be refreshed")
            return False

        values = self._read_registers_raw(Reg.FB_INIT_STATE, 6)
        if values is None:
            self._mark_state_error(self._last_error or "gripper status read failed")
            return False
        self._update_state_from_feedback(values)
        return True

    def get_state(self) -> Dict[str, object]:
        if self.mode == "remote":
            self.refresh_state()
        return self._snapshot_state()

    def GetAllState(self) -> dict:
        return self.get_state()

    @staticmethod
    def decode_init_state(value: int) -> str:
        return INIT_STATE_TEXT.get(int(value), f"unknown init state {value}")

    @staticmethod
    def decode_grip_state(value: int) -> str:
        return GRIP_STATE_TEXT.get(int(value), f"unknown grip state {value}")

    @staticmethod
    def decode_error(value: int) -> str:
        return ERROR_TEXT.get(int(value), f"unknown error code {value}")

    def is_initialized(self) -> bool:
        state = self.get_state()
        return bool(state.get("valid")) and state.get("init_state") == 1

    def is_moving(self) -> bool:
        state = self.get_state()
        return bool(state.get("valid")) and state.get("grip_state") == 0

    def has_error(self) -> bool:
        state = self.get_state()
        return int(state.get("error", -1)) not in (0, -1)

    def wait_until_initialized(self, timeout_s: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.is_initialized():
                return True
            if self.mode == "local":
                self.refresh_state()
            time.sleep(min(0.05, self.read_interval_s))
        self._fail("waiting for initialization timed out")
        return False

    def wait_until_position(self, target: int, tolerance: int = 10, timeout_s: float = 5.0) -> bool:
        target = _clip(target, 0, 1000)
        tolerance = max(0, int(tolerance))
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            state = self.get_state()
            pos = int(state.get("position", -1))
            if bool(state.get("valid")) and pos >= 0 and abs(pos - target) <= tolerance:
                self._set_command_result(True, "gripper reached target position")
                return True
            time.sleep(min(0.05, self.read_interval_s))
        self._fail(f"waiting for gripper to reach position {target} timed out")
        return False

    # ================= Public control API =================

    def enable(self) -> bool:
        if self.mode == "remote":
            return self._remote_bool_call("Enable")
        return self._execute_write(Reg.SYS_ENABLE, 1, "enable", require_initialized=False)

    def disable(self) -> bool:
        if self.mode == "remote":
            return self._remote_bool_call("Disable")
        return self._execute_write(Reg.SYS_ENABLE, 0, "disable", require_initialized=False)

    def Initialization(self) -> bool:
        """Compatibility API: run full calibration and initialization."""
        return self.calibrate()

    def initialize(self) -> bool:
        return self.calibrate()

    def calibrate(self) -> bool:
        if self.mode == "remote":
            return self._remote_bool_call("Initialization")
        return self._execute_write(Reg.INIT_ACTION, 0xA5, "full initialization", require_initialized=False, allow_rate_limit=False)

    def home(self) -> bool:
        if self.mode == "remote":
            return self._remote_bool_call("Home")
        return self._execute_write(Reg.INIT_ACTION, 1, "one-direction homing", require_initialized=False, allow_rate_limit=False)

    def SetTargetPosition(self, pos: int) -> bool:
        if self.mode == "remote":
            pos = _clip(pos, 0, 1000)
            return self._remote_value_call("SetTargetPosition", pos)
        pos = _clip(pos, 0, 1000)
        return self._execute_write(Reg.TARGET_POS, pos, f"move to position {pos}", require_initialized=True)

    def SetTargetForce(self, force: int) -> bool:
        if self.mode == "remote":
            force = _clip(force, 20, 100)
            return self._remote_value_call("SetTargetForce", force)
        force = _clip(force, 20, 100)
        return self._execute_write(Reg.SET_FORCE, force, f"set grip force {force}", require_initialized=False)

    def SetTargetSpeed(self, speed: int) -> bool:
        if self.mode == "remote":
            speed = _clip(speed, 1, 100)
            return self._remote_value_call("SetTargetSpeed", speed)
        speed = _clip(speed, 1, 100)
        return self._execute_write(Reg.SET_SPEED, speed, f"set speed {speed}", require_initialized=False)

    def move_to(
        self,
        pos: int,
        speed: Optional[int] = None,
        force: Optional[int] = None,
        wait: bool = False,
        timeout_s: float = 5.0,
        tolerance: int = 10,
    ) -> bool:
        pos = _clip(pos, 0, 1000)
        with self._command_lock:
            if speed is not None and not self.SetTargetSpeed(speed):
                return False
            if force is not None and not self.SetTargetForce(force):
                return False
            if not self.SetTargetPosition(pos):
                return False
        if wait:
            return self.wait_until_position(pos, tolerance=tolerance, timeout_s=timeout_s)
        return True

    def Open(self, wait: bool = False, timeout_s: float = 5.0) -> bool:
        if self.mode == "remote":
            ok = self._remote_bool_call("Open")
            if ok and wait:
                return self.wait_until_position(self.open_position, timeout_s=timeout_s)
            return ok
        return self.move_to(self.open_position, wait=wait, timeout_s=timeout_s)

    def Close(self, wait: bool = False, timeout_s: float = 5.0) -> bool:
        """Close the gripper. Use disconnect to release resources."""
        if self.mode == "remote":
            ok = self._remote_bool_call("Close")
            if ok and wait:
                return self.wait_until_position(self.close_position, timeout_s=timeout_s)
            return ok
        return self.move_to(self.close_position, wait=wait, timeout_s=timeout_s)

    def Stop(self) -> bool:
        if self.mode == "remote":
            return self._remote_bool_call("Stop")
        return self._execute_write(Reg.STOP_NOW, 1, "planned stop", require_initialized=False, allow_rate_limit=False)

    def Resume(self) -> bool:
        if self.mode == "remote":
            return self._remote_bool_call("Resume")
        return self._execute_write(Reg.STOP_NOW, 2, "resume previous target", require_initialized=False, allow_rate_limit=False)

    def Clear_error(self) -> bool:
        if self.mode == "remote":
            return self._remote_bool_call("ClearError")
        return self._execute_write(Reg.CLEAR_ERR, 1, "clear error", require_initialized=False, allow_rate_limit=False)

    def SetJog(self, direction: int) -> bool:
        direction = int(direction)
        if direction not in (-1, 0, 1):
            return self._fail("jog direction must be -1, 0, or 1")
        if self.mode == "remote":
            return self._remote_value_call("SetJog", direction)
        return self._execute_write(Reg.JOG_MODE, direction, f"jog {direction}", require_initialized=True)

    def SetFollowMode(self, enabled: bool) -> bool:
        value = 1 if enabled else 0
        if self.mode == "remote":
            return self._remote_value_call("SetFollowMode", value)
        return self._execute_write(Reg.FOLLOW_MODE, value, "set position-follow mode", require_initialized=False)

    # ================= Status compatibility API =================

    def GetCurrentPosition(self) -> int:
        return int(self.get_state().get("position", -1))

    def GetInitState(self) -> int:
        return int(self.get_state().get("init_state", -1))

    def GetGripState(self) -> int:
        return int(self.get_state().get("grip_state", -1))

    def GetCurrentSpeed(self) -> int:
        return int(self.get_state().get("speed", -1))

    def GetCurrentCurrent(self) -> int:
        return int(self.get_state().get("current", -1))

    def GetCurrentForce(self) -> int:
        """Compatibility API: returns motor current because no force feedback register exists."""
        return self.GetCurrentCurrent()

    def GetErrorCode(self) -> int:
        return int(self.get_state().get("error", -1))

    def GetLastMessage(self) -> str:
        return self._last_message

    def GetLastError(self) -> str:
        return self._last_error

    def read_registers(self, start_addr: int, count: int = 1) -> Optional[List[int]]:
        if not self._ensure_local_ready():
            return None
        return self._read_registers_raw(start_addr, count)

    def write_register(self, reg_addr: int, value: int) -> bool:
        return self._execute_write(reg_addr, value, f"write register 0x{reg_addr:04X}", require_initialized=False)

    def write_registers(self, start_addr: int, values: List[int]) -> bool:
        if not self._ensure_local_ready():
            return False
        with self._command_lock:
            ok = self._write_registers_raw(start_addr, values)
            if ok:
                self._set_command_result(True, f"write multiple registers from 0x{start_addr:04X} succeeded")
                return True
            return self._fail(f"multi-register write failed: {self._last_error}")

    # ================= gRPC helper logic =================

    def _remote_bool_call(self, rpc_name: str) -> bool:
        if not self._connected:
            return self._fail("remote gripper is not connected")
        try:
            rpc = getattr(self.stub, rpc_name)
            resp = rpc(empty_pb2.Empty(), timeout=5)
            return self._apply_response(resp)
        except grpc.RpcError as exc:
            return self._fail(f"remote call {rpc_name} failed: {exc}")
        except Exception as exc:
            return self._fail(f"remote call {rpc_name} error: {exc}")

    def _remote_value_call(self, rpc_name: str, value: int) -> bool:
        if not self._connected:
            return self._fail("remote gripper is not connected")
        try:
            rpc = getattr(self.stub, rpc_name)
            resp = rpc(gripper_pb2.ValueRequest(value=int(value)), timeout=5)
            return self._apply_response(resp)
        except grpc.RpcError as exc:
            return self._fail(f"remote call {rpc_name} failed: {exc}")
        except Exception as exc:
            return self._fail(f"remote call {rpc_name} error: {exc}")

    def _apply_response(self, resp) -> bool:
        message = getattr(resp, "message", "")
        self._set_command_result(bool(resp.success), message)
        state = getattr(resp, "state", None)
        if state is not None:
            self._update_state_from_response(state)
        return bool(resp.success)

    def _update_state_from_response(self, resp):
        update_age_ms = float(getattr(resp, "update_age_ms", -1.0))
        timestamp = 0.0 if update_age_ms < 0 else time.monotonic() - update_age_ms / 1000.0
        state = {
            "valid": bool(getattr(resp, "valid", False)),
            "connected": bool(getattr(resp, "connected", False)),
            "stale": bool(getattr(resp, "stale", True)),
            "message": getattr(resp, "message", ""),
            "init_state": int(getattr(resp, "init_state", -1)),
            "init_state_text": getattr(resp, "init_state_text", ""),
            "grip_state": int(getattr(resp, "grip_state", -1)),
            "grip_state_text": getattr(resp, "grip_state_text", ""),
            "position": int(getattr(resp, "position", -1)),
            "speed": int(getattr(resp, "speed", -1)),
            "current": int(getattr(resp, "current", -1)),
            "error": int(getattr(resp, "error", -1)),
            "error_text": getattr(resp, "error_text", ""),
            "timestamp": timestamp,
            "update_age_ms": update_age_ms,
        }
        with self._state_lock:
            self._state_cache = state

    # ================= Result bookkeeping =================

    def _set_command_result(self, success: bool, message: str):
        self._last_message = message
        if not success:
            self._last_error = message

    def _fail(self, message: str) -> bool:
        self._set_command_result(False, message)
        print(message)
        return False
