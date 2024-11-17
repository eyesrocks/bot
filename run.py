import requests
import asyncio
from discord.utils import chunk_list
from tool.greed import Greed
from typing import List
import multiprocessing
import time
from config import CONFIG_DICT

TOKEN = CONFIG_DICT["token"]
headers = {
    'Authorization': f'Bot {TOKEN}'
}

async def start():
    BOTS = []
    PROCESSES = []
    ips = ["23.160.168.194", "23.160.168.195", "23.160.168.196"]
    response = requests.get('https://discord.com/api/v10/gateway/bot', headers=headers)
    shard_count = response.json()['shards']
    shards = [i for i in range(shard_count)]
    per_cluster = round(len(shards) / 3)

    for i, shard_array in enumerate(chunk_list(shards, per_cluster), start=0):
        bot = Greed(CONFIG_DICT, shard_count=shard_count, shard_ids=shard_array, local_address=(ips[i], 0))
        BOTS.append(bot)

    while True:
        for i, bot in enumerate(BOTS):
            if len(PROCESSES) <= i or not PROCESSES[i].is_alive():
                # Process is not alive, restart it
                process = multiprocessing.Process(target=bot.run, daemon=True)
                process.start()
                if len(PROCESSES) > i:
                    PROCESSES[i] = process  # Replace the dead process
                else:
                    PROCESSES.append(process)  # Add new process

        await asyncio.sleep(5)  # Check every 5 seconds

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    asyncio.run(start())