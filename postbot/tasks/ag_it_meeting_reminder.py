"""Sends a reminder for the next AG IT meeting into the AG IT channel"""

import datetime

DESCRIPTION = "Erinnerung an das nächste AG-IT-Treffen"

async def run(driver, args: str = "") -> None:

    """Execute only every two weeks"""
    weeknumber = datetime.date.today().isocalendar()[1]
    if weeknumber % 2 == 1:
        return

    tomorrow = datetime.date.today() + datetime.timedelta(days=1)

    driver.posts.create_post({
        "channel_id": "ftx1e8fazjn68bqbt1zdq71aeh",
        "message": f"Das nächste AG-IT Treffen ist morgen, den {tomorrow.day}.{tomorrow.month}., um 21:00 Uhr :tada: Bitte reagiert, ob ihr kommt.",
    })

    pass
