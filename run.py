import requests, asyncio
from discord.utils import chunk_list
from tool.greed import Greed
from itertools import islice
from typing import List
import multiprocessing
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

    for i, shard_array in enumerate(chunk_list(shards, per_cluster), start = 0):
        bot = Greed(CONFIG_DICT, shard_count = shard_count, shard_ids = shard_array, local_address = (ips[i], 0))
        BOTS.append(bot)
    stdout, stdin = multiprocessing.Pipe()
    for bot in BOTS:
        process = multiprocessing.Process(target=bot.run, daemon = True)
        process.start()
        PROCESSES.append(process)
    
    # Keep processes alive and monitor their status
    await asyncio.gather(*[asyncio.to_thread(process.join) for process in PROCESSES])

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    asyncio.run(start())


