import os
import logging

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
)

logger = logging.getLogger(__name__)

_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])


def _api() -> MessagingApi:
    return MessagingApi(ApiClient(_config))


def reply(reply_token: str, text: str):
    try:
        _api().reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(type="text", text=text)],
            )
        )
    except Exception as e:
        logger.error("reply error: %s", e)


def push(user_id: str, text: str):
    try:
        _api().push_message(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessage(type="text", text=text)],
            )
        )
    except Exception as e:
        logger.error("push error to %s: %s", user_id, e)
