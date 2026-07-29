import datetime

DESCRIPTION = "vierteljährliche Erinnerung zur Kündigungsfrist"

# (move_out, deadline) per quarter — last day of quarter, 5th of month before
_QUARTERS = {
    1: ("31.03", "05.02"),
    2: ("30.06", "05.05"),
    3: ("30.09", "05.08"),
    4: ("31.12", "05.11"),
}

CHANNELS = [
    "e5dimwbokjnmucs3q9o915wyna", "beugzez81bnx9f4ywrbpezownh", "5ggm6dskpbr5ikc8qzksxjw31o",
    "bnztrjqjt7be8x7umeqgtdu7xa", "ijw58n1qubrrpdx3jtdb15yxso", "sbj448duu3n69q8hsaqyib9cda",
    "9wjw9mecatnz9ry5b941y9kmdh", "xcu86akqbjg6dg9w3xbkaud7ch", "e5h9bsccd3fi7gteus4p7wxi8w",
    "hauijh76ajn1udfo34q1k7zooy", "z6gsnq4byt8mxfurjknrmiw5uy", "9weitxqzz7d7unakfsamodn6wo",
    "wfyaysxrmtd13y5fj679zzbwse", "8ceaebeb63rd381wfbu9hw1yna", "g5uyftthhpby8nbz9a8y1dbsaa",
    "j44xp18p9fye3q8eq6ih6beyur", "tukp1agnbpy33p9op66ykmamna", "hx7iijf473rjmruzejif5qzx3y",
    "5cc7fs5fppf1pguw9yunaqdtiw", "1ua57rok17go9f1n5obnfzkwnh", "4djhtfywyj8sfrutmtwkd1q4ac",
    "bx1hxxqhtf8fjeoucqewy7jtkw", "8jo39raottnifdghwnz5e9ae9r", "xyzqywmn6bbwtqxqapmnzw8dey",
    "jpdtxfm7tibmpmwxiorp378f8o", "f8km9s64tbnoux8xb63qpba4uc", "rxxidz669idsux19n9694w8szc",
    "ojfa1qr1nb8ciy6t6dbfaejy5a", "38t9kcfq778ht869zaz1z56dph", "qeig9hass7fkxcxcxy4r7q4szr",
    "rgadorojf7bpdbnjzd9w4uz4ph", "kjhmcnmzmfddtcbpybsyu13fte", "69f5wzq7o3rszm55o8p8y9osce",
    "hfk47dse3788jfcx3t8qk1optw", "upt18p5zg3re8r1nb3duhgzr4e", "f1b4qjfwk3fsmdtekd5ufgyzxy",
    "jcdwtt4dmtdc8byu7szf7r7mgy", "d4ui86yxibbw7ept3bqb38j4dw", "zgtgc74wgif4irbuauyamcax8w",
    "96frbpues3nkdfe5zjfjn6q9ia", "drzkukk4p3gkdj9eonqm7yt6na", "cfytfnna5f89inhfoxkqe8cwfc",
    "bq7obr9rx3fxjbhh4uf5kejecr", "8otasprmi3ga7x6as1sttq1o6w", "a4zf5wrxgbr8imhajm6xers3qo",
    "84txspt9pjn4jbfmoomks9thay",
]

async def run(driver, args: str = "") -> None:
    import logging

    logger = logging.getLogger(__name__)

    today = datetime.date.today()
    quarter = (today.month - 1) // 3 + 1
    year = today.year
    move_out, deadline = _QUARTERS[quarter]

    message = (
        f"#### Erinnerung Kündigungsfrist // Reminder notice period :house_with_garden: \n\n"
        f"Liebe Mitbewohnis,\n"
        f"kurze Erinnerung, dass – falls ihr zum **{move_out}.{year}** ausziehen wollt – die Kündigungsfrist am **{deadline}.{year}** ist. "
        f"Gebt uns einfach durch eine kurze formlose Kündigung an [mietverwaltung@collegiumacademicum.de](mailto:mietverwaltung@collegiumacademicum.de) Bescheid :)\n\n"
        f"Dear flatmates,\n"
        f"A quick reminder that if you want to move out by the **{move_out}.{year}**, the deadline to send in your notice of termination is **{deadline}.{year}**. "
        f"So if this applies to you, please let us know by then via [mietverwaltung@collegiumacademicum.de](mailto:mietverwaltung@collegiumacademicum.de) :)"
    )

    for channel_id in CHANNELS:
        try:
            driver.posts.create_post({"channel_id": channel_id, "message": message})
        except Exception as e:
            logger.error(f"Error occurred while creating post in channel {channel_id}: {e}")