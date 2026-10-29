# setup.py
from setuptools import setup, find_packages

setup(
    name="dmgripper",
    version="1.0.0",
    description="SDK for DM Robotics Gripper Control (Local & Remote)",
    author="1",
    packages=find_packages(), 
    install_requires=[
        "python-can==4.6.1",
    ],
    extras_require={
        "remote": [
            "grpcio",
            "protobuf",
        ],
        "build": [
            "grpcio-tools",
        ],
    },
    python_requires='>=3.10',
)
