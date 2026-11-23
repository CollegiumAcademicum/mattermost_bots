DESCRIPTION = "Weekly message to remind AG WAS Members that there is a Meeting and ask for Participation"


async def run(driver, args: str = "") -> None:

    driver.posts.create_post({
        "channel_id": "wdutkg3zjf8ffgf4wteg1fk44r",
        "message": "### AG WAS Treffen \n\n\nReagiert bitte wer kommt oder falls ihr nicht könnt.
        \nTreffen findet Standartmäßig im Seminarraum, hinterer Teil, um 19 Uhr statt.
        \n @kenia und @dominik sind eure Ansprechpersonen falls ihr bspw. neu in die AG kommen wollt, nicht alleine ins Treffen gehen wollt oder wissen wollt was in der AG WAS abgeht.
        \n\n Liebe Grüße :rat:",
    })

    pass
