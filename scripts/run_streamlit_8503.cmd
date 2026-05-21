@echo off
cd /d Z:\Projects\20260515_8760
python -m streamlit run src/green_direct/ui/app.py --server.port=8503 --server.address=localhost > outputs\streamlit_8503.task.log 2>&1
