from typing import List, Union, Iterable
from dataclasses import dataclass
import sys
import asyncio

from components.utils import *
from .player import *
from prompts import Role_tips, game_description, Moderator_speech, format_control, \
    format_control_schemas, Moderator_remember_speech



# I prevented changing the class provided by the stakeholder significantly as that class is poorly written.
# It's very easy to introduce bugs if altered. TODO: Will consider optimizing once everything is functioning correctly.

# Note: I replaced all instances of Timestamp with self._terminal
# TODO: this class is an example migration from AvalonVanilla, should be changed to Avalon

class AvalonVanilla():
    type_name = 'AvalonVanilla'

    # Note: I added two new args: players and moderator
    def __init__(self, web_socket, players, moderator, char_to_name: dict = {}, name_to_char: dict = {}, output_folder_name: str = ""):
        self.web_socket = web_socket
        self.players = players
        self.results = {}
        self.moderator = moderator

        self.char_to_name = char_to_name
        self.turn = 0
        self.round = 1
        self._terminal = False
        self.name_to_char = name_to_char

        self.output_folder_name = output_folder_name

        # intent, first_order, formulation, second_order, intent modify, refinement, discussion, vote, action,assassin,summary
        # if the intent is picked randomly, then skip intent selection phase
        self.phase = 'formulation_con'
        self.current_player = 1
        self.current_leader = 1
        self.previous_player = 1
        self.vote_count = 0
        self.current_quest = 1
        self.every_round_team_member = {1: [], 2: [], 3: [], 4: [], 5: []}
        self.every_round_team_result = {1: {}, 2: {}, 3: {}, 4: {}, 5: {}, }
        self.every_round_team_no = {1: 2, 2: 3, 3: 2, 4: 3, 5: 3}
        self.quest_result = {1: None, 2: None, 3: None, 4: None, 5: None}
        self.if_finish_contemplation = False
        self.is_first_order_active = False
        self.vote_result = {}
        self.consecutive_vote_failure_count = 0
        self.role_tips = {
            "Merlin": "You are " + self.char_to_name['Merlin'] + " and your role is Merlin. " + self.char_to_name['Morgana'] + ' and ' + self.char_to_name[
                'Assassin'] + " are evil players",
            "Percival": "You are " + self.char_to_name['Percival'] + " and your role is Percival. " + self.char_to_name['Merlin'] + ' and ' + self.char_to_name[
                'Morgana'] + " are Merlin and Morgana, but you don't know which is Merlin and which is Morgana.",
            "Servant": "You are " + self.char_to_name['Servant'] + " and your role is of a loyal servant.",
            "Morgana": "You are " + self.char_to_name['Morgana'] + " and your role is Morgana and Assassin is " + self.char_to_name['Assassin'] + ".",
            "Assassin": "You are " + self.char_to_name['Assassin'] + " and your role is Assassin and Morgana is " + self.char_to_name['Morgana'] + "."
        }
        self.if_propose = True
        self.first_order_player_options = []
        self.first_order_player_option_idx = 0

        self.reset()
    
    async def send_websocket_message(self, message):
        await self.web_socket.send_text(json.dumps(message))

    # Note: added by Steven. Some of the args are unnecessary but included to interface with the original class
    def send_message(self, agent_name, content, turn, timestamp="wuhu", visible_to="all", msg_type="text", logged=False):
        """
        Sends a message from an agent to one or more players.

        Parameters:
            agent_name (str): The name of the sending agent.
            content (str | dict): The message content.
            turn (int): The current turn number.
            timestamp (str): The timestamp of the message.
            visible_to (str | list): The recipient(s), either "all", a single player, or a list of players.
            msg_type (str): The type of message.
            logged (bool): Whether the message should be logged.
        """
        agent_name = agent_name[:7]  # Truncate agent name to first 7 characters
        sender = self.players.get(agent_name)  # Safely get the sender player

        # Ensure content is in string format, convert dict to JSON if necessary
        content = json.dumps(content) if isinstance(content, dict) else str(content)

        # Determine recipients based on 'visible_to'
        if visible_to == "all":
            recipients = self.players.values()  # Send to all players
        elif isinstance(visible_to, str):
            recipients = [self.players[visible_to]]  # Send to a single player
        else:
            recipients = [self.players[p] for p in visible_to]  # Send to multiple players

        # Send the message to each recipient
        for player in recipients:
            sender.send(content, player)

            message = {
                'sender': agent_name,
                'recipient': player.name,
                'content': content,
                'turn': turn,
                'timestamp': timestamp,
                'visible_to': visible_to,
                'msg_type': msg_type
            }
            asyncio.create_task(self.send_websocket_message(message))

    # Note: added by Steven. Some of the args are unnecessary but included to interface with the original class
    def _moderator_speak(self, text: str, visible_to: str | list = "all", round: int = 0, msg_type=None):
        """
        Moderator sends a message to one or more players.

        Parameters:
            text (str): The message text.
            visible_to (str | list): The recipient(s), either "all", a single player, or a list of players.
            round (int): The current round number.
            msg_type (str): The type of message.
        """
        # Determine recipients based on 'visible_to'
        if visible_to == "all":
            recipients = self.players.values()  # Send to all players
        elif isinstance(visible_to, str):
            recipients = [self.players[visible_to]]  # Send to a single player
        else:
            recipients = [self.players[p] for p in visible_to]  # Send to multiple players

        # Send the moderator's message to each recipient
        for player in recipients:
            self.moderator.send(text, player)

            message = {
                'sender': 'Moderator',
                'recipient': player.name,
                'content': text,
                'turn': round,
                'visible_to': visible_to,
                'msg_type': msg_type
            }
            asyncio.create_task(self.send_websocket_message(message))

    # # start the game, everyone knows who is leader first
    # # for the first round, no deductive reasoning, only contemplation
    def reset(self):
        self.turn = 0
        self._terminal = False

        # self.set_intent(round=1)
        # announce the leader
        self._moderator_speak('This is round ' + str(self.round) + '. For this round, the leader is ' + 'Player' + str(
            self.current_leader), round=self.round)

        # propose team prompt
        self._moderator_speak(
            Moderator_speech['discussion']['first'] + str(self.every_round_team_no[self.current_quest]) + f". Remember to pick {str(self.every_round_team_no[self.round])} team members.",
            round=self.round)
        # TODO add contemplation prompt for leader

        # intent prompts for first player
        self._moderator_speak(self.role_tips[self.name_to_char['Player' + str(self.current_player)]], round=self.round,
                              visible_to='Player' + str(self.current_player), msg_type='role_tips')
        self.prompt_for_formulation_con(self.current_player, self.round)

        return self._terminal


    # get current player
    def get_next_player(self) -> str:
        current_player = self.current_player
        self.previous_player = current_player
        if self.if_finish_contemplation:
            if self.phase not in ('intent_evaluation', 'selected_intent_evaluation'):
                if self.phase != 'action':
                    if self.current_player != 5:
                        self.current_player += 1
                    else:
                        self.current_player = 1
                else:
                    for member in self.every_round_team_member[self.round]:
                        if member not in self.every_round_team_result[self.round]:
                            self.current_player = int(member[-1])
                            return 'Player' + str(self.current_player)

        return 'Player' + str(current_player)

    # update current player, phase, calculate the vote, form the team, put the observation in the message pool
    def process_speech(self, response_str, player_name):
        if len(self.first_order_player_options) == 0:
            if self.round == 1 and self.consecutive_vote_failure_count == 0:
                other_players = ['Player' + str(i + 1) for i in range(player_name - 1)]
            else:
                other_players = ['Player' + str(i + 1) for i in range(5) if (i+1) != player_name]
            self.first_order_player_options = other_players
            self.first_order_player_option_idx = 0
            self.is_first_order_active = True

        response_str = response_str.replace('[other players]', self.first_order_player_options[self.first_order_player_option_idx])

        self.first_order_player_option_idx += 1
        if self.first_order_player_option_idx == len(self.first_order_player_options):
            self.is_first_order_active = False
            self.first_order_player_options = []
            self.first_order_player_option_idx = 0
        return response_str

    def extract_team_members(self, action):
        action_list = action.split('\n')
        players = action_list[0]
        players_list = players.split(',')
        for player in players_list:
            self.every_round_team_member[self.round][player] = None

    def check_game_state(self):
        fail = len([item for item in self.quest_result if self.quest_result[item] == 0])
        success = len([item for item in self.quest_result if self.quest_result[item] == 1])

        if fail >= 3:
            self._moderator_speak('The game is over! Evil team wins!', round=self.round)
            self._terminal = True
        if success >= 3:
            self._moderator_speak('The game is over! The loyal team wins! We move to the assassin phase.',
                                  round=self.round)
            self.phase = 'assassin'

    def prompt_for_formulation_con(self, cur_player, cur_round):
        self._moderator_speak(
            Moderator_speech['formulation_contemplation'], round=cur_round,
            visible_to='Player' + str(cur_player), msg_type='formulation_contemplation')
        self._moderator_speak(format_control['contemplation'], round=cur_round,
                              visible_to='Player' + str(cur_player), msg_type='format')

    def prompt_for_first_order(self, cur_player, cur_round):
        speech = self.process_speech(Moderator_speech['first_order'], cur_player)
        self._moderator_speak(speech, round=cur_round, visible_to='Player' + str(cur_player), msg_type='first_order')
        self._moderator_speak(format_control['first_order'], round=self.round,
                              visible_to='Player' + str(cur_player), msg_type='format')

    def prompt_for_voting(self, cur_player, cur_round):
        player_name = "Player" + str(cur_player)
        remember_speech = self.get_remember_speech(player_name)
        self._moderator_speak(self.role_tips[self.name_to_char[player_name]],
                              round=cur_round, visible_to='Player' + str(cur_player), msg_type='role_tips')
        self._moderator_speak(player_name + ", it is your turn to vote. " + remember_speech, round=cur_round,
                              visible_to=player_name)
        self._moderator_speak(format_control['vote'], round=cur_round,
                              visible_to=player_name, msg_type='format')

    def prompt_for_action(self, cur_round):
        message = " It is your turn to make a choice for the quest result."

        character = self.name_to_char[self.get_next_player()]
        if character in ('Morgana', 'Assassin'):
            message += """ Remember, as an evil player your default choice should be to fail the quest,
even if it risks revealing your identity."""
        else:
            message += " As a loyal player you should always succeed the quest."

        self._moderator_speak(self.role_tips[character] + message, round=cur_round,
                              visible_to='Player' + str(self.current_player))
        self._moderator_speak(format_control['action'], round=cur_round,
                              visible_to='Player' + str(self.current_player), msg_type='format')

    def save_results(self, player_name, phase, data):
        if player_name not in self.results:
            self.results[player_name] = {}
            self.results[player_name]['role'] = self.name_to_char[player_name]

        if self.round not in self.results[player_name]:
            self.results[player_name][self.round] = {}
        if phase not in self.results[player_name][self.round]:
            self.results[player_name][self.round][phase] = []

        self.results[player_name][self.round][phase].append(data)

 

  
    
    def first_order(self, player_name, action):
        action = parse_json_response(response=action, schema=format_control_schemas['first_order'])
        self.save_results(player_name, self.phase, {'intent_guess': action})

        if 'reasoning' in action.keys():
            del action['reasoning']
        if 'confidence' in action.keys():
            del action['confidence']
        if 'evidence' in action.keys():
            del action['evidence']

        self.send_message(agent_name=player_name + "(" + self.name_to_char[player_name] + ")", content=action,
                          msg_type='first_order', visible_to=player_name, turn=self.round)

        if self.is_first_order_active:
            self.prompt_for_first_order(self.current_player, self.round)
        else:
            self.phase = 'formulation_con'
            self.prompt_for_formulation_con(self.current_player, self.round)

    def formulation_con(self, player_name, action):
        action = parse_json_response(response=action, schema=format_control_schemas['contemplation'])

        self.phase = "second_order"
        thinking = "Think:" + action['Think']
        speak = "Speech:" + action['Speak']
        self.send_message(agent_name=player_name, content=thinking,
                           msg_type="formulation_con", visible_to=player_name, turn=self.round)
        self.send_message(agent_name=player_name, content=speak,
                           msg_type="formulation_con", visible_to=player_name, turn=self.round)
        self._moderator_speak(Moderator_speech['second_order'], round=self.round, visible_to=player_name, msg_type='second_order')
        self._moderator_speak(format_control['second_order'], round=self.round, visible_to=player_name,
                              msg_type='format')

    def get_remember_speech(self, player_name):
        if self.name_to_char[player_name] in ('Morgana', 'Assassin'):
            remember_speech = Moderator_remember_speech['team']['evil']
        else:
            remember_speech = Moderator_remember_speech['team']['good']
        return remember_speech

    def second_order(self, player_name, action):
        action = parse_json_response(response=action, schema=format_control_schemas['second_order'])
        self.send_message(agent_name=player_name + "(" + self.name_to_char[player_name] + ")", content=action,
                          msg_type="second_order", visible_to=player_name, turn=self.round)

        self.if_finish_contemplation = True
        self._moderator_speak(
            Moderator_speech['refinement_contemplation'], round=self.round,
            visible_to=player_name, msg_type='refinement_contemplation')
        self.phase = 'discussion'
        if self.if_propose:
            if self.round > 1:
                remember_speech = self.get_remember_speech(player_name)
                moderator_speech = Moderator_speech['discussion']['first'].replace('[remember]', remember_speech)
                self._moderator_speak(
                     moderator_speech + str(self.every_round_team_no[self.round]) + f". Remember to pick {str(self.every_round_team_no[self.round])} team members.",
                    round=self.round)
            self._moderator_speak(format_control['proposal'], round=self.round, visible_to=player_name,
                                  msg_type='format')
        else:
            self._moderator_speak(format_control['contemplation'], round=self.round, visible_to=player_name,
                                  msg_type='format')
        self.if_finish_contemplation = True

    def discussion(self, player_name, action):
        if player_name == 'Player' + str(self.current_leader):
            action = parse_json_response(response=action, schema=format_control_schemas['proposal'])
            print(action)
            thinking = action['Think']
            speech = action['Speak']
            self.send_message(agent_name=player_name + "(" + self.name_to_char[player_name] + ")", content=thinking,
                              msg_type='thinking', visible_to=player_name, turn=self.round)

            proposed_players = action['team'].split(',')
            self.every_round_team_member[self.round] = proposed_players
            if len(proposed_players) != self.every_round_team_no[self.current_quest]:
                print("Proposed number of team members don't match the required the team members.", proposed_players)
                sys.exit()

            self.send_message(agent_name=player_name + "(" + self.name_to_char[player_name] + ")",
                               content=action['team'] + '\n' + speech, msg_type='discussion', visible_to='all',
                               turn=self.round)
            self.if_propose = False

        else:
            action = parse_json_response(response=action, schema=format_control_schemas['contemplation'])
            thinking = action['Think']
            speech = action['Speak']
            self.send_message(agent_name=player_name + "(" + self.name_to_char[player_name] + ")", content=thinking,
                              msg_type='thinking', visible_to=player_name, turn=self.round)

            self.send_message(agent_name=player_name + "(" + self.name_to_char[player_name] + ")", content=speech,
                               msg_type='discussion', visible_to='all', turn=self.round)


        self.turn += 1
        if self.turn < 5:
            self.if_finish_contemplation = False
            self.phase = "first_order"
            self._moderator_speak(self.role_tips[self.name_to_char['Player' + str(self.current_player)]],
                                  round=self.round, visible_to='Player' + str(self.current_player), msg_type='role_tips')
            self._moderator_speak("Player" + str(self.current_player) + Moderator_speech['discussion']['rest'],
                                  visible_to='Player' + str(self.current_player), round=self.round)
            self.prompt_for_first_order(self.current_player, self.round)

        else:
            self.phase = 'vote'
            self._moderator_speak(Moderator_speech['vote'] + '.And the proposed team members are:' + ','.join(
                self.every_round_team_member[self.round]), round=self.round)
            self.prompt_for_voting(self.current_player, self.round)
            self.turn = 0

    def vote(self, player_name, action):
        action = parse_json_response(response=action, schema=format_control_schemas['vote'])

        vote_result = action['vote']
        explanation = action['explanation']

        self.vote_result[player_name] = vote_result

        self.save_results(player_name, self.phase, {'vote_result': vote_result})

        self.send_message(agent_name=player_name + "(" + self.name_to_char[player_name] + ")", content=explanation,
                           msg_type='explanation', visible_to=player_name, turn=self.round)


        if vote_result == 'agree':
            self.vote_count += 1
        self.turn += 1
        if self.turn != 5:
            self.prompt_for_voting(self.current_player, self.round)

        if self.turn == 5:
            if self.vote_count >= 3 or self.consecutive_vote_failure_count == 1:
                # on agreement on team or 2 consecutive disagreement, this should execute
                self.consecutive_vote_failure_count = 0
                self._moderator_speak(
                    Moderator_speech['vote_result']['agree'] + ','.join(self.every_round_team_member[self.round]),
                    round=self.round)  # add player name
                self._moderator_speak("The vote result for this round is: " + str(self.vote_result), round=self.round)
                self.phase = 'action'
                self._moderator_speak(Moderator_speech['action'], round=self.round)
                self.prompt_for_action(self.round)
            else:
                # on the first disagreement on team, this should execute
                self.consecutive_vote_failure_count += 1
                self.current_player = 1

                self.phase = "summary"
                self._moderator_speak(Moderator_speech['summary'], round=self.round,
                                      visible_to='Player' + str(self.current_player))
            self.turn = 0

    def action(self, player_name, action):
        action = parse_json_response(response=action, schema=format_control_schemas['action'])

        result = action['result']
        explanation = action['explanation']

        self.every_round_team_result[self.round][player_name] = result

        self.save_results(player_name, self.phase, {'action_result': result})

        self.send_message(agent_name=player_name + "(" + self.name_to_char[player_name] + ")", content=result,
                           msg_type='action', visible_to=player_name, turn=self.round)

        self.send_message(agent_name=player_name + "(" + self.name_to_char[player_name] + ")", content=explanation,
                           msg_type='explanation', visible_to=player_name, turn=self.round)



        self.turn += 1
        if self.turn == len(self.every_round_team_member[self.round]):
            fail_no = list(self.every_round_team_result[self.round].values()).count('failure')
            if fail_no > 0:
                self.quest_result[self.round] = 0
                self._moderator_speak("The quest is failed, there are " + str(fail_no) + ' fail choice',
                                      round=self.round)
            else:
                self.quest_result[self.round] = 1
                self._moderator_speak("Nice, the quest is successful!", round=self.round)

            self.turn = 0
            self.check_game_state()
            if self.phase == 'assassin':
                self._moderator_speak(text=Moderator_speech['assassin'], visible_to=self.char_to_name['Assassin'],
                                      round=self.round)
                self.current_player = int(self.char_to_name['Assassin'][-1])
                self._moderator_speak(text=format_control['assassin'], round=self.round,
                                      visible_to=self.char_to_name['Assassin'], msg_type='format')
            else:
                self.phase = "summary"
                self.current_player = 1
                self.turn = 0
                self._moderator_speak(Moderator_speech['summary'], round=self.round,
                                      visible_to='Player' + str(self.current_player))

            # if self._terminal:
            #     return TimeStep(observation=self.get_observation(player_name), reward=self.get_zero_rewards(),
            #                     terminal=self._terminal)
        else:
            self.prompt_for_action(self.round)

    def summary(self, player_name, action):
        self.send_message(agent_name=player_name + "(" + self.name_to_char[player_name] + ")", content=action,
                          msg_type='summary', visible_to=player_name, turn=self.round)

        self.turn += 1
        if self.turn == 5:
            if self.vote_count < 3 and self.consecutive_vote_failure_count == 1:
                # on disagreement this should execute
                if self.current_leader != 5:
                    self.current_leader += 1
                else:
                    self.current_leader = 1
                self.phase = 'discussion'
                self.current_player = self.current_leader
                self._moderator_speak(Moderator_speech['vote_result']['announce_leader'] + str(self.current_leader),
                                      round=self.round)
                self._moderator_speak(Moderator_speech['discussion']['first'] + str(
                    self.every_round_team_no[self.current_quest]) + '. Remember to select different players this time.',
                                      round=self.round, visible_to='Player' + str(self.current_leader))
                self._moderator_speak(format_control['proposal'], round=self.round,
                                      visible_to='Player' + str(self.current_leader), msg_type='format')

                self.vote_count = 0
                self.every_round_team_member[self.round] = []
            else:
                # on agreement on team and quest completion this should execute
                self.phase = 'discussion'
                self.if_propose = True
                self.round += 1
                self.current_leader += 1

                self.current_player = self.current_leader
                self.current_quest += 1

                print(f'\n\nNow entering round - {self.round}\n\n')

                self._moderator_speak(
                    'This is round ' + str(self.round) + '. For this round, the leader is ' + 'Player' + str(
                        self.current_leader), round=self.round)

                self.if_finish_contemplation = False
                self.phase = "first_order"
                self._moderator_speak(self.role_tips[self.name_to_char['Player' + str(self.current_player)]],
                                      round=self.round, visible_to='Player' + str(self.current_player), msg_type='role_tips')
                self.prompt_for_first_order(self.current_player, self.round)

            self.turn = 0
        else:
            self._moderator_speak(Moderator_speech['summary'], round=self.round,
                                  visible_to='Player' + str(self.current_player))

    def assassin(self, player_name, action):
        action = parse_json_response(response=action, schema=format_control_schemas['assassin'])
        assassinated_player = action['player']

        self.send_message(agent_name=player_name + "(" + self.name_to_char[player_name] + ")",
                          content=assassinated_player, turn=self.round)

        if action != self.char_to_name['Merlin']:
            self._moderator_speak('Assassin failed! The game is over. Loyal team wins!', round=self.round)
        else:
            self._moderator_speak('Assassin succeed! The game is over. Evil team wins!', round=self.round)
        self._terminal = True

    def step(self, player_name: str, action: str) -> bool:
        try :
            self.check_game_state()
            if self._terminal:
                return self._terminal

            elif self.phase == "first_order":
                self.first_order(player_name, action)
            elif self.phase == "formulation_con":
                self.formulation_con(player_name, action)
            elif self.phase == "second_order":
                self.second_order(player_name, action)

            elif self.phase == 'discussion':
                self.discussion(player_name, action)
            elif self.phase == 'vote':
                self.vote(player_name, action)

            elif self.phase == 'action':
                self.action(player_name, action)

            elif self.phase == 'summary':
                self.summary(player_name, action)

            elif self.phase == 'assassin':
                self.assassin(player_name, action)

            return self._terminal
        except Exception as e:
            with open(self.output_folder_name + "/results.json", "w") as file:
                json.dump(self.results, file)
            raise e
