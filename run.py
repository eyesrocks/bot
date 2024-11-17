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

def run_bot(bot):
    bot.run()

async def start():
    PROCESSES = []
    ips = ["23.160.168.194", "23.160.168.195", "23.160.168.196"]
    response = requests.get('https://discord.com/api/v10/gateway/bot', headers=headers)
    shard_count = response.json()['shards']
    shards = [i for i in range(shard_count)]
    per_cluster = round(len(shards) / 3)

    for i, shard_array in enumerate(chunk_list(shards, per_cluster), start=0):
        bot = Greed(CONFIG_DICT, shard_count=shard_count, shard_ids=shard_array, local_address=(ips[i], 0))
        process = multiprocessing.Process(target=run_bot, args=(bot,), daemon=True)
        process.start()
        PROCESSES.append(process)

    while True:
        for i, process in enumerate(PROCESSES):
            if not process.is_alive():
                # Recreate and restart the dead process
                bot = Greed(CONFIG_DICT, shard_count=shard_count, 
                          shard_ids=list(chunk_list(shards, per_cluster))[i], 
                          local_address=(ips[i], 0))
                new_process = multiprocessing.Process(target=run_bot, args=(bot,), daemon=True)
                new_process.start()
                PROCESSES[i] = new_process

        await asyncio.sleep(5)  # Check every 5 seconds

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    asyncio.run(start())