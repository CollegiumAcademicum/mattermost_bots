DESCRIPTION = "Weekly message to remind AG WAS Members that there is a Meeting and ask for Participation"


async def run(driver, args: str = "") -> None:

    driver.posts.create_post({
        "channel_id": "wdutkg3zjf8ffgf4wteg1fk44r",
        "message": f"Test,AG WAS Bot! \n\n\nDas ist der Reminder für Dominik dass er hier noch eine Nachricht rein schreiben soll. irgendwas wie 'hey, reagiert wenn ihr ins treffen kommt' \n :feuervoigl:",
    })

    pass
