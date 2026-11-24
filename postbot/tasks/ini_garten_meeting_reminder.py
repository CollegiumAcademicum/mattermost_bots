"""Sends a reminder for the next Garten Ini meeting into the garten Ini channel"""

import datetime

DESCRIPTION = "Erinnerung an das nächste Garten-Ini-Treffen"

async def run(driver, args: str = "") -> None:

    tomorrow = datetime.date.today() + datetime.timedelta(days=1)

    driver.posts.create_post({
        "channel_id": "huoy7ao5nfb1tjtd8ykowoh8mw",
        "message": f"Hey hey, am Samstag, den {tomorrow.day}.{tomorrow.month}. ist wieder Garten Treff! Wenn ihr Zeit und Lust habt mitzumachen, reagiert auf diese Nachricht mit :leaves:.",
    })
