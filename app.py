from sanic import Sanic, json, raw
from sanic.request import Request
from sanic_cors import CORS
from tool.important.database import Database, Record

app = Sanic("cdn")

async def avatar(request: Request, user_id: int, identifier: str):
    if not (data := await app.ctx.db.fetchrow("""SELECT avatar, content_type, ts FROM avatars WHERE user_id = $1 AND id = $2""", user_id, identifier)):
        return json(content={'message':'Not found'}, status=404)
    return raw(data.avatar, content_type=data.content_type, status=200)

@app.main_process_start
async def on_start(*_):
    app.ctx.db = Database()
    await app.ctx.db.connect()

app.add_route(avatar, "/avatar/<user_id>/<identifier>", methods = ["GET", "OPTIONS"])

if __name__ == "__main__":
    app.run(port=5555, workers=10)
