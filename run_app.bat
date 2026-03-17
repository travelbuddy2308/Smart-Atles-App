@echo off
REM ===============================
REM Run Streamlit Web Application
REM ===============================

REM Activate your Python virtual environment (if you have one)
REM Replace "venv" with your env folder name
call venv\Scripts\activate

REM Navigate to your app folder (if needed)
cd %~dp0

REM Run the Streamlit app
streamlit run log_p.py

REM Keep the window open after exit
pause