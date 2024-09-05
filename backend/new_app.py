from flask import Flask, request, send_file, jsonify, sessions
from flask_cors import CORS
# from elevenlabs import generate, set_api_key, voices, save
from elevenlabs.client import ElevenLabs
import os
import uuid
import numpy
import librosa
import openai
import time
import logging
# import whisper
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
CORS(app)
# set_api_key(os.getenv("ELEVEN_KEY"))
client = ElevenLabs(api_key=os.getenv("ELEVEN_KEY"))
app.secret_key = os.getenv("SECRET_KEY")
openai.api_key = os.getenv("OPENAI_API_KEY")
# model = whisper.load_model("base")

audio_path = "audio"
if not os.path.exists(audio_path):
    os.makedirs(audio_path)
else:
    current_time = time.time()
    for file in os.listdir(audio_path):
        file_path = os.path.join(audio_path, file)
        file_time = os.path.getmtime(file_path)
        if current_time - file_time > 300:
            os.remove(file_path)


# @app.route("/convert", methods=["POST"])
# def convert():
#     audio_file = request.files.get("audio")
#     if audio_file:
#         file_name = str(uuid.uuid4()) + ".wav"
#         file_path = os.path.join(audio_path, file_name)
#         audio_file.save(file_path)
#         data, sampleRate = librosa.load(file_path)
#         result = model.transcribe(numpy.array(data), language="en")
#         print(result["text"])
#         return result["text"]
#     else:
#         return jsonify("Invalid audio file.")

# " generates chat and audio response from text"
@app.route("/chat", methods=["POST"])
def chat():
    audio_file = request.files.get("audio")
    if audio_file:
        file_name = str(uuid.uuid4()) + ".wav"
        file_path = os.path.join(audio_path, file_name)
        audio_file.save(file_path)
        data, sampleRate = librosa.load(file_path)
        user_text = model.transcribe(numpy.array(data))["text"]

        if "messages" not in session:
            session["messages"] = []

        session["messages"].append({"role": "user", "content": user_text})
        if len(session["messages"]) > 10:
            session["messages"].pop(0)

        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=session["messages"]
        )

        chatbot_message = completion.choices[0].message.content

        session["messages"].append({"role": "assistant", "content": chatbot_message})
        if len(session["messages"]) > 10:
            session["messages"].pop(0)

        # Convert text to speech
        audio = generate(text=chatbot_message, voice=voices()[-1])
        chat_file_name = str(uuid.uuid4()) + ".wav"
        save(audio=audio, filename=os.path.join(audio_path, chat_file_name))
        return jsonify(
            {"user": user_text, "chat": chatbot_message, "audioSrc": chat_file_name}
        )
    else:
        return jsonify({"chat": ["Invalid audio file."]}), 400


@app.route("/post-query", methods=["POST"])
def post_query():
    # take the text
    app.logger.debug(f"Request data: {request.json}")
    data = request.get_json()
    # query = data["query"]
    # generate the openai response
    return jsonify({"query": "query"})

    # return jsonify({"query": query})

# " generates speech from text"
# @app.route("/generate", methods=["POST"])
# def generate_elevenlabs():
#     data = request.get_json()
#     text = data["text"]
#     audio = generate(text=text, voice=voices()[-1])
#     file_name = "speech.wav"
#     save(audio=audio, filename=os.path.join("audio", file_name))
#     return file_name


@app.route("/<file_name>")
def get_file(file_name):
    return send_file(os.path.join("audio", file_name), as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)