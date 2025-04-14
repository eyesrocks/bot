CONFIG = {
    "prefix": ";",
    "owners": {
        961016602944483459,
        1294487023272595511,
    },
    "token": "MTE0OTUzNTgzNDc1Njg3NDI1MA.GSOfph.hblFTcu2t1qmcPB61TnnB_eIIu2hNXRWk6QnSo",
    "rival_api": "abc2f2fe-a27b-43c0-8b0d-5b4b76752209",
    "domain": "https://eyes.rocks",
}

# testing token MTMwMTg2MTExNTMxMTAzMDMzMw.GMZuAn.BMEDBuh0Tk1MYZUs81-moajFDaV8JbcIQR1OX8

# main token MTE0OTUzNTgzNDc1Njg3NDI1MA.GVpIbW.lvZYmGc_g6QdvZyy649OxNtMen5v3Quc_ZlOgM


CHANCES = {
    "roll": {"percentage": 50.0, "total": 100.0},
    "coinflip": {"percentage": 60.0, "total": 100.0},
    "gamble": {"percentage": 20.0, "total": 100.0},
    "supergamble": {"percentage": 21.0, "total": 1000.0},
}


class Authorization:
    class Instagram:
        session_id = ""
        csrf_token = ""

    class LastFM:
        api_key = "ac82ef7e341d3e9dd71c2e7f5625b6a8"
        api_secret = "1008d94193db951eae45e3ebf9a9a034"
        pending_auth = {}
        cb_url = "https://api.eyes.rocks/callback"

    class Outages:
        api_key = "greed_outages_api_key_2024_because_im_a_boss_85_2007_noscopes"
