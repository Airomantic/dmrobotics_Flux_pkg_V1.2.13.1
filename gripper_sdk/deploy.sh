bash can_restart.sh
pip install --no-index --find-links=./pkg .
sudo cp gripper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable gripper.service
sudo systemctl start gripper.service
sudo systemctl status gripper.service