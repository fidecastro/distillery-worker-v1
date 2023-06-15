##### Distillery Worker for serverless Runpod - Version 1.0 - June 14 2023

import json
import time
import subprocess
import requests
from PIL import Image, PngImagePlugin
import base64
import io
import runpod
from concurrent.futures import ThreadPoolExecutor

######## User inputs below this line
API_COMMAND_LINE = 'python3 stable-diffusion-webui/launch.py --xformers --api --no-hashing --no-download-sd-model --freeze-settings --disable-console-progressbars --skip-version-check --skip-python-version-check --skip-prepare-environment --skip-torch-cuda-test --skip-install'
KILL_API_IN_END = False  # Whether to kill the API server after the last request
INITIAL_PORT = 7860  # Port to start looking for available ports
######## Code to handle the launch and killing of the API server (must be in the SD Server) ########
import requests

class APISingleton:
    _instance = None
    _process = None
    base_url = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._process = None
        self.base_url = None

    def find_available_port(self):
        port = INITIAL_PORT
        while True:
            try:
                response = requests.get(f'http://127.0.0.1:{port}')
                if response.status_code != 200:
                    return f"http://127.0.0.1:{port}"
                else:
                    port += 1
            except requests.ConnectionError:
                return f"http://127.0.0.1:{port}"

    def start_api(self):
        if self.base_url is None:
            self.base_url = self.find_available_port()
            api_command_line = API_COMMAND_LINE + f" --port {self.base_url.split(':')[2]}"  # Split on ':' and get the third item to retrieve the port
            if self._process is None or self._process.poll() is not None:
                self._process = subprocess.Popen(api_command_line.split())
                print("API process started with PID:", self._process.pid)
            while not is_api_running(self.base_url):  # keep trying to connect until the server is ready
                print("API not ready yet, trying again...")
                time.sleep(1)  # wait for a bit before trying again to avoid overwhelming the server

    def kill_api(self):
        if self._process is not None and self._process.poll() is None:
            self._process.kill()
            self._process = None
            print("API process killed")

def is_api_running(url):
    test_payload = {
        "steps": 1,
        "width": 64,
        "height": 64,
        "cfg_scale": 6,
        "enable_hr": False,
        "restore_faces": False,
        "batch_size": 1,
        "save_images": False,
        "alwayson_scripts": [],
        "script_name": "",
        "do_not_save_samples": True
        }
    try:
        response = requests.get(url)
        if response.status_code == 200:
            test_image = generate_images(test_payload,url)
            if test_image:  # this checks whether test_image is not an empty list
                return True
    except Exception as e:
        print(f"API not ready yet, exception: {str(e)}")
    return False  # server is not ready

def process_image(image_b64, url):
    image = Image.open(io.BytesIO(base64.b64decode(image_b64.split(",",1)[0])))
    png_payload = {
        "image": "data:image/png;base64," + image_b64
    }
    response = requests.post(f'{url}/sdapi/v1/png-info', json=png_payload)
    pnginfo_data = response.json()
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("parameters", pnginfo_data.get("info"))
    bio = io.BytesIO()  # we'll use BytesIO to hold the image in memory
    image.save(bio, 'PNG', pnginfo=pnginfo)
    bio.seek(0)  # reset file pointer to the beginning
    image_base64 = base64.b64encode(bio.read()).decode("utf-8")  # Encode image to base64 and decode to string
    return {"image_base64": image_base64, "png_info": pnginfo_data.get("info")}

def generate_images(payload, url):
    response = requests.post(f'{url}/sdapi/v1/txt2img', json=payload)
    r = response.json()
    images = []
    if 'images' in r:
        images.extend(r['images'])
    return images

def deliver_images(payload):
    try:
        if api_singleton.base_url is None:
            api_singleton = APISingleton.get_instance()
            api_singleton.start_api()  # Request to start the API
            base_url = api_singleton.base_url
    except Exception as e:
        api_singleton = APISingleton.get_instance()
        api_singleton.start_api()  # Request to start the API
        base_url = api_singleton.base_url
    results = []
    try:
        images = generate_images(payload, base_url)
        with ThreadPoolExecutor(max_workers=len(images)) as executor:
            futures = [executor.submit(process_image, image_b64, base_url) for image_b64 in images]
            for future in futures:
                results.append(future.result())
    finally:  # This ensures finish_request() is called even if an error occurs
        if KILL_API_IN_END: 
            api_singleton.kill_api() # Request to kill the API
    return json.dumps(results)  # Convert the list of results to a JSON string

def handler(event):
    payload = event.get('input')
    if payload is None:
        return {"error": "No payload provided in event"}
    files = deliver_images(payload)
    return files

runpod.serverless.start({"handler": handler})
