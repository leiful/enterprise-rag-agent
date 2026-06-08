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
    if isinstance(error, AuthenticationError):
        return "Model request error: authentication failed. Check DEEPSEEK_API_KEY in .env."
    if isinstance(error, RateLimitError):
        return "Model request error: rate limit reached. Wait a moment and try again."
    if isinstance(error, BadRequestError):
        return f"Model request error: bad request. {error}"
    if isinstance(error, APIConnectionError):
        return f"Model request error: connection failed. {error}"
    if isinstance(error, APIStatusError):
        return f"Model request error: API returned status {error.status_code}. {error}"
    if isinstance(error, APIError):
        return f"Model request error: API error. {error}"
    return f"Model request error: {error}"
