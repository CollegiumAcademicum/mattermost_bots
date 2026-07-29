import datetime

DESCRIPTION = "halbjährliche Erinnerung Bildungsnachweise (Neubau)"

# (deadline, period_start, period_end) — period_end year = same year for H1, year+1 for H2
_HALVES = {
    1: ("15.04", "01.04", "30.09"),
    2: ("15.10", "01.10", "31.03"),
}

_FORM_URL = "https://cacloud.ca-hd.de/index.php/s/GeYbRPLrgHa3xfo/download" # Link MUST end with /download
_LETTER_URL = "https://cacloud.ca-hd.de/index.php/s/ENmRsQnexoQJbJd/download"

CHANNELS = [
    "nia18g1eojrrdg3mucpaze39dc",
    "nia18g1eojrrdg3mucpaze39dc",
]


async def run(driver, args: str = "") -> None:
    import logging
    import requests

    logger = logging.getLogger(__name__)

    today = datetime.date.today()
    half = 1 if today.month <= 6 else 2
    year = today.year
    deadline, period_start, period_end = _HALVES[half]
    end_year = year if half == 1 else year + 1
    period = f"{period_start}.{year % 100:02d} - {period_end}.{end_year % 100:02d}"

    form_bytes = requests.get(_FORM_URL, timeout=15).content
    letter_bytes = requests.get(_LETTER_URL, timeout=15).content

    message = (
        f"### Nachweise/ Proof of Education :incoming_envelope:\n\n"
        f"*English version below*\n\n"
        f"Hey liebe Menschen,\n\n"
        f"Es ist mal wieder soweit, wir brauchen die **Nachweise für das nächste halbe Jahr**. "
        f"Bitte ladet den Nachweis bis zum **{deadline}.** auf https://nachweis.collegiumacademicum.de hoch.  \n"
        f"@Studierende: Nachweis = aktuelle Immatrikulationsbescheinigung ({period})\n"
        f"@Azubis: Wir haben **ein Dokument, welches als Nachweis ausreicht**. Ihr müsst es nur ausfüllen und bei eurer Ausbildungsstelle für eine Unterschrift abgeben. "
        f"Außerdem haben wir ein **Erklärungsschreiben (Bescheid für Ausbildungsstellen)** erstellt, welches ihr eurer Ausbildungsstelle geben könnt, damit die Bescheid wissen, warum ihr jedes halbe Jahr einen neuen Nachweis braucht. "
        f"**Außerdem wichtig:** Euer Ausbildungsvertrag reicht leider als Nachweis nicht aus!\n\n"
        f"Falls ihr Fragen dazu oder irgendwelche Probleme habt, kommt gerne auf uns (Mietverwaltung) zu. Danke euch \\(:\n\n"
        f"---\n\n"
        f"Hey, dear flatmates,\n\n"
        f"It's that time again, we need the **proof of education for the next six months**. "
        f"Please upload the proof of education to https://nachweis.collegiumacademicum.de until the **{deadline}**.\n"
        f"@students: proof of education = current certificate of enrollment ({period})\n"
        f"@Trainees: We've put together a **document that works as proof.** All you need to do is fill it out and have your training centre sign it. "
        f"We've also added a **letter of explanation (Bescheid für Ausbildungsstellen)** that you can give to your training centre, so they understand why you need a new certificate every six months.\n\n"
        f"**Important**: unfortunately, your training contract isn't enough on its own as proof. "
        f"If you have any questions or problems, please do not hesitate to contact us (rental administration). Thank you \\(:"
    )

    for channel_id in CHANNELS:
        try:
            form_upload = driver.files.upload_file(
                channel_id=channel_id,
                files={"files": ("Nachweis_Formular_Azubis.pdf", form_bytes, "application/pdf")},
            )
            letter_upload = driver.files.upload_file(
                channel_id=channel_id,
                files={"files": ("Erklaerungsschreiben_Ausbildungsstellen.pdf", letter_bytes, "application/pdf")},
            )
            file_ids = [
                form_upload["file_infos"][0]["id"],
                letter_upload["file_infos"][0]["id"],
            ]
            driver.posts.create_post({"channel_id": channel_id, "message": message, "file_ids": file_ids})
        except Exception as e:
            logger.error(f"Failed to post to channel {channel_id}: {e}")