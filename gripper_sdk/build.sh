
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. dmgripper/gripper.proto

sed -i 's/from dmgripper import gripper_pb2 as/from . import gripper_pb2 as/' dmgripper/gripper_pb2_grpc.py
sed -i 's/^import gripper_pb2 as/from . import gripper_pb2 as/' dmgripper/gripper_pb2_grpc.py

echo "Build complete. Imports fixed."
