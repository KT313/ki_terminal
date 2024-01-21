import os
import json
import requests
import subprocess
import socket
import contextlib
import io
import sys

default_settings_json = {
        'mode': 'thi',
        'credentials_file': 'lib/id.txt',
        'local_address': "127.0.0.1",
        'local_port': 8080,
        'local_model': None,
        'local_software': 'ollama',
        'local_dns': 'None'
        }

def ensure_settings_file(file_path, default_settings=default_settings_json):
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            json.dump(default_settings, file, indent=4)
            print(f"Created settings file: {file_path}")

def update_settings(key, value, path):
    settings_file = path
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as file:
            settings = json.load(file)
    else:
        settings = default_settings_json
    
    if value.isdigit():
        value = int(value)
    settings[key] = value

    with open(settings_file, 'w') as file:
        json.dump(settings, file, indent=4)

def make_request_info(settings, msg, current_dir):
    # print(settings)

    with open(f'{current_dir}/lib/request.txt', 'r') as file:
        lines = file.readlines()

    headers = lines[:16]          # first 18 lines are headers
    json_content = lines[16:]     # the rest is json data

    # convert headers to dictionary
    header_dict = {}
    for header in headers:
        if ": " in header:
            key,val = header.strip().split(": ", 1)
            header_dict[key] = val
    header_dict["Cookie"] = open(f"{current_dir}/{settings['credentials_file']}","r").read().strip()

    # reconstruct url from the header
    url = 'https://' + header_dict['Host'] + headers[0].split()[1]

    json_content = ''.join(json_content).strip()
    # print(f"\"{json_content}\"")
    # convert json lines to a json object
    json_data = json.loads(''.join(json_content))
    json_data["messages"] = msg
    # print(json_data)

    # here modify the json_data


    # dropping 'Content-Length' because it will be automatically set by requests library
    if 'Content-Length' in header_dict:
        del header_dict['Content-Length']

    # local mode
    if settings['mode'] == 'local':
        url = f"http://{settings['local_address']}:{settings['local_port']}/api/generate"
        header_dict['Host'] = None
        header_dict['Referer'] = None
        header_dict['Origin'] = None
        json_data['model'] = settings['local_model']

    return url, header_dict, json_data

def send_request(url, headers, json_data):
    try:
        response = requests.post(url, headers=headers, json=json_data)
    except requests.exceptions.TooManyRedirects:
        print(" | too many redirects, probably cookies expired")
        exit()
    
    if "choices" in response.json():
        reply = response.json()["choices"][0]["message"]["content"]
    else:
        reply = " | received empty reply from server"
        print(response.json())

    return reply


def make_curl_cmd(settings, msg, current_dir, question_mode, context_mode):
    if context_mode and os.path.exists(f'{current_dir}/lib/context.txt'):
        context_val = open(f'{current_dir}/lib/context.txt', 'r').read().strip() + " "
    else:
        context_val = ""

    # save user msg for context
    open(f'{current_dir}/lib/context.txt', 'a').write(f"USER: {msg[1]['content']}\n")    

    # apply format
    msg[1]["content"] =  f"[INST] {msg[1]['content']} [/INST]"

    prompt = ""
    for entry in msg:
        content = entry['content']
        if 'name' in entry:
            line = f"{entry['name']}: \n{content}"
        else:
            line = f"{entry['role']}: \n{content}"
        prompt += line + "\n"

    # just for testing models
    model_val = "mixtral_instruct_q3km:latest"
    #model_val = "yarn-mistral:7b-128k"

    # default inference parameters
    num_ctx_val = 8192      # context
    num_predict_val = 4096
    mirostat_val = 0
    temp_val = 0.8
    seed_val = 0
    tfs_z_val = 1
    top_k_val = 40
    top_p_val = 0.9

    
    # question mode
    if question_mode:
        template_val = "{{ .System }} {{ .Prompt }} Sure, "
        mirostat_val = 2
    
    # terminal command mode
    else:
        template_val = "{{ .System }} {{ .Prompt }} "
        mirostat_val = 0
        temp_val = 0.0
        tfs_z_val = 5.0
        top_k_val = 1
        top_p_val = 0.01
    
    # generating post data
    data = {
        "model": model_val,
        "system": msg[0]["content"],
        "prompt": f'{context_val}{msg[1]["content"]}',
        "template": template_val,
        # "format": "json",
        "options": {
            "mirostat": mirostat_val,
            "num_ctx": num_ctx_val,
            "num_predict": num_predict_val,
            "temperature": temp_val,      # std: 0.8
            "seed": seed_val,
            "tfs_z": tfs_z_val,
            "top_k": top_k_val,             # 1 - 100, -> number of best possible tokens to consider (1: only best)
            "top_k": top_p_val,             # 0 - 2+, 0: very conservative(?) reply, 2+: very diverse reply std: 0.9
            }, 
        # "context": context_val,
        "stream": False,
        "raw": False,
    }

    ip_address = open(f'{current_dir}/lib/ip.txt', 'r').read()
    cmd = ['curl', '-s', f'http://{ip_address}:11434/api/generate', '-d', json.dumps(data)]

    # print(cmd)
    # print("------------------")

    return cmd

def send_curl(curl_cmd, current_dir):
    #print(curl_cmd)
    #print()
    try:
        process = subprocess.run(curl_cmd, shell=False, check=True, stdout=subprocess.PIPE, universal_newlines=True)
    except Exception as e:
        if e.returncode == 7:
            return "code 7"
        else:
            print(f"----------\nError: \n{e}\n----------")
    output_json = json.loads(process.stdout)

    # print(output_json)
    # print()
    response = output_json["response"].strip()

    open(f'{current_dir}/lib/context.txt', 'a').write(f"EXPERT: {response}\n")
    
    return response

def get_ip(hostname):
    ip_address = socket.gethostbyname(hostname)
    return ip_address

