import cgi
import http.server
import math
import os
import socketserver
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import FileIO
from flask import Flask, send_file, request
from flask_cors import CORS, cross_origin

import openai
from imaginairy import config
from imaginairy.cli.shared import (ImagineColorsCommand, _imagine_cmd,
                                   add_options, common_options)

app = Flask(__name__)
cors = CORS(app)

openai.api_key = "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"

directories = [os.path.abspath("./.temp"), os.path.abspath("./.temp/outputs"), os.path.abspath("./.temp/controls")]
for directory in directories:
    if not os.path.exists(directory):
        os.makedirs(directory)

def describe_prompt(furniture, description):
    prompt = f"You are a professional interior designer. \
        Explain in a clear and concise manner of the interior design of a room containing the following furnitures:\n\"{furniture}\"\n\nThe room and the furniture arragements should be described as follows:\n{description}. \
        You should mention that the furniture is in the room. \
        You should also describe the position of each furnitures in the room. \
        Do not mention furnitures that are not in the given list.\
        You should also tell the bot that it should not add any furnitures that are not in the given list.\
        "
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": prompt}
        ],
        temperature=0.8,
    )
    return response.choices[0]['message']['content']

class DalleFurniture:
    def __init__(self, prompt: str, control_image_path: str, timestamp: str):
        self.prompt = prompt
        self.control_image_path = control_image_path
        self.timestamp = timestamp
        
    def run(self) -> str:
        # TODO: Alternative method
        return
        
class ImagineFurniture(DalleFurniture):
    def __init__(self, prompt: str, control_image_path: str, timestamp: str):
        super().__init__(prompt, control_image_path, timestamp)
        
    def run(self) -> str:
        allow_compose_phase = True
        arg_schedules = None
        caption = False
        caption_text = None
        control_image = None
        control_image_raw = None
        control_mode = ""
        fix_faces = False
        fix_faces_fidelity = None
        height = None
        init_image = self.control_image_path
        init_image_strength = .1
        make_compare_gif = False
        make_gif = False
        mask_image = None
        mask_mode = "keep"
        mask_modify_original = True
        mask_prompt = "ceiling OR crossbeam OR beam OR structure OR windows"
        model_config_path = None
        model_weights_path = config.DEFAULT_MODEL
        negative_prompt = None
        outdir = f"./.temp/outputs/{self.timestamp}"
        outpaint = ""
        output_file_extension = "jpg"
        precision = "autocast"
        prompt_library_path = None
        prompt_strength = 9
        prompt_texts = [self.prompt]
        repeats = 1
        sampler_type = config.DEFAULT_SAMPLER
        seed = None
        show_work = False
        steps = False
        tile = False
        tile_x = False
        tile_y = False
        upscale = False
        width = None

        if isinstance(init_image, str):
            init_images = [init_image]
        else:
            init_images = init_image

        from imaginairy.utils import glob_expand_paths

        init_images = glob_expand_paths(init_images)

        total_image_count = len(prompt_texts) * max(len(init_images), 1) * repeats

        from imaginairy import ImaginePrompt, LazyLoadingImage, imagine_image_files

        new_init_images = []
        for _init_image in init_images:
            if _init_image and _init_image.startswith("http"):
                _init_image = LazyLoadingImage(url=_init_image)
            new_init_images.append(_init_image)
        init_images = new_init_images
        if not init_images:
            init_images = [None]

        prompts = []
        prompt_expanding_iterators = {}
        from imaginairy.enhancers.prompt_expansion import expand_prompts

        for _ in range(repeats):
            for prompt_text in prompt_texts:
                if prompt_text not in prompt_expanding_iterators:
                    prompt_expanding_iterators[prompt_text] = expand_prompts(
                        n=math.inf,
                        prompt_text=prompt_text,
                        prompt_library_paths=prompt_library_path,
                    )
                prompt_iterator = prompt_expanding_iterators[prompt_text]
                if tile:
                    _tile_mode = "xy"
                elif tile_x:
                    _tile_mode = "x"
                elif tile_y:
                    _tile_mode = "y"
                else:
                    _tile_mode = ""
                for _init_image in init_images:
                    prompt = ImaginePrompt(
                        next(prompt_iterator),
                        negative_prompt=negative_prompt,
                        prompt_strength=prompt_strength,
                        init_image=_init_image,
                        init_image_strength=init_image_strength,
                        control_image=control_image,
                        control_image_raw=control_image_raw,
                        control_mode=control_mode,
                        seed=seed,
                        sampler_type=sampler_type,
                        steps=steps,
                        height=height,
                        width=width,
                        mask_image=mask_image,
                        mask_prompt=mask_prompt,
                        mask_mode=mask_mode,
                        mask_modify_original=mask_modify_original,
                        outpaint=outpaint,
                        upscale=upscale,
                        fix_faces=fix_faces,
                        fix_faces_fidelity=fix_faces_fidelity,
                        tile_mode=_tile_mode,
                        allow_compose_phase=allow_compose_phase,
                        model=model_weights_path,
                        model_config_path=model_config_path,
                        caption_text=caption_text,
                    )
                    from imaginairy.prompt_schedules import (
                        parse_schedule_strs,
                        prompt_mutator,
                    )

                    if arg_schedules:
                        schedules = parse_schedule_strs(arg_schedules)
                        for new_prompt in prompt_mutator(prompt, schedules):
                            prompts.append(new_prompt)
                    else:
                        prompts.append(prompt)

        filenames = imagine_image_files(
            prompts,
            outdir=outdir,
            record_step_images=show_work,
            output_file_extension=output_file_extension,
            print_caption=caption,
            precision=precision,
            make_gif=make_gif,
            make_compare_gif=make_compare_gif,
        )

        horizontal_flip(filenames[0])
        
        return filenames[0]


@app.post('/imagine-furniture')
@cross_origin()
def imagine_furniture():
    print("/imagine_furniture")
    timestamp = str(time.time())
    file = request.files.get("file")
    file_bytes: bytes = file.stream.read()
    file_path = rf'.temp/controls/control-image-{timestamp}.jpg'
    with open(file_path, 'wb+') as f:
        f.write(file_bytes)

    furniture = request.form.get("furniture", "<empty>")
    description = request.form.get("description", "<no description>")
    print('furniture', furniture, 'description', description)
    prompt = describe_prompt(furniture, description)
    print(prompt)
    
    imagine = ImagineFurniture(prompt, file_path, timestamp)
    file = imagine.run()

    return f"http://192.168.100.90:80/file/{timestamp}"


def horizontal_flip(path):
    # importing PIL Module
    from PIL import Image
    # open the original image
    original_img = Image.open(path)
    # Flip the original image horizontally
    horz_img = original_img.transpose(method=Image.FLIP_LEFT_RIGHT)
    horz_img.save(path)
    # close all our files object
    original_img.close()
    horz_img.close()


@app.post("/test")
@cross_origin()
def test():
    timestamp = "1681796676.7124608"
    file = request.files.get("file")
    file_bytes: bytes = file.stream.read()
    file_path = rf'.temp/controls/control-image-{timestamp}.jpg'
    with open(file_path, 'wb+') as f:
        f.write(file_bytes)

    furniture = request.form.get("furniture", "<empty>")
    description = request.form.get("description", "<no description>")
    prompt = describe_prompt(furniture, description)

    print(prompt)
    return f"http://192.168.100.90:80/file/{timestamp}"

    
@app.get("/")
@cross_origin()
def home():
    return "Hello World!"
    
    
@app.get("/file/<file_id>")  
@cross_origin()
def file(file_id):  
    file_dir = f".temp/outputs/{file_id}/generated"
    file_name = os.listdir(file_dir)[0]
    return send_file(os.path.join(file_dir, file_name))

app.run(port=80, host="0.0.0.0")
