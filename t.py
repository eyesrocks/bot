import requests

r = requests.get("https://discord.com/api/v10/users/@me", headers = {"Authorization": f"Bot MTE0OTUzNTgzNDc1Njg3NDI1MA.Gao7xE.lq-Qj_UlaPInoZxrjBt_2IhME5t4YuJLjlW9oU"})
print(r.json())