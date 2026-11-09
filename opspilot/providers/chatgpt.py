"""ChatGPT-plan Responses transport; domain tools stay inside OpsPilot."""

import json
import time

import httpx

from opspilot.domain.models import Usage
from opspilot.providers.chat_api import ChatAPI, ProviderError
from opspilot.providers.chatgpt_auth import API, ChatGPTAccounts, SubscriptionError


class ChatGPTSubscription(ChatAPI):
    """Reuse the existing planner/selector prompts, replacing only HTTP transport."""

    def __init__(self, settings, accounts: ChatGPTAccounts, profile_id: str, client=None):
        super().__init__(settings, client)
        self.accounts = accounts
        self.profile_id = profile_id

    def complete(self, system, payload, schema):
        self.last_observation = {
            "http_status": None,
            "input_tokens": None,
            "output_tokens": None,
            "request_started": False,
            "error_type": None,
        }
        token = self.accounts.access_token(self.profile_id)
        body = {
            "model": self.settings.llm_model,
            "instructions": system
            + "\nReturn JSON matching this schema: "
            + json.dumps(schema.model_json_schema()),
            "input": [
                {
                    "role": "developer",
                    "content": "Return only JSON matching the response schema in the instructions.",
                },
                {"role": "user", "content": json.dumps(payload)},
            ],
            "store": False,
            "stream": True,
            "text": {"format": {"type": "json_object"}},
        }
        owned = self.client is None
        client = self.client or httpx.Client(trust_env=False, follow_redirects=False)
        started = time.monotonic()
        output, completed, size = [], None, 0
        try:
            # Do not retry a possibly billed inference or switch billing paths.
            self.last_observation["request_started"] = True
            with client.stream(
                "POST",
                API + "/responses",
                json=body,
                headers={"Authorization": "Bearer " + token},
                timeout=self.settings.subscription_timeout_seconds,
            ) as response:
                self.last_observation["http_status"] = response.status_code
                if response.status_code >= 300:
                    raise SubscriptionError(
                        f"ChatGPT request rejected (HTTP {response.status_code}); "
                        "review the account, model and ChatGPT Settings → Usage."
                    )
                event_data = []
                for line in response.iter_lines():
                    size += len(line)
                    if size > 524288 or time.monotonic() - started > 120:
                        raise SubscriptionError("ChatGPT response exceeded the local limit.")
                    if line.startswith("data:"):
                        event_data.append(line[5:].lstrip())
                    if line or not event_data:
                        continue
                    raw = "\n".join(event_data)
                    event_data.clear()
                    if raw == "[DONE]":
                        continue
                    event = json.loads(raw)
                    kind = event.get("type")
                    if kind == "response.output_text.delta":
                        output.append(event["delta"])
                    elif kind in {"error", "response.failed", "response.incomplete"}:
                        error = event.get("error") or event.get("response", {}).get("error") or {}
                        error_type = error.get("type")
                        self.last_observation["error_type"] = (
                            error_type
                            if error_type
                            in {
                                "invalid_request_error",
                                "authentication_error",
                                "permission_error",
                                "rate_limit_error",
                                "server_error",
                            }
                            else "unknown"
                        )
                        if error_type == "invalid_request_error":
                            raise SubscriptionError(
                                "ChatGPT rejected the request format; check subscription adapter "
                                "settings. No partial generated answer was accepted."
                            )
                        raise SubscriptionError(
                            "ChatGPT did not complete the response; "
                            "review ChatGPT Settings → Usage "
                            "or reconnect. No partial generated answer was accepted."
                        )
                    elif kind == "response.completed":
                        completed = event["response"]
                if completed is None or completed.get("status") != "completed":
                    raise SubscriptionError("ChatGPT stream ended without a completed response.")
                # Use only assistant text; never expose reasoning events.
                final_text = "".join(
                    part["text"]
                    for item in completed.get("output", [])
                    if item.get("type") == "message" and item.get("role") == "assistant"
                    for part in item.get("content", [])
                    if part.get("type") == "output_text"
                )
                raw_usage = completed.get("usage") or {}
                self.last_observation.update(
                    input_tokens=raw_usage.get("input_tokens"),
                    output_tokens=raw_usage.get("output_tokens"),
                )
                result = schema.model_validate_json(final_text or "".join(output))
                usage = Usage(
                    input_tokens=raw_usage.get("input_tokens", 0),
                    output_tokens=raw_usage.get("output_tokens", 0),
                )
                return result, usage
        except httpx.HTTPError:
            raise ProviderError(
                "ChatGPT connection interrupted; no partial answer accepted."
            ) from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("ChatGPT returned invalid structured output.") from None
        finally:
            if owned:
                client.close()
