import time

from dmgripper.gripper import Gripper


def wait_for_init(gripper: Gripper, timeout_s: float = 10.0) -> bool:
    if gripper.GetInitState() == 1:
        print("gripper is already initialized.")
        return True

    print("gripper is not initialized; starting full initialization.")
    if not gripper.Initialization():
        print(f"initialization command failed: {gripper.GetLastError()}")
        return False

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = gripper.GetAllState()
        print(
            f"\rinit_state={state.get('init_state_text')} "
            f"position={state.get('position')} message={state.get('message')}",
            end="",
            flush=True,
        )
        if state.get("init_state") == 1:
            print("\ninitialization succeeded.")
            return True
        time.sleep(0.2)

    print("\ninitialization timed out.")
    return False


def main():
    server_ip = "192.168.127.10"
    server_port = 50008

    print(f"connecting remote gripper: {server_ip}:{server_port}")
    gripper = Gripper(mode="remote", remote_ip=server_ip, remote_port=server_port)

    if not gripper.connect():
        print(f"connection failed: {gripper.GetLastError()}")
        return

    try:
        gripper.enable()
        if not wait_for_init(gripper):
            return

        print("\n=== Slow close ===")
        gripper.SetTargetSpeed(20)
        if not gripper.Close(wait=True, timeout_s=5.0):
            print(f"close failed: {gripper.GetLastError()}")
            return
        print(f"close completed, current position: {gripper.GetCurrentPosition()}")

        print("\n=== Fast open ===")
        gripper.SetTargetSpeed(50)
        if not gripper.Open(wait=True, timeout_s=5.0):
            print(f"open failed: {gripper.GetLastError()}")
            return
        print(f"open completed, current position: {gripper.GetCurrentPosition()}")

        print("\n=== Stop test ===")
        gripper.SetTargetSpeed(40)
        gripper.Close()
        trigger_pos = -1
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            pos = gripper.GetCurrentPosition()
            if 200 <= pos <= 300:
                trigger_pos = pos
                print(f"\ntrigger Stop at position: {trigger_pos}")
                gripper.Stop()
                break
            print(f"\rcurrent position: {pos}", end="", flush=True)
            time.sleep(0.02)

        time.sleep(0.5)
        state = gripper.GetAllState()
        print(
            f"\nstate after stop: position={state.get('position')} "
            f"grip_state={state.get('grip_state_text')} message={state.get('message')}"
        )

    except KeyboardInterrupt:
        print("\ntest interrupted by user.")
    except Exception as exc:
        print(f"\ntest error: {exc}")
    finally:
        print("\ndisconnecting.")
        gripper.disconnect()


if __name__ == "__main__":
    main()
