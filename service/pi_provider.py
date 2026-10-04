"""LangExtract transport to the private model bridge owned by a Pi run.

The upstream model remains in Node's Pi ModelRuntime. Windows system proxies
must not intercept this loopback connection, and HTTP retries must not silently
repeat a completed, billed inference after a transport timeout.
"""
from urllib.parse import urlparse

import httpx
from openai import OpenAI
from langextract.factory import ModelConfig
from langextract.providers import router
from langextract.providers.openai import OpenAILanguageModel


TRANSPORT_VERSION = "pi-loopback-direct-1"


@router.register(r"^pi-private-bridge$", priority=100)
class PiBridgeLanguageModel(OpenAILanguageModel):
    def __init__(self, **kwargs):
        address = urlparse(kwargs.get("base_url") or "")
        if (address.scheme != "http" or address.hostname not in {"127.0.0.1", "localhost", "::1"}
                or address.username or address.password or not kwargs.get("api_key")):
            raise ValueError("pi_runtime_bridge_required")
        super().__init__(**kwargs)
        self._client.close()
        self._client = OpenAI(
            api_key=self.api_key, base_url=self.base_url,
            http_client=httpx.Client(trust_env=False, timeout=httpx.Timeout(600, connect=10)),
            timeout=600, max_retries=0,
        )


def pi_model_config(runtime, **inference):
    return ModelConfig(model_id=runtime["model"], provider="PiBridgeLanguageModel",
                       provider_kwargs={"api_key": runtime["api_key"], "base_url": runtime["base_url"], **inference})
