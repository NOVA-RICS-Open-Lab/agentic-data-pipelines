FROM python:3.11-slim
WORKDIR /app
RUN pip install asyncua
COPY kukarobot_sim.py .
CMD ["python", "-u","kukarobot_sim.py"]