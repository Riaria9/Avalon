from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Type, TypeVar, Union
import logger
import inspect
from dataclasses import dataclass

from autogen import ConversableAgent, Agent
from autogen.runtime_logging import log_event, log_function_use, log_new_agent, logging_enabled



@dataclass
class PlayerMessage:
    content: str
    turn: int
    msg_type: str = "text"


# TODO: need to change to ExtendedConversableAgent for web app and impelment async functions
# Note: The default generate_reply function only supports getting chat histroy from one agent, but in avalon, 
# it is common for multiple agents to chat to the agent and than generate reply -> I override the generate_reply function as a naive solution

## Note: I chose not to use the GroupChatManager class from autogen for multi-agent communication, 
# as it provides limited control over individual agent actions within the group chat.

class Player(ConversableAgent):
    def __init__(self, *args, **kwargs):
        # Check for required fields and raise an error if any are missing
        if 'name' not in kwargs:
            raise ValueError("Missing required argument: 'name'")
        if 'role_desc' not in kwargs:
            raise ValueError("Missing required argument: 'role_desc'")
        if 'global_prompt' not in kwargs:
            raise ValueError("Missing required argument: 'global_prompt'")

        # Extract the necessary values from kwargs
        name = kwargs['name']
        role_desc = kwargs.pop('role_desc') 
        global_prompt = kwargs.pop('global_prompt')

        # Create the system message
        system_message = '\n'.join([
            kwargs.get('system_message', ''),
            'You are a helpful assistant.',
            f'{global_prompt.strip()}',
            f'Your name is {name}.',
            f'You are a player with a role "{role_desc}".'
        ])

        # Update kwargs with the system message
        kwargs['system_message'] = system_message
        
        # Call the superclass initializer
        super().__init__(*args, **kwargs)
        
        # Assign attributes
        self.role_desc = role_desc
        self.all_messages = []


    def get_visible_message(self, **kwargs):
        """
        TODO: Get visible history messages for the agent.
        Please visit the "MessagePool" class in the modified version of Chatarena from the stakeholder for reference.
        eg. we may want to remove some messages from old rounds
        
        Placeholder logic: Returns a list of all message contents.
        """
        placeholder = []

        # Iterate through all messages and collect their content
        for message in self.all_messages:
            placeholder.append(message.content)
        return placeholder


    def send(
        self,
        message: Union[Dict, str],
        recipient: Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
        **kwargs
    ):
        """Send a message to another agent.

        Args:
            message (dict or str): message to be sent.
                The message could contain the following fields:
                - content (str or List): Required, the content of the message. (Can be None)
                - function_call (str): the name of the function to be called.
                - name (str): the name of the function to be called.
                - role (str): the role of the message, any role that is not "function"
                    will be modified to "assistant".
                - context (dict): the context of the message, which will be passed to
                    [OpenAIWrapper.create](../oai/client#create).
                    For example, one agent can send a message A as:
        ```python
        {
            "content": lambda context: context["use_tool_msg"],
            "context": {
                "use_tool_msg": "Use tool X if they are relevant."
            }
        }
        ```
                    Next time, one agent can send a message B with a different "use_tool_msg".
                    Then the content of message A will be refreshed to the new "use_tool_msg".
                    So effectively, this provides a way for an agent to send a "link" and modify
                    the content of the "link" later.
            recipient (Agent): the recipient of the message.
            request_reply (bool or None): whether to request a reply from the recipient.
            silent (bool or None): (Experimental) whether to print the message sent.

        Raises:
            ValueError: if the message can't be converted into a valid ChatCompletion message.
        """
        message = self._process_message_before_send(message, recipient, ConversableAgent._is_silent(self, silent))
        # When the agent composes and sends the message, the role of the message is "assistant"
        # unless it's "function".
        valid = self._append_oai_message(message, "assistant", recipient, is_sending=True, **kwargs) #Note: added **kwargs
        if valid:
            recipient.receive(message, self, request_reply, silent)
        else:
            raise ValueError(
                "Message can't be converted into a valid ChatCompletion message. Either content or function_call must be provided."
            )


    def _append_oai_message(self, message: Union[Dict, str], role, conversation_id: Agent, is_sending: bool, **kwargs) -> bool:
        """Append a message to the ChatCompletion conversation.

        If the message received is a string, it will be put in the "content" field of the new dictionary.
        If the message received is a dictionary but does not have any of the three fields "content", "function_call", or "tool_calls",
            this message is not a valid ChatCompletion message.
        If only "function_call" or "tool_calls" is provided, "content" will be set to None if not provided, and the role of the message will be forced "assistant".

        Args:
            message (dict or str): message to be appended to the ChatCompletion conversation.
            role (str): role of the message, can be "assistant" or "function".
            conversation_id (Agent): id of the conversation, should be the recipient or sender.
            is_sending (bool): If the agent (aka self) is sending to the conversation_id agent, otherwise receiving.

        Returns:
            bool: whether the message is appended to the ChatCompletion conversation.
        """
        message = self._message_to_dict(message)
        # create oai message to be appended to the oai conversation that can be passed to oai directly.
        oai_message = {
            k: message[k]
            for k in ("content", "function_call", "tool_calls", "tool_responses", "tool_call_id", "name", "context")
            if k in message and message[k] is not None
        }
        if "content" not in oai_message:
            if "function_call" in oai_message or "tool_calls" in oai_message:
                oai_message["content"] = None  # if only function_call is provided, content will be set to None.
            else:
                return False

        if message.get("role") in ["function", "tool"]:
            oai_message["role"] = message.get("role")
        elif "override_role" in message:
            # If we have a direction to override the role then set the
            # role accordingly. Used to customise the role for the
            # select speaker prompt.
            oai_message["role"] = message.get("override_role")
        else:
            oai_message["role"] = role

        if oai_message.get("function_call", False) or oai_message.get("tool_calls", False):
            oai_message["role"] = "assistant"  # only messages with role 'assistant' can have a function call.
        elif "name" not in oai_message:
            # If we don't have a name field, append it
            if is_sending:
                oai_message["name"] = self.name
            else:
                oai_message["name"] = conversation_id.name

        self._oai_messages[conversation_id].append(oai_message)

        #Note: changed for avalon
        if role == "user": # append only when receive a message
            msg_type = kwargs.get("msg_type", "txt")
            turn = kwargs.get("turn", -1)
            message = PlayerMessage(content=oai_message, turn=turn, msg_type=msg_type)
            self.all_messages.append(message)

        return True



    def generate_reply(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        sender: Optional["Agent"] = None,
        **kwargs: Any,
    ) -> Union[str, Dict, None]:
        """Reply based on the conversation history and the sender.

        Either messages or sender must be provided.
        Register a reply_func with `None` as one trigger for it to be activated when `messages` is non-empty and `sender` is `None`.
        Use registered auto reply functions to generate replies.
        By default, the following functions are checked in order:
        1. check_termination_and_human_reply
        2. generate_function_call_reply (deprecated in favor of tool_calls)
        3. generate_tool_calls_reply
        4. generate_code_execution_reply
        5. generate_oai_reply
        Every function returns a tuple (final, reply).
        When a function returns final=False, the next function will be checked.
        So by default, termination and human reply will be checked first.
        If not terminating and human reply is skipped, execute function or code and return the result.
        AI replies are generated only when no code execution is performed.

        Args:
            messages: a list of messages in the conversation history.
            sender: sender of an Agent instance.

        Additional keyword arguments:
            exclude (List[Callable]): a list of reply functions to be excluded.

        Returns:
            str or dict or None: reply. None if no reply is generated.
        """
        if all((messages is None, sender is None)):
            # Note: changed for avalon
            turn = kwargs.get("turn", -1)
            messages = self.get_visible_message(turn = turn)

        if messages is None:
            messages = self._oai_messages[sender]

        # Call the hookable method that gives registered hooks a chance to process the last message.
        # Message modifications do not affect the incoming messages or self._oai_messages.
        messages = self.process_last_received_message(messages)

        # Call the hookable method that gives registered hooks a chance to process all messages.
        # Message modifications do not affect the incoming messages or self._oai_messages.
        messages = self.process_all_messages_before_reply(messages)

        for reply_func_tuple in self._reply_func_list:
            reply_func = reply_func_tuple["reply_func"]
            if "exclude" in kwargs and reply_func in kwargs["exclude"]:
                continue
            if inspect.iscoroutinefunction(reply_func):
                continue
            if self._match_trigger(reply_func_tuple["trigger"], sender):

                final, reply = reply_func(self, messages=messages, sender=sender, config=reply_func_tuple["config"])
                if logging_enabled():
                    log_event(
                        self,
                        "reply_func_executed",
                        reply_func_module=reply_func.__module__,
                        reply_func_name=reply_func.__name__,
                        final=final,
                        reply=reply,
                    )
                if final:
                    return reply
        return self._default_auto_reply


