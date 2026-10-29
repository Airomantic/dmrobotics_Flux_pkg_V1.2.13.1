import grpc
from concurrent import futures
import threading
from google.protobuf import empty_pb2

from dmgripper import gripper_pb2
from dmgripper import gripper_pb2_grpc
from dmgripper.gripper import Gripper


def _state_to_pb(state: dict) -> gripper_pb2.StateResponse:
    return gripper_pb2.StateResponse(
        valid=bool(state.get("valid", False)),
        init_state=int(state.get("init_state", -1)),
        grip_state=int(state.get("grip_state", -1)),
        position=int(state.get("position", -1)),
        speed=int(state.get("speed", -1)),
        current=int(state.get("current", -1)),
        error=int(state.get("error", -1)),
        message=str(state.get("message", "")),
        update_age_ms=float(state.get("update_age_ms", -1.0)),
        stale=bool(state.get("stale", True)),
        init_state_text=str(state.get("init_state_text", "unknown")),
        grip_state_text=str(state.get("grip_state_text", "unknown")),
        error_text=str(state.get("error_text", "unknown")),
        connected=bool(state.get("connected", False)),
    )


class GripperService(gripper_pb2_grpc.GripperServiceServicer):
    def __init__(self):
        self.gripper = None
        self.lock = threading.RLock()

    def _get_gripper(self):
        with self.lock:
            return self.gripper

    def _current_state_pb(self) -> gripper_pb2.StateResponse:
        gripper = self._get_gripper()
        if gripper is None:
            return gripper_pb2.StateResponse(
                valid=False,
                stale=True,
                connected=False,
                message="gripper is not connected",
                init_state=-1,
                grip_state=-1,
                position=-1,
                speed=-1,
                current=-1,
                error=-1,
                init_state_text="unknown",
                grip_state_text="unknown",
                error_text="unknown",
                update_age_ms=-1.0,
            )
        return _state_to_pb(gripper.get_state())

    def _response(self, success: bool, message: str) -> gripper_pb2.Response:
        return gripper_pb2.Response(
            success=bool(success),
            message=message,
            state=self._current_state_pb(),
        )

    def _exec_bool(self, func_name: str, val=None) -> gripper_pb2.Response:
        gripper = self._get_gripper()
        if gripper is None:
            return self._response(False, "gripper is not connected")

        try:
            func = getattr(gripper, func_name)
            ok = func(val) if val is not None else func()
            message = gripper.GetLastMessage() if ok else gripper.GetLastError()
            if not message:
                message = "command executed successfully" if ok else "command execution failed"
            return self._response(ok, message)
        except Exception as exc:
            return self._response(False, f"execution of {func_name} raised an exception: {exc}")

    # ================= Connection management =================

    def Connect(self, request, context):
        with self.lock:
            if self.gripper is not None:
                self.gripper.disconnect()

            print(f"connecting local CAN-FD: channel={request.channel}, gripper_id={request.motor_id}")
            self.gripper = Gripper(
                mode="local",
                channel=request.channel,
                motor_id=request.motor_id,
                read_interval_s=request.read_interval_s or 0.05,
                read_timeout_s=request.read_timeout_s or 0.1,
                retry_count=request.retry_count if request.retry_count > 0 else 2,
                stale_timeout_s=request.stale_timeout_s or 0.5,
                command_min_interval_s=request.command_min_interval_s or 0.02,
            )
            ok = self.gripper.connect()
            message = self.gripper.GetLastMessage() if ok else self.gripper.GetLastError()
            if not ok:
                self.gripper.disconnect()
                self.gripper = None
            return self._response(ok, message or ("connected" if ok else "connection failed"))

    def Disconnect(self, request, context):
        with self.lock:
            if self.gripper is None:
                return self._response(True, "gripper is already disconnected")

            ok = self.gripper.disconnect()
            message = self.gripper.GetLastMessage() if ok else self.gripper.GetLastError()
            if ok:
                self.gripper = None
            return self._response(ok, message or ("disconnected" if ok else "disconnect failed"))

    # ================= Control API =================

    def Enable(self, request, context):
        return self._exec_bool("enable")

    def Disable(self, request, context):
        return self._exec_bool("disable")

    def Initialization(self, request, context):
        return self._exec_bool("Initialization")

    def Home(self, request, context):
        return self._exec_bool("home")

    def Open(self, request, context):
        return self._exec_bool("Open")

    def Close(self, request, context):
        return self._exec_bool("Close")

    def Stop(self, request, context):
        return self._exec_bool("Stop")

    def Resume(self, request, context):
        return self._exec_bool("Resume")

    def ClearError(self, request, context):
        return self._exec_bool("Clear_error")

    def SetTargetPosition(self, request, context):
        return self._exec_bool("SetTargetPosition", request.value)

    def SetTargetForce(self, request, context):
        return self._exec_bool("SetTargetForce", request.value)

    def SetTargetSpeed(self, request, context):
        return self._exec_bool("SetTargetSpeed", request.value)

    def SetJog(self, request, context):
        return self._exec_bool("SetJog", request.value)

    def SetFollowMode(self, request, context):
        return self._exec_bool("SetFollowMode", request.value)

    # ================= Status API =================

    def _value_response(self, value: int) -> gripper_pb2.ValueResponse:
        state = self._current_state_pb()
        return gripper_pb2.ValueResponse(
            value=int(value),
            success=bool(state.valid),
            message=state.message,
            state=state,
        )

    def GetCurrentPosition(self, request, context):
        gripper = self._get_gripper()
        value = gripper.GetCurrentPosition() if gripper else -1
        return self._value_response(value)

    def GetInitState(self, request, context):
        gripper = self._get_gripper()
        value = gripper.GetInitState() if gripper else -1
        return self._value_response(value)

    def GetCurrentForce(self, request, context):
        gripper = self._get_gripper()
        value = gripper.GetCurrentForce() if gripper else -1
        return self._value_response(value)

    def GetAllState(self, request, context):
        return self._current_state_pb()


def serve(port: int = 50008):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    gripper_pb2_grpc.add_GripperServiceServicer_to_server(GripperService(), server)
    address = f"[::]:{port}"
    bind_port = server.add_insecure_port(address)
    if bind_port == 0:
        raise RuntimeError(f"gRPC server startup failed: port {port} binding failed")

    print(f"gripper gRPC server started on port {bind_port}.")
    try:
        server.start()
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("shutdown signal received, stopping gRPC server.")
        server.stop(0)
    except Exception as exc:
        print(f"gRPC server runtime error: {exc}")
        server.stop(0)
        raise


if __name__ == "__main__":
    serve()
