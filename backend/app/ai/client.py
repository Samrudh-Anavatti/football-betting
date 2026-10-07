"""The one place a Claude client is built. Microsoft Foundry when FOUNDRY_* is
set (billed through Azure), otherwise Anthropic's API if ANTHROPIC_API_KEY is.
Everything else uses the same messages API, so switching is a settings change."""
import anthropic

from .. import config


def configured() -> bool:
    return bool((config.FOUNDRY_RESOURCE and config.FOUNDRY_API_KEY) or config.ANTHROPIC_API_KEY)


def provider_name() -> str:
    return "Microsoft Foundry" if config.FOUNDRY_RESOURCE and config.FOUNDRY_API_KEY else "Anthropic API"


def make_client() -> anthropic.Anthropic:
    if config.FOUNDRY_RESOURCE and config.FOUNDRY_API_KEY:
        return anthropic.AnthropicFoundry(api_key=config.FOUNDRY_API_KEY, resource=config.FOUNDRY_RESOURCE,
                                          timeout=300, max_retries=2)
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=300, max_retries=2)


def cost_usd(model: str, usage) -> float:
    inp, out, cache_write, cache_read = config.AI_PRICES.get(model, config.AI_PRICES["claude-sonnet-5-5"])
    return round((
        (usage.input_tokens or 0) * inp
        + (usage.output_tokens or 0) * out
        + (usage.cache_creation_input_tokens or 0) * cache_write
        + (usage.cache_read_input_tokens or 0) * cache_read
    ) / 1_000_000, 6)
