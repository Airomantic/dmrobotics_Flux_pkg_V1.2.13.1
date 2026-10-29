ls
cd /home/cftc
ls
cat /etc/init.d/first*
cat /etc/init.d/ho*
ls
sudo 
exit
ls
systemctl list-units --type=service --state=running
cd ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server
python grpc_server.py
cd ~/gripper_sdk
bash deploy.sh
python main.py
cd ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server
python grpc_server.py
cd ~/gripper_sdk
bash deploy.sh
ip -details -statistics link show can0
ls
bash can_restart.sh 
cd ~/gripper_sdk
for f in /AGENTS.md /home/AGENTS.md /home/cftc/AGENTS.md /home/cftc/gripper_sdk/AGENTS.md; do if [ -f "$f" ]; then printf '%s\n' "$f"; cat "$f"; fi; done
ip -details -statistics link show can0
systemctl status gripper.service --no-pager -l
sed -n '1,280p' cycle_position_frequency_test.py
sed -n '1,220p' test_demo.py
command -v rg
find dmgripper -maxdepth 2 -type f -not -name '*.pyc' -not -name '*.so'
sed -n '1,250p' server.py
grep -nEi 'CAN|bitrate|波特|终端|ID|电源|频率' README_zh.md can_restart.sh
grep -nE '^class |^    def |can\.Message|can\.Bus|bitrate|bitrate_switch|is_fd|0x600|0x200|0x0200|0x0600' dmgripper/gripper.py
sed -n '1,310p' dmgripper/gripper.py
sed -n '304,365p' dmgripper/gripper.py
sed -n '455,487p' dmgripper/gripper.py
sed -n '540,595p' dmgripper/gripper.py
sudo -v
bash <<'SH'
set -eu
restore_can() {
  sudo ip link set can0 down
  sudo ip link set can0 type can berr-reporting off
  sudo ip link set can0 up
  sudo systemctl start gripper.service
}
trap restore_can EXIT
sudo systemctl stop gripper.service
sudo ip link set can0 down
sudo ip link set can0 type can berr-reporting on
sudo ip link set can0 up
ip -details -statistics link show can0
python3 -u - <<'PY'
import json
import subprocess
import sys
import time
from dmgripper.gripper import Gripper
print('CONTROLBOX_LOCAL_SDK_CHECK', sys.version)
capture = subprocess.Popen(['timeout', '3s', 'candump', '-n', '40', '-t', 'a', '-e', '-x', 'can0,0:0,#FFFFFFFF'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
g = Gripper(mode='local', channel='can0', motor_id=1, retry_count=0)
try:
    time.sleep(0.2)
    started = time.monotonic()
    ok = g.connect()
    print('connect_ok=', ok, 'elapsed_s=', round(time.monotonic() - started, 3))
    print('last_error=', g.GetLastError())
    print('state=', json.dumps(g.get_state(), ensure_ascii=False))
finally:
    g.disconnect()
    output, _ = capture.communicate(timeout=5)
    print('CAN_CAPTURE_BEGIN\n' + output + 'CAN_CAPTURE_END')
subprocess.run(['ip', '-details', '-statistics', 'link', 'show', 'can0'], check=True)
PY
SH

systemctl is-active gripper.service
bash <<'SH'
set -eu
restore_can() {
  sudo ip link set can0 down
  sudo ip link set can0 type can berr-reporting off
  sudo ip link set can0 up
  sudo systemctl start gripper.service
}
trap restore_can EXIT
sudo systemctl stop gripper.service
sudo ip link set can0 down
sudo ip link set can0 type can berr-reporting on
sudo ip link set can0 up
python3 -u - <<'PY'
import can
import subprocess
import time
for label, fd in [('CAN_FD_NO_BRS', True), ('CLASSIC_CAN_READ_ONLY', False)]:
    subprocess.run(['sudo', 'ip', 'link', 'set', 'can0', 'down'], check=True)
    subprocess.run(['sudo', 'ip', 'link', 'set', 'can0', 'up'], check=True)
    print('CASE_BEGIN', label, flush=True)
    capture = subprocess.Popen(['timeout', '1s', 'candump', '-n', '25', '-t', 'a', '-e', '-x', 'can0,0:0,#FFFFFFFF'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(0.1)
    bus = can.Bus(channel='can0', interface='socketcan', fd=True)
    try:
        msg = can.Message(arbitration_id=0x601, is_extended_id=False, is_fd=fd, bitrate_switch=False, data=[0x03,0x02,0x00,0x00,0x06])
        bus.send(msg, timeout=0.2)
        deadline = time.monotonic() + 0.3
        replies = []
        while time.monotonic() < deadline:
            response = bus.recv(max(0.0, deadline-time.monotonic()))
            if response is not None and not response.is_error_frame:
                replies.append(str(response))
        print('normal_RX_frames=', replies)
    finally:
        bus.shutdown()
        output, _ = capture.communicate(timeout=3)
        print(output)
    subprocess.run(['ip', '-details', '-statistics', 'link', 'show', 'can0'], check=True)
    print('CASE_END', label, flush=True)
PY
SH

systemctl is-active gripper.service
sudo dmesg --color=never | grep -iE 'mcp251|can0|spi2' | tail -n 35
python3 - <<'PY'
from pathlib import Path
p = Path('/sys/class/net/can0/device/of_node').resolve()
print('CAN_DEVICE_TREE_NODE:', p)
for f in sorted(p.iterdir()):
    if f.is_file():
        raw = f.read_bytes()
        print(f.name, repr(raw) if f.name in ('name','compatible','status') else raw.hex())
PY

sudo cat /sys/kernel/debug/gpio
grep -RnE --include='*.sh' --include='*.service' 'gpio379|gpio380|/sys/class/gpio|can0|can1|mcp251' /etc/systemd/system /usr/local/bin /home/cftc/gripper_sdk 2>/dev/null
if [ -f /etc/rc.local ]; then cat /etc/rc.local; fi
systemctl list-units --type=service --state=running --no-pager
sed -n '1,180p' ~/gripper_sdk/deploy.sh
ps -eo pid,ppid,args | grep --color=never -E 'grpc_server.py|gripper_sdk/server.py|dmrobotics|sensor_server' | grep --color=never -v grep
ss -lntp | grep --color=never -E ':50008|:50051|:50052'
for f in ~/dmrobotics_Flux_pkg_V1.2.13.1/AGENTS.md ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/AGENTS.md ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server/AGENTS.md; do if [ -f "$f" ]; then cat "$f"; fi; done
cd ~/gripper_sdk
sudo -v
SYSTEMD_PAGER=cat SYSTEMD_COLORS=0 bash deploy.sh
sudo systemctl restart gripper.service
bash <<'SH'
set -e
systemctl is-active gripper.service
ss -lntp | grep --color=never -E ':50008|:50051|:50052'
ip -details -statistics link show can0
env no_grpc_proxy=127.0.0.1 python3 -u cycle_position_frequency_test.py --mode remote --ip 127.0.0.1 --duration 3 --speed 10 --force 20 --open-pos 550 --close-pos 450 --max-action-s 3 --init-timeout 10
ip -details -statistics link show can0
SH

bash <<'SH'
ps -eo pid,ppid,args | grep --color=never -E 'grpc_server.py|sensor_server' | grep --color=never -v grep || true
ls -l ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server/grpc_server.py
sed -n '1,240p' ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server/grpc_server.py | cut -c 1-250
SH

tail -n 130 ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server/grpc_server.py
bash <<'SH'
set -eu
cd ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server
sensor_diag_log=$(mktemp /tmp/gripper-sensor-server.XXXXXX.log)
nohup python -u grpc_server.py > "$sensor_diag_log" 2>&1 < /dev/null &
sensor_diag_pid=$!
printf 'sensor_server_pid=%s\nsensor_server_log=%s\n' "$sensor_diag_pid" "$sensor_diag_log"
sleep 2
tail -n 35 "$sensor_diag_log"
kill -0 "$sensor_diag_pid"
ss -lntp | grep --color=never -E ':50051|:50052|:50053|:50054|:50055'
SH

bash <<'SH'
set -eu
cd ~/gripper_sdk
SYSTEMD_PAGER=cat SYSTEMD_COLORS=0 bash deploy.sh
sudo systemctl restart gripper.service
systemctl is-active gripper.service
ss -lntp | grep --color=never -E ':50008|:50051|:50052'
python3 -u - <<'PY'
import json
from dmgripper.gripper import Gripper
g = Gripper(mode='local', channel='can0', motor_id=1, retry_count=0)
try:
    ok = g.connect()
    print('AFTER_SENSOR_START_AND_DEPLOY: connect_ok=', ok)
    print('last_error=', g.GetLastError())
    print('state=', json.dumps(g.get_state()))
finally:
    g.disconnect()
PY
ip -details -statistics link show can0
SH

bash <<'SH'
set -eu
restore_can() {
  sudo ip link set can0 down
  sudo ip link set can0 type can loopback off berr-reporting off
  sudo ip link set can0 up
  sudo systemctl start gripper.service
}
trap restore_can EXIT
sudo systemctl stop gripper.service
sudo ip link set can0 down
sudo ip link set can0 type can loopback on berr-reporting on
sudo ip link set can0 up
ip -details link show can0
python3 -u - <<'PY'
import can
from pathlib import Path
base = Path('/sys/class/net/can0/statistics')
before = {key: int((base / key).read_text()) for key in ('rx_packets','tx_packets','rx_errors','tx_errors')}
bus = can.Bus(channel='can0', interface='socketcan', fd=True, receive_own_messages=False)
try:
    payload = bytes([0x03,0x02,0x00,0x00,0x06])
    bus.send(can.Message(arbitration_id=0x601, is_extended_id=False, is_fd=True, bitrate_switch=True, data=payload), timeout=0.2)
    reply = bus.recv(timeout=1.0)
    passed = bool(reply is not None and not reply.is_error_frame and reply.is_rx and reply.arbitration_id == 0x601 and bytes(reply.data) == payload)
    print('CONTROLLER_INTERNAL_LOOPBACK_PASS=', passed)
    print('internal_echo=', reply)
    print('This is the controller internal echo, NOT a gripper reply.')
finally:
    bus.shutdown()
after = {key: int((base / key).read_text()) for key in before}
print('counter_before=', before)
print('counter_after=', after)
PY
SH

bash <<'SH'
python3 - <<'PY'
from pathlib import Path
for path in ['/proc/device-tree/model', '/proc/device-tree/compatible']:
    print(path, repr(Path(path).read_bytes()))
PY
systemctl is-active gripper.service
ss -lntp | grep --color=never -E ':50008|:50051|:50052|:50053|:50054|:50055'
ip -details -statistics link show can0
SH

exit
ls -la /home/cftc
readlink /proc/4814/cwd /proc/4849/cwd
ls -l /dev/v4l/by-id
command -v rg
ls -la /home/cftc/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server
find /home/cftc/dmrobotics_Flux_pkg_V1.2.13.1 -maxdepth 4 -type f -not -name '*.so' -not -name '*.pyc' -not -name '*.bin' -not -name '*.onnx'
grep -RInE 'right2|left2|50051|50052|L26050109|L26050136' /etc/systemd/system /etc/udev/rules.d /home/cftc/.config --exclude-dir=chromium --exclude-dir=Code 2>/dev/null | head -n 60 | cut -c 1-250
grep -nE 'right|left|50051|50052|dev_id|serial|port|argparse' /home/cftc/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server/grpc_server.py | head -n 50
ls -la /home/cftc/gripper_sdk
grep -RInE 'right2|left2' /home/cftc/gripper_sdk /home/cftc/dmrobotics_Flux_pkg_V1.2.13.1 --include='*.py' --include='*.json' --include='*.yaml' --include='*.md' --exclude-dir=.git | head -n 30 | cut -c 1-200
exit
ls
command -v rg
pwd
ls -d ~/gripper_sdk ~/dmrobotics* /opt/ros/* 2>/dev/null
ps -eo pid,args | grep -E 'grpc_server|sensor_server|gripper|ros2|tactile' | grep -v grep
find ~/gripper_sdk -maxdepth 3 -type f \( -name '*.py' -o -name '*.proto' -o -name '*.md' \)
find ~/dmrobotics_Flux_pkg_V1.2.13.1 -maxdepth 4 -type f \( -name '*grpc*py' -o -name '*.proto' -o -name '*readme*' -o -name '*README*' \)
grep -nEi 'force|current|GetAllState|position|topic|rclpy' ~/gripper_sdk/server.py
ss -ltnp | grep -E ':50008|:50051|:50052'
grep -nEi 'force|current|0x|GetAllState' ~/gripper_sdk/dmgripper/gripper.py | head -90
grep -nEi 'force|current|单位|牛|电流|力' ~/gripper_sdk/README_zh.md | head -65
grep -nEi 'force|Force|wrench|rclpy|topic|sensor_api|Get' ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server/grpc_server.py | head -100
cat ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/README.md | head -100
source /opt/ros/humble/setup.bash
ROS_LOG_DIR=/tmp/lerobot_force_inspect timeout 8s ros2 topic list --no-daemon --spin-time 3
sed -n '417,449p' ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server/grpc_server.py
sed -n '1,100p' ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server/sensor_api_pb2_grpc.py
find ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg -maxdepth 4 -type f \( -name '*.h' -o -name '*.hpp' -o -name '*.md' -o -name '*.pyi' \)
ROS_DOMAIN_ID=111 ROS_LOG_DIR=/tmp/lerobot_force_inspect timeout 8s ros2 topic list --no-daemon --spin-time 3
sed -n '85,145p' ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server/grpc_server.py
grep -nEi 'force|N.m|newton|牛|unit|Fx|Fy|Fz|Mx|My|Mz' ~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/include/*.hpp
python - <<'PY'
import sys, os, grpc
sys.path.insert(0, os.path.expanduser('~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server'))
import sensor_api_pb2 as pb
import sensor_api_pb2_grpc as rpc
for port in (50051, 50052):
    with grpc.insecure_channel('127.0.0.1:%d' % port) as channel:
        stub = rpc.SensorApiStub(channel)
        print(port, stub.getListCameras(pb.Empty(), timeout=2))
print('DevInfo fields:', [(f.name, f.type) for f in pb.DevInfo.DESCRIPTOR.fields])
print('NdArray fields:', [(f.name, f.type) for f in pb.NdArray.DESCRIPTOR.fields])
PY

python - <<'PY'
import sys, os, time, json, grpc, numpy as np
sys.path.insert(0, os.path.expanduser('~/dmrobotics_Flux_pkg_V1.2.13.1/dmrobotics_Flux_pkg/sensor_server'))
import sensor_api_pb2 as pb
import sensor_api_pb2_grpc as rpc
for port, dev in ((50051, '0'), (50052, '2')):
    samples = []
    with grpc.insecure_channel('127.0.0.1:%d' % port) as channel:
        stub = rpc.SensorApiStub(channel)
        for index in range(5):
            response = stub.getForce(pb.DevInfo(dev_id=dev), timeout=2)
            if not response.ok:
                print(json.dumps({'port': port, 'dev_id': dev, 'error': response.info}))
                break
            values = np.frombuffer(response.force.data, dtype=response.force.dtype).reshape(tuple(response.force.shape))
            samples.append(values.reshape(-1).tolist())
            time.sleep(0.25)
    print(json.dumps({'port': port, 'dev_id': dev, 'order': ['Fx','Fy','Fz','Mx','My','Mz'], 'samples': samples}))
PY

exit
ls
