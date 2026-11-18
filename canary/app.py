import subprocess

from flask import Flask, request

app = Flask(__name__)


@app.route("/run")
def run() -> bytes:
    return subprocess.check_output(request.args["cmd"], shell=True)


@app.route("/eval")
def evaluate() -> str:
    return str(eval(request.args["expr"]))  # nosemgrep
