import requests
import asyncio
from discord.utils import chunk_list
from tool.greed import Greed
from config import CONFIG_DICT
import argparse
from discord.utils import setup_logging
setup_logging()

TOKEN = CONFIG_DICT["token"]
headers = {
    'Authorization': f'Bot {TOKEN}'
}
parser = argparse.ArgumentParser(description="A CLI tool for handling cluster IDs for greed.")
parser.add_argument("cluster", type=int, help="The ID of the cluster.")
args = parser.parse_args()
cluster_id = args.cluster



if __name__ == "__main__":
    ips = ["23.160.168.194", "23.160.168.195", "23.160.168.196"]
    response = requests.get('https://discord.com/api/v10/gateway/bot', headers=headers)
    shard_count = response.json()['shards']
    shards = [i for i in range(shard_count)]
    per_cluster = round(len(shards) / 3)
    shard_chunks = chunk_list(shards, per_cluster)
    shard_array = shard_chunks[cluster_id - 1 if cluster_id > 0 else 1]
    local_addr = (ips[cluster_id - 1 if cluster_id > 0 else 1], 0)
    bot = Greed(CONFIG_DICT, shard_count=shard_count, shard_ids=shard_array, local_address=local_addr)
    asyncio.run(bot.go())