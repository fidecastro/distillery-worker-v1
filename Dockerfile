# Using the official Python image as the base image
FROM felipeinfante/distillery-container:v1.0base

# Setting the working directory in the container
WORKDIR /workspace

# Copy the Python script and SD folder into the container
COPY distillery-worker.py .
COPY stable-diffusion-webui .

RUN git config --global --add safe.directory '*'

# Specifying the command to run the script
CMD ["python3", "-u", "distillery-worker.py"]
