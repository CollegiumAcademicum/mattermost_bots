DESCRIPTION = "Weekly message to remind AG WAS Members that there is a Meeting and ask for Participation"


async def run(driver, args: str = "") -> None:

    driver.posts.create_post({
        "channel_id": "wdutkg3zjf8ffgf4wteg1fk44r",
        "message": "### AG WAS Treffen \n\n\nReagiert bitte wer kommt oder falls ihr nicht könnt.\n\n:rat:",
    })

    pass
