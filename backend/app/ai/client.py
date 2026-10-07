"""The one place the model client is built: GPT-5.6 Luna on our Microsoft Foundry
resource, through the OpenAI SDK's Responses API (Foundry's v1 endpoint).

Switching model is a settings change (AI_MODEL = another deployment's name on
the same resource), as long as it speaks the Responses API.
"""
from openai import OpenAI

from .. import config


def configured() -> bool:
    return bool(config.FOUNDRY_RESOURCE and config.FOUNDRY_API_KEY)


def provider_name() -> str:
    return "Microsoft Foundry"


def make_client() -> OpenAI:
    return OpenAI(
        base_url=f"https://{config.FOUNDRY_RESOURCE}.openai.azure.com/openai/v1/",
        api_key=config.FOUNDRY_API_KEY,
        timeout=300,
        max_retries=2,
    )


def cost_usd(model: str, usage) -> float:
    """Responses API usage: input_tokens includes the cached ones."""
    inp, out, cached = config.AI_PRICES.get(model, config.AI_PRICES[config.DEFAULT_AI_MODEL])
    details = getattr(usage, "input_tokens_details", None)
    cached_tokens = (getattr(details, "cached_tokens", 0) or 0) if details else 0
    fresh = (usage.input_tokens or 0) - cached_tokens
    return round((fresh * inp + cached_tokens * cached + (usage.output_tokens or 0) * out) / 1_000_000, 6)
