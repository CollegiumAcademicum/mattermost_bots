import datetime

DESCRIPTION = "halbjährliche Erinnerung Bildungsnachweise (Neubau)"

# (deadline, period_start, period_end) — period_end year = same year for H1, year+1 for H2
_HALVES = {
    1: ("15.04", "01.04", "30.09"),
    2: ("15.10", "01.10", "31.03"),
}

_FORM_URL = "https://cacloud.ca-hd.de/index.php/s/GeYbRPLrgHa3xfo/download" # Link MUST end with /download
_LETTER_URL = "https://cacloud.ca-hd.de/index.php/s/ENmRsQnexoQJbJd/download"

CHANNELS = [ "e5dimwbokjnmucs3q9o915wyna", "beugzez81bnx9f4ywrbpezownh", "5ggm6dskpbr5ikc8qzksxjw31o", "bnztrjqjt7be8x7umeqgtdu7xa", "ijw58n1qubrrpdx3jtdb15yxso", "sbj448duu3n69q8hsaqyib9cda", "9wjw9mecatnz9ry5b941y9kmdh", "xcu86akqbjg6dg9w3xbkaud7ch", "e5h9bsccd3fi7gteus4p7wxi8w", "hauijh76ajn1udfo34q1k7zooy", "z6gsnq4byt8mxfurjknrmiw5uy", "9weitxqzz7d7unakfsamodn6wo", "wfyaysxrmtd13y5fj679zzbwse", "8ceaebeb63rd381wfbu9hw1yna", "g5uyftthhpby8nbz9a8y1dbsaa", "j44xp18p9fye3q8eq6ih6beyur", "tukp1agnbpy33p9op66ykmamna", "hx7iijf473rjmruzejif5qzx3y", "5cc7fs5fppf1pguw9yunaqdtiw", "1ua57rok17go9f1n5obnfzkwnh", "4djhtfywyj8sfrutmtwkd1q4ac", "bx1hxxqhtf8fjeoucqewy7jtkw", "8jo39raottnifdghwnz5e9ae9r", "xyzqywmn6bbwtqxqapmnzw8dey", "jpdtxfm7tibmpmwxiorp378f8o", "f8km9s64tbnoux8xb63qpba4uc", "rxxidz669idsux19n9694w8szc", "ojfa1qr1nb8ciy6t6dbfaejy5a", "38t9kcfq778ht869zaz1z56dph", "qeig9hass7fkxcxcxy4r7q4szr", "rgadorojf7bpdbnjzd9w4uz4ph", "kjhmcnmzmfddtcbpybsyu13fte", "69f5wzq7o3rszm55o8p8y9osce", "hfk47dse3788jfcx3t8qk1optw", "upt18p5zg3re8r1nb3duhgzr4e", "f1b4qjfwk3fsmdtekd5ufgyzxy", "jcdwtt4dmtdc8byu7szf7r7mgy", "d4ui86yxibbw7ept3bqb38j4dw", "zgtgc74wgif4irbuauyamcax8w", "96frbpues3nkdfe5zjfjn6q9ia", "drzkukk4p3gkdj9eonqm7yt6na", "cfytfnna5f89inhfoxkqe8cwfc", "bq7obr9rx3fxjbhh4uf5kejecr", "8otasprmi3ga7x6as1sttq1o6w", "a4zf5wrxgbr8imhajm6xers3qo", "84txspt9pjn4jbfmoomks9thay",]


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
        f"Bitte ladet den Nachweis bis zum **{deadline}.** auf https://nachweis.collegiumacademicum.de hoch. "
        f"Wenn ihr eure Ausbildung bereits beendet habt und im nächsten Zeitraum ausziehen werdet müsst ihr das dort auch angeben.  \n"
        f"@Studierende: Nachweis = aktuelle Immatrikulationsbescheinigung ({period})\n"
        f"@Azubis: Wir haben **ein Dokument, welches als Nachweis ausreicht**. Ihr müsst es nur ausfüllen und bei eurer Ausbildungsstelle für eine Unterschrift abgeben. "
        f"Außerdem haben wir ein **Erklärungsschreiben (Bescheid für Ausbildungsstellen)** erstellt, welches ihr eurer Ausbildungsstelle geben könnt, damit die Bescheid wissen, warum ihr jedes halbe Jahr einen neuen Nachweis braucht. "
        f"**Außerdem wichtig:** Euer Ausbildungsvertrag reicht leider nicht als Nachweis aus, wenn er älter als 6 Monate ist!\n\n"
        f"Zur Erinnerung: Nach unserem Konsens werden für jede Woche Verspätung nach dem {deadline}. 5 € Verwaltungsgebühr fällig. "
        f"Solltet ihr aus irgendeinem Grund nicht in der Lage sein den Nachweis rechtzeitig hochzuladen sagt uns bitte vorher Bescheid, dann müsst ihr natürlich nicht sofort Verwaltungsgebühren zahlen.\n\n"
        f"Falls ihr Fragen dazu oder irgendwelche Probleme habt, kommt gerne auf uns (Mietverwaltung) zu. Danke euch \\(:\n\n"
        f"---\n\n"
        f"Hey, dear flatmates,\n\n"
        f"It's that time again, we need the **proof of education for the next six months**. "
        f"Please upload the proof of education to https://nachweis.collegiumacademicum.de until the **{deadline}**. "
        f"If you have already completed your training and are moving out in the next period, you must also state this there.  \n"
        f"@students: proof of education = current certificate of enrollment ({period})\n"
        f"@Trainees: We've put together a **document that works as proof.** All you need to do is fill it out and have your training centre sign it. "
        f"We've also added a **letter of explanation (Bescheid für Ausbildungsstellen)** that you can give to your training centre, so they understand why you need a new certificate every six months. "
        f"**Important**: unfortunately, your training contract is not sufficient proof if it is more than 6 months old!\n\n"
        f"Just a reminder: as per our consensus, an administrative fee of €5 will be charged for each week’s delay after {deadline}. "
        f"If, for any reason, you are unable to upload the proof on time, please let us know in advance; in that case, you will of course not have to pay the administrative fees straight away.\n\n"
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