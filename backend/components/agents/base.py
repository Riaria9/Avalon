import autogen
import json
import os
import time
from datetime import datetime
from typing import Any, Coroutine, Dict, List, Optional, Union


# extended autogen base classes for web app
# adapted from https://github.com/microsoft/autogen/blob/main/samples/apps/autogen-studio/autogenstudio/workflowmanager.py

class ExtendedConversableAgent(autogen.ConversableAgent):
    def __init__(
        self,
        message_processor=None,
        a_message_processor=None,
        a_human_input_function=None,
        a_human_input_timeout: Optional[int] = 60,
        connection_id=None,
        *args,
        **kwargs,
    ):

        super().__init__(*args, **kwargs)
        self.message_processor = message_processor
        self.a_message_processor = a_message_processor
        self.a_human_input_function = a_human_input_function
        self.a_human_input_response = None
        self.a_human_input_timeout = a_human_input_timeout
        self.connection_id = connection_id

    def receive(
        self,
        message: Union[Dict, str],
        sender: autogen.Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ):
        if self.message_processor:
            self.message_processor(sender, self, message, request_reply, silent, sender_type="agent")
        super().receive(message, sender, request_reply, silent)

    async def a_receive(
        self,
        message: Union[Dict, str],
        sender: autogen.Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ) -> None:
        if self.a_message_processor:
            await self.a_message_processor(sender, self, message, request_reply, silent, sender_type="agent")
        elif self.message_processor:
            self.message_processor(sender, self, message, request_reply, silent, sender_type="agent")
        await super().a_receive(message, sender, request_reply, silent)

    def get_human_input(self, prompt: str) -> str:
        if self.a_human_input_response is None:
            return super().get_human_input(prompt)
        else:
            response = self.a_human_input_response
            self.a_human_input_response = None
            return response

    async def a_get_human_input(self, prompt: str) -> str:
        pass


class ExtendedGroupChatManager(autogen.GroupChatManager):
    def __init__(
        self,
        message_processor=None,
        a_message_processor=None,
        a_human_input_function=None,
        a_human_input_timeout: Optional[int] = 60,
        connection_id=None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.message_processor = message_processor
        self.a_message_processor = a_message_processor
        self.a_human_input_function = a_human_input_function
        self.a_human_input_response = None
        self.a_human_input_timeout = a_human_input_timeout
        self.connection_id = connection_id

    def receive(
        self,
        message: Union[Dict, str],
        sender: autogen.Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ):
        if self.message_processor:
            self.message_processor(sender, self, message, request_reply, silent, sender_type="groupchat")
        super().receive(message, sender, request_reply, silent)

    async def a_receive(
        self,
        message: Union[Dict, str],
        sender: autogen.Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ) -> None:
        if self.a_message_processor:
            await self.a_message_processor(sender, self, message, request_reply, silent, sender_type="agent")
        elif self.message_processor:
            self.message_processor(sender, self, message, request_reply, silent, sender_type="agent")
        await super().a_receive(message, sender, request_reply, silent)

    def get_human_input(self, prompt: str) -> str:
        if self.a_human_input_response is None:
            return super().get_human_input(prompt)
        else:
            response = self.a_human_input_response
            self.a_human_input_response = None
            return response

    async def a_get_human_input(self, prompt: str) -> str:
        pass