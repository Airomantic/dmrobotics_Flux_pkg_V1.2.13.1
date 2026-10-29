import argparse
import time

from dmgripper.gripper import Gripper


def wait_for_initialization(gripper: Gripper, timeout_s: float = 10.0) -> bool:
    if gripper.GetInitState() == 1:
        print("gripper is already initialized.")
        return True

    print("gripper is not initialized; starting homing initialization...")
    if not gripper.Initialization():
        print("initialization command failed.")
        return False

    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if gripper.GetInitState() == 1:
            print("initialization succeeded.")
            return True
        time.sleep(0.2)

    print("initialization timed out.")
    return False


def run_cycle_test(args: argparse.Namespace) -> None:
    gripper = Gripper(
        mode=args.mode,
        channel=args.channel,
        motor_id=args.motor_id,
        remote_ip=args.ip,
        remote_port=args.port,
    )

    print(f"connecting gripper: mode={args.mode}, ip={args.ip}, port={args.port}, channel={args.channel}, motor_id={args.motor_id}")
    if not gripper.connect():
        print("connection failed; check server, CAN interface, IP, or port.")
        return

    read_count = 0
    valid_count = 0
    min_pos = None
    max_pos = None
    last_print = 0.0
    action = "close"
    target = args.close_pos
    completed_close = 0
    completed_open = 0
    full_cycles = 0
    action_start = time.perf_counter()
    timed_out_action = None

    try:
        gripper.enable()
        if not wait_for_initialization(gripper, timeout_s=args.init_timeout):
            return

        gripper.SetTargetSpeed(args.speed)
        gripper.SetTargetForce(args.force)
        if not gripper.move_to(target):
            print("close target position command failed.")
            return
        print(
            f"starting {args.duration:.1f}s close->open cycle: "
            f"open={args.open_pos}, close={args.close_pos}, speed={args.speed}, force={args.force}"
        )

        start = time.perf_counter()
        end = start + args.duration
        while time.perf_counter() < end:
            now = time.perf_counter()
            pos = gripper.GetCurrentPosition()
            read_count += 1

            if pos >= 0:
                valid_count += 1
                min_pos = pos if min_pos is None else min(min_pos, pos)
                max_pos = pos if max_pos is None else max(max_pos, pos)

                reached_open = action == "open" and pos >= args.open_pos - args.tolerance
                reached_close = action == "close" and pos <= args.close_pos + args.tolerance

                if reached_close:
                    completed_close += 1
                    action = "open"
                    target = args.open_pos
                    if not gripper.move_to(target):
                        print("\nopen target position command failed.")
                        break
                    action_start = now
                elif reached_open:
                    completed_open += 1
                    full_cycles += 1
                    action = "close"
                    target = args.close_pos
                    if not gripper.move_to(target):
                        print("\nclose target position command failed.")
                        break
                    action_start = now
                elif args.max_action_s > 0 and now - action_start >= args.max_action_s:
                    timed_out_action = action
                    print(f"\n{action} action timed out, current position {pos}, target position {target}.")
                    break

            if now - last_print >= args.print_interval:
                elapsed = now - start
                freq = read_count / elapsed if elapsed > 0 else 0.0
                print(
                    f"\raction={action:<5} pos={pos:>4} target={target:>4} "
                    f"reads={read_count:>5} freq={freq:>7.1f} Hz "
                    f"valid={valid_count:>5} close_ok={completed_close} open_ok={completed_open}",
                    end="",
                    flush=True,
                )
                last_print = now

        total_time = time.perf_counter() - start
        freq = read_count / total_time if total_time > 0 else 0.0
        valid_freq = valid_count / total_time if total_time > 0 else 0.0
        print("\n\n=== Test results ===")
        print(f"test duration: {total_time:.3f} s")
        print(f"read count: {read_count}")
        print(f"valid read count: {valid_count}")
        print(f"read frequency: {freq:.2f} Hz")
        print(f"valid read frequency: {valid_freq:.2f} Hz")
        print(f"position range: {min_pos if min_pos is not None else 'N/A'} - {max_pos if max_pos is not None else 'N/A'}")
        print(f"successful close count: {completed_close}")
        print(f"successful open count: {completed_open}")
        print(f"successful full cycles: {full_cycles}")
        if timed_out_action:
            print(f"unfinished action: {timed_out_action} -> {target}")
        else:
            print(f"current target at end: {action} -> {target}")

    except KeyboardInterrupt:
        print("\ntest interrupted by user.")
    finally:
        try:
            gripper.Stop()
        finally:
            gripper.disconnect()
        print("connection closed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="5-second gripper open/close cycle and realtime position read-frequency test")
    parser.add_argument("--mode", choices=("remote", "local"), default="remote")
    parser.add_argument("--ip", default="192.168.127.10", help="server IP in remote mode")
    parser.add_argument("--port", type=int, default=50008, help="server port in remote mode")
    parser.add_argument("--channel", default="can0", help="CAN channel in local mode")
    parser.add_argument("--motor-id", type=int, default=1)
    parser.add_argument("--duration", type=float, default=5.0, help="test duration in seconds")
    parser.add_argument("--speed", type=int, default=80, help="target speed, range 1-100")
    parser.add_argument("--force", type=int, default=50, help="target force, range 20-100")
    parser.add_argument("--open-pos", type=int, default=1000)
    parser.add_argument("--close-pos", type=int, default=0)
    parser.add_argument("--tolerance", type=int, default=10, help="position-reached tolerance")
    parser.add_argument("--max-action-s", type=float, default=0.0, help="maximum wait time for one open or close action; 0 disables action timeout")
    parser.add_argument("--print-interval", type=float, default=0.1, help="realtime print refresh interval")
    parser.add_argument("--init-timeout", type=float, default=10.0)
    return parser.parse_args()


if __name__ == "__main__":
    run_cycle_test(parse_args())
