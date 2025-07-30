import os
import random
import datetime
import pandas as pd
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from autogen import ConversableAgent, config_list_from_json
from components.agents.game.player import *
from components.agents.game.master import *

app = FastAPI()

def create_player(player_name, role_desc, backend):
    player = Player(
        name=player_name,
        role_desc=role_desc,
        global_prompt=game_description,
        llm_config=backend
    )
    return player

@app.head("/")
async def root_head():
    return {"message": "Uvicorn server is running"}

@app.websocket("/avalon")
async def websocket_endpoint(websocket: WebSocket):
    # Accept WebSocket connection
    await websocket.accept()

    folder_name = 'output/' + 'game_' + str(datetime.datetime.now().date()) + '-' + str(datetime.datetime.now().hour) + '-' + str(datetime.datetime.now().minute) + '-' + str(datetime.datetime.now().second)
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
    file_name = folder_name + '/conversation'

    players_no = [1, 2, 3, 4, 5]
    characters = ['Merlin', 'Percival', 'Servant', 'Assassin', 'Morgana']
    name2role = {}
    role2name = {}
    shuffled_players = random.sample(players_no, 5)
    for index, player_no in enumerate(shuffled_players):
        name2role['Player' + str(player_no)] = characters[index]
        role2name[characters[index]] = 'Player' + str(player_no)

    config_list = config_list_from_json(env_or_file="OAI_CONFIG_LIST")
    backend = {"config_list": config_list}

    players = {}
    for player in name2role:
        if name2role[player] == 'Assassin':
            addition_info = [name for name in name2role if name2role[name] == 'Morgana'][0]
        elif name2role[player] == 'Morgana':
            addition_info = [name for name in name2role if name2role[name] == 'Assassin'][0]
        elif name2role[player] == 'Merlin':
            addition_info = [name for name in name2role if name2role[name] in ['Morgana', 'Assassin']]
            addition_info = ','.join(addition_info)
        elif name2role[player] == 'Percival':
            addition_info = [name for name in name2role if name2role[name] in ['Morgana', 'Merlin']]
            addition_info = ','.join(addition_info) + " .However, you don't know which one is Merlin and which one is Morgana."
        else:
            addition_info = ''
        players[player] = create_player(player, Role_tips[name2role[player]] + addition_info, backend)

    conversation_df = pd.DataFrame(columns=['agent_name', 'visible_to', 'content', 'turn', 'timestamp', 'msg_type'])
    conversation_df.to_csv(file_name + '.csv', index=False)

    with open(folder_name + "/player_roles.json", "w") as f:
        json.dump(role2name, f)

    moderator = ConversableAgent(name='game master', llm_config=backend, system_message="You are a helpful game moderator")
    env = AvalonVanilla(websocket, players, moderator, role2name, name2role, folder_name)

    async def game_loop():
        print("Starting an example run of 5 steps...")
        await websocket.send_text(json.dumps({"sender": "server", "recipient": "all", "content": "WebSocket connected", "turn": 1, "timestamp": str(datetime.datetime.now())}))

        for i in range(5):
            player_name = env.get_next_player()
            player = players[player_name]
            action = player.generate_reply()
            await asyncio.sleep(0.1)
            action_content = action["content"]
            env.step(player_name, action_content)

    await game_loop()

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        print("WebSocket connection closed")
