from aiohttp import ClientSession
from shazamio import Shazam
from loguru import logger
from dataclasses import dataclass
from asyncio import create_subprocess_shell
from asyncio.subprocess import PIPE
from aiofiles import open as async_open
from tuuid import tuuid
from os import remove


@dataclass
class Track:
    song: str
    artist: str
    metadata: list
    cover_art: str
    url: str


class Recognizer:
    def __init__(self):
        self.session = ClientSession()
        self.client = Shazam()

    async def get_bytes(self, url: str) -> bytes:
        async with self.session.get(url) as response:
            return await response.read()

    async def get_audio(self, file: str) -> bytes:
        output_file = f"{file.rsplit('.', 1)[0]}.mp3"
        process = await create_subprocess_shell(
            f"ffmpeg -i {file} -q:a 0 -map a {output_file}",
            stdout=PIPE
        )
        await process.communicate()
        async with async_open(output_file, "rb") as ff:
            data = await ff.read()
        remove(file)
        remove(output_file)
        return data

    async def recognize(self, url: str):
        if not url.endswith(".mp3"):
            extension = url.split("/")[-1].split(".")[-1].split("?")[0]
            file = f"/root/{tuuid()}.{extension}"
            async with async_open(file, "wb") as ff:
                await ff.write(await self.get_bytes(url))
            bytes_ = await self.get_audio(file)
        else:
            bytes_ = await self.get_bytes(url)

        try:
            data = await self.client.recognize(bytes_)
            logger.info(data)
            track = data["track"]
        except (IndexError, KeyError):
            return None

        return Track(
            song=track["title"],
            artist=track["subtitle"],
            metadata=track["sections"][0]["metadata"],
            cover_art=track["images"]["coverart"],
            url=track["url"],
        )
