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

def run_bot(config, shard_count, shard_ids, local_address):
    bot = Greed(config, shard_count=shard_count, shard_ids=shard_ids, local_address=local_address)
    bot.run()

async def start():
    ips = ["23.160.168.194", "23.160.168.195", "23.160.168.196"]
    response = requests.get('https://discord.com/api/v10/gateway/bot', headers=headers)
    shard_count = response.json()['shards']
    shards = [i for i in range(shard_count)]
    per_cluster = round(len(shards) / 3)

    processes = []
    for i, shard_array in enumerate(chunk_list(shards, per_cluster), start=0):
        process = multiprocessing.Process(target=run_bot, args=(CONFIG_DICT, shard_count, shard_array, (ips[i], 0)), daemon=True)
        process.start()
        processes.append(process)

    while True:
        for i, process in enumerate(processes):
            if not process.is_alive():
                # Process is not alive, restart it
                process = multiprocessing.Process(target=run_bot, args=(CONFIG_DICT, shard_count, chunk_list(shards, per_cluster)[i], (ips[i], 0)), daemon=True)
                process.start()
                processes[i] = process  # Replace the dead process

        await asyncio.sleep(5)  # Check every 5 seconds

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    asyncio.run(start())