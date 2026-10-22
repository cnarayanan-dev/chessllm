from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter

from chessllm.api.deps import ConfigDep, EnginesDep
from chessllm.api.errors import error_responses
from chessllm.api.schemas.models import ModelInfo
from chessllm.core.types import Sampling
from chessllm.exceptions import InvalidSamplingConfig
from chessllm.llm.models import LlmModel, load_sampling

router = APIRouter()


@router.get("/api/models", responses=error_responses(InvalidSamplingConfig))
def list_models(config: ConfigDep, engines: EnginesDep) -> list[ModelInfo]:
    """Each model with the sampling it would play at: its own defaults, overridden by the config file.

    The sampling is None when Ollama can't show the model, e.g. when it isn't installed."""
    sampling_config = load_sampling(config.sampling_file)

    def sampling(model: LlmModel) -> Sampling | None:
        try:
            return engines.sampling_defaults(model.name) | sampling_config
        except Exception:
            return None

    # The models are asked at once, so a stalled Ollama holds the list up for one timeout, not one per model.
    with ThreadPoolExecutor() as pool:
        samplings = list(pool.map(sampling, engines.models))
    return [
        ModelInfo(name=model.name, thinking=model.thinking, sampling=model_sampling)
        for model, model_sampling in zip(engines.models, samplings)
    ]
