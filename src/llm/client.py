import logging

from openai import AzureOpenAI

logger = logging.getLogger(__name__)


class AzureOpenAIClient:
    """Wrapper around Azure OpenAI for fraud analysis."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = "2024-10-21",
    ):
        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        self._deployment = deployment
        logger.info(
            "AzureOpenAIClient initialized: endpoint=%s, deployment=%s",
            endpoint, deployment,
        )

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 1.0,
    ) -> str:
        """Send a chat completion request and return the response content."""
        try:
            response = self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=512,
            )
            content = response.choices[0].message.content or ""
            logger.debug("LLM response received (%d chars)", len(content))
            return content
        except Exception:
            logger.exception("Azure OpenAI chat request failed")
            raise
