# -*- coding: utf-8 -*-

import os

from langchain_openai import ChatOpenAI
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from config import BASE_URL, MODEL


def create_client():
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY. Please set it in .env.")

    return ChatOpenAI(
        model=MODEL,
        api_key=api_key,
        base_url=BASE_URL,
        temperature=0,
    )


def format_model_error(error):
    return "AI 服务暂时不可用，请稍后再试。"
