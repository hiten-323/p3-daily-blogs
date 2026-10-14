"""Platform-native growth engine prompts. The gate in core/growth_engine.py enforces them."""
from content_generator.prompts.growth_engine.platforms import generation_preface, prompt_block

__all__ = ["generation_preface", "prompt_block"]
