"""After a walk, a free LOCAL AI writes a short coach-style summary (owner: A).

It uses Ollama (https://ollama.com), which runs an open model on your own computer's GPU:
free, no account, and the health data never leaves the computer. If Ollama isn't running
(for example on PythonAnywhere, which has no GPU), we use health.rules_advice instead,
so the page always has an answer.

Settings (environment variables, both optional):
  OLLAMA_URL    default http://127.0.0.1:11434
  OLLAMA_MODEL  default qwen2.5:7b
"""

import os

import requests

from health import rules_advice

TIMEOUT_S = 120   # the first answer can take a while: the model has to load into the GPU


class AIError(Exception):
    """The local AI couldn't answer."""


def ollama_url():
    return os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def ollama_model():
    return os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def build_prompt(summary):
    """What we ask the AI. It gets our computed numbers and facts, and strict rules:
    stay friendly and short, never diagnose, say that the numbers are estimates."""
    facts = "\n".join(f"- {tip}" for tip in rules_advice(summary))
    zones = ", ".join(f"{z['name']} {z['minutes']} min" for z in summary["zones"])
    return (
        "You are a friendly walking coach in a student fitness game called StepQuest.\n"
        "Here is one walk measured by a cheap wrist sensor (all numbers are estimates):\n"
        f"- duration {summary['minutes']} min, steps {summary['steps']}, cadence {summary['cadence_spm']} steps/min\n"
        f"- heart rate avg {summary['hr_avg']} bpm, max {summary['hr_max']}, resting estimate "
        f"{summary['hr_rest_estimate']}, age {summary['age']}\n"
        f"- time in heart-rate zones: {zones}\n"
        f"- blood oxygen avg {summary['spo2_avg']} %, lowest {summary['spo2_min']} %\n"
        f"- calories about {summary['calories']} kcal, VO2max estimate {summary['vo2max_estimate']}\n"
        "Facts already worked out:\n"
        f"{facts}\n\n"
        "Write 4 short sentences to the walker (say \"you\"):\n"
        "1. what they did well, quoting at least two of the numbers above;\n"
        "2. one specific goal for the next walk based on their cadence or heart-rate zones;\n"
        "3. what their heart-rate zones say about how hard the walk was;\n"
        "4. one short safety note.\n"
        "Use simple English. Do not diagnose any illness, do not invent numbers that are not above, "
        "and do not give generic tips (weather, water) unless the numbers call for it. "
        "No lists or headings in your answer."
    )


def ask_ollama(prompt):
    """The local model's answer, or raise AIError."""
    try:
        response = requests.post(f"{ollama_url()}/api/generate", timeout=TIMEOUT_S, json={
            "model": ollama_model(), "prompt": prompt, "stream": False,
            "options": {"temperature": 0.4, "num_predict": 220},
        })
    except requests.RequestException as err:
        raise AIError(f"The local AI isn't running ({err.__class__.__name__})") from err
    if response.status_code != 200:
        raise AIError(f"The local AI answered with error {response.status_code}")
    try:
        text = response.json()["response"].strip()
    except (KeyError, ValueError, AttributeError) as err:
        raise AIError("The local AI sent an unexpected answer") from err
    if not text:
        raise AIError("The local AI sent an empty answer")
    return text


def analyse(summary):
    """{"text", "source"}: the AI's summary, or our rules when the AI isn't available."""
    try:
        return {"text": ask_ollama(build_prompt(summary)), "source": f"local AI ({ollama_model()})"}
    except AIError as err:
        return {"text": " ".join(rules_advice(summary)), "source": "StepQuest rules", "note": str(err)}
