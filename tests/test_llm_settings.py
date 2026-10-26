"""configs/llm.yaml is the single place where the advisor's settings are set."""

from cotraffic.llm.advised import AdvisorConfig
from cotraffic.llm.client import Options
from cotraffic.llm.prompts import load
from cotraffic.llm.settings import load_settings


def test_code_defaults_match_the_settings_file():  # [Exigence 3]
    settings = load_settings()
    assert Options() == settings.options
    assert AdvisorConfig() == settings.advisor


def test_settings_are_complete_and_bounded():
    s = load_settings()
    assert s.model and s.quantization and s.options.keep_alive
    assert s.options.temperature == 0 and s.options.top_k == 1  # greedy: reproducible
    assert 0 < s.options.num_predict <= 200 and s.options.timeout_s <= 120
    assert 0 < s.advisor.beta <= 8 and s.advisor.period_s >= 60
    assert load(s.prompt_version, s.technique).version == s.prompt_version
