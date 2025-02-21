import asyncio
import uvloop
import argparse
from discord.utils import chunk_list, setup_logging
from loguru import logger
from tool.greed import Greed
from config import CONFIG_DICT

setup_logging()
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

TOKEN = CONFIG_DICT["token"]

parser = argparse.ArgumentParser(
    description="CLI tool for handling cluster IDs for Greed."
)
parser.add_argument("cluster", type=int, help="The ID of the cluster (1-3)")
args = parser.parse_args()
cluster_id = args.cluster

if not (1 <= cluster_id <= 3):
    logger.error("Cluster ID must be between 1 and 3.")
    exit(1)

async def main():
    ips = ["23.160.168.122", "23.160.168.124", "23.160.168.125"]
    
    shard_count = 26
    clusters = 3
    per_cluster = (shard_count + clusters - 1) // clusters
    
    shards = list(range(shard_count))
    shard_chunks = chunk_list(shards, per_cluster)
    
    shard_array = shard_chunks[cluster_id - 1]
    local_addr = (ips[cluster_id - 1], 0)
    
    logger.info(f"Starting cluster {cluster_id} with shards: {shard_array}")
    
    bot = Greed(CONFIG_DICT, shard_count=shard_count, shard_ids=shard_array, local_address=local_addr)
    await bot.go()

if __name__ == "__main__":
    asyncio.run(main())
